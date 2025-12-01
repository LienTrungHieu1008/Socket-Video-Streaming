from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket
import threading
import io

from RtpPacket import RtpPacket

# Trạng thái của client
INIT = 0
READY = 1
PLAYING = 2

STATE_STRINGS = {
    INIT: "INIT",
    READY: "READY",
    PLAYING: "PLAYING"
}

# Mã lệnh RTSP
SETUP = 0
PLAY = 1
PAUSE = 2
TEARDOWN = 3


class Client:
    def __init__(self, master, serverAddr, serverPort, rtpPort, fileName):
        self.master = master
        self.serverAddr = serverAddr
        self.serverPort = int(serverPort)
        self.rtpPort = int(rtpPort)
        self.fileName = fileName

        # Trạng thái RTSP/Client
        self.state = INIT
        self.rtspSeq = 0          # CSeq
        self.sessionId = 0        # Session ID (nhận từ server ở SETUP)
        self.requestSent = -1     # Loại request cuối cùng đã gửi

        # Socket RTSP (TCP) và RTP (UDP)
        self.rtspSocket = None
        self.rtpSocket = None

        # Biến phục vụ nhận và hiển thị frame
        self.frameNbr = 0
        self.teardownAcked = False
        self.listenThread = None

        # GUI
        self.createWidgets()
        self.master.protocol("WM_DELETE_WINDOW", self.handler)

        # Kết nối tới server RTSP
        self.connectToServer()

    # ================== GUI ==================

    def createWidgets(self):
        """Tạo giao diện người dùng."""
        # Khung hiển thị video
        self.label = Label(self.master)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W + E + N + S,
                        padx=5, pady=5)

        # Nút SETUP
        self.setup = Button(self.master, width=10, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.handlerSetup
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Nút PLAY
        self.play = Button(self.master, width=10, padx=3, pady=3)
        self.play["text"] = "Play"
        self.play["command"] = self.handlerPlay
        self.play.grid(row=1, column=1, padx=2, pady=2)

        # Nút PAUSE
        self.pause = Button(self.master, width=10, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.handlerPause
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        # Nút TEARDOWN
        self.teardown = Button(self.master, width=10, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.handlerTeardown
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

    # ================== Kết nối RTSP ==================

    def connectToServer(self):
        """Kết nối tới server RTSP qua TCP."""
        try:
            self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except Exception as e:
            tkinter.messagebox.Message(
                self.master,
                title="Connection Error",
                message=f"Cannot connect to server {self.serverAddr}:{self.serverPort}\n{e}"
            ).show()

    # ================== Handler cho các nút ==================

    def handlerSetup(self):
        """Gửi yêu cầu SETUP."""
        if self.state != INIT:
            return

        try:
            # Tạo UDP socket dùng nhận RTP và bind vào rtpPort
            self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtpSocket.bind(('', self.rtpPort))
            self.rtpSocket.settimeout(0.5)  # timeout 0.5s như yêu cầu trong PDF
        except Exception as e:
            tkinter.messagebox.Message(
                self.master,
                title="RTP Socket Error",
                message=f"Cannot bind RTP port {self.rtpPort}.\n{e}"
            ).show()
            return

        self.sendRtspRequest(SETUP)

    def handlerPlay(self):
        """Gửi yêu cầu PLAY."""
        if self.state != READY:
            return

        # Bắt đầu thread lắng nghe RTP nếu chưa chạy
        if self.listenThread is None or not self.listenThread.is_alive():
            self.listenThread = threading.Thread(target=self.listenRtp)
            self.listenThread.daemon = True
            self.listenThread.start()

        self.sendRtspRequest(PLAY)

    def handlerPause(self):
        """Gửi yêu cầu PAUSE."""
        if self.state != PLAYING:
            return
        self.sendRtspRequest(PAUSE)

    def handlerTeardown(self):
        """Gửi yêu cầu TEARDOWN."""
        if self.state == INIT and self.sessionId == 0:
            # Chưa SETUP mà đóng luôn cửa sổ
            self.cleanup()
            return

        self.sendRtspRequest(TEARDOWN)
        self.teardownAcked = True  # báo cho thread listenRtp dừng

    def handler(self):
        """Xử lý khi người dùng tắt cửa sổ."""
        self.handlerTeardown()

    # ================== Nhận dữ liệu RTP ==================

    def listenRtp(self):
        """Nhận dữ liệu RTP từ server."""
        while not self.teardownAcked:
            if self.rtpSocket is None:
                break
            try:
                data, _ = self.rtpSocket.recvfrom(20480)  # buffer size
                if not data:
                    continue

                rtpPacket = RtpPacket()
                rtpPacket.decode(data)

                currFrameNbr = rtpPacket.seqNum()
                # Chỉ hiển thị frame mới (tránh lặp / trễ)
                if currFrameNbr > self.frameNbr:
                    self.frameNbr = currFrameNbr
                    payload = rtpPacket.getPayload()
                    self.updateMovie(payload)

            except socket.timeout:
                # Bình thường khi PAUSE hoặc mạng chậm
                continue
            except OSError:
                # Socket đã đóng
                break
            except Exception:
                # Có thể log thêm nếu cần
                break

    def updateMovie(self, image_data: bytes):
        """Cập nhật giao diện với frame mới (JPEG bytes)."""
        try:
            img = Image.open(io.BytesIO(image_data))
            photo = ImageTk.PhotoImage(img)
            self.label.configure(image=photo)
            self.label.image = photo  # giữ reference
        except Exception:
            # Bỏ qua frame bị lỗi
            pass

    # ================== RTSP ==================

    def sendRtspRequest(self, requestCode: int):
        """Xây dựng và gửi request RTSP tương ứng."""
        if self.rtspSocket is None:
            return

        # Không cho PLAY/PAUSE/TEARDOWN nếu chưa có Session ID
        if requestCode in (PLAY, PAUSE, TEARDOWN) and self.sessionId == 0:
            print("Session ID is 0. SETUP may have failed.")
            return

        # Tăng CSeq
        self.rtspSeq += 1

        request = ""

        if requestCode == SETUP:
            request += f"SETUP {self.fileName} RTSP/1.0\r\n"
            request += f"CSeq: {self.rtspSeq}\r\n"
            request += f"Transport: RTP/UDP; client_port={self.rtpPort}\r\n"

        elif requestCode == PLAY:
            request += f"PLAY {self.fileName} RTSP/1.0\r\n"
            request += f"CSeq: {self.rtspSeq}\r\n"
            request += f"Session: {self.sessionId}\r\n"

        elif requestCode == PAUSE:
            request += f"PAUSE {self.fileName} RTSP/1.0\r\n"
            request += f"CSeq: {self.rtspSeq}\r\n"
            request += f"Session: {self.sessionId}\r\n"

        elif requestCode == TEARDOWN:
            request += f"TEARDOWN {self.fileName} RTSP/1.0\r\n"
            request += f"CSeq: {self.rtspSeq}\r\n"
            request += f"Session: {self.sessionId}\r\n"

        # Kết thúc header bằng CRLF trống
        request += "\r\n"

        try:
            self.requestSent = requestCode
            self.rtspSocket.sendall(request.encode("utf-8"))
            self.recvRtspReply()
        except Exception as e:
            print("Failed to send RTSP request:", e)

    def recvRtspReply(self):
        """Đọc và xử lý phản hồi RTSP từ server."""
        try:
            reply = self.rtspSocket.recv(1024)
            if not reply:
                return
            reply = reply.decode("utf-8")
        except Exception:
            return

        # Chuẩn hoá và tách dòng
        lines = reply.replace('\r', '').split('\n')
        if len(lines) < 1:
            return

        # Dòng trạng thái: RTSP/1.0 200 OK
        status_line = lines[0].split(' ')
        if len(status_line) < 2:
            return
        status_code = status_line[1]

        if status_code == '200':
            # Thành công
            if self.requestSent == SETUP:
                # Lấy Session ID
                for line in lines[1:]:
                    if "Session" in line:
                        try:
                            self.sessionId = int(line.split(':')[1].strip())
                        except Exception:
                            pass
                        break
                self.state = READY
                print("State -> READY")

            elif self.requestSent == PLAY:
                self.state = PLAYING
                print("State -> PLAYING")

            elif self.requestSent == PAUSE:
                self.state = READY
                print("State -> READY")

            elif self.requestSent == TEARDOWN:
                self.state = INIT
                print("State -> INIT (teardown)")
                self.cleanup()

        elif status_code == '404':
            tkinter.messagebox.Message(
                self.master,
                title="RTSP Error",
                message="404 NOT FOUND: requested movie does not exist."
            ).show()

        elif status_code == '500':
            tkinter.messagebox.Message(
                self.master,
                title="RTSP Error",
                message="500 CONNECTION ERROR."
            ).show()

    # ================== Dọn tài nguyên ==================

    def cleanup(self):
        """Đóng socket và huỷ GUI."""
        self.teardownAcked = True

        try:
            if self.rtpSocket is not None:
                self.rtpSocket.close()
                self.rtpSocket = None
        except Exception:
            pass

        try:
            if self.rtspSocket is not None:
                self.rtspSocket.close()
                self.rtspSocket = None
        except Exception:
            pass

        try:
            self.master.destroy()
        except Exception:
            pass
