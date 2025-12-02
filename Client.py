from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket
import time
import threading
import io
import sys
import traceback

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
        self.playEvent = threading.Event()
        self.stopEvent = threading.Event()

        # --- THÊM BIẾN THỐNG KÊ (STATISTICS) ---
        self.startTime = 0
        self.totalBytes = 0       # Tổng số byte nhận được
        self.totalFrames = 0      # Tổng số frame nhận được
        self.expectedFrames = 0   # Tổng số frame lẽ ra phải nhận (dựa trên SeqNum)
        self.lostFrames = 0       # Số frame bị mất\

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

        # --- PHẦN NÂNG CAO: CHỌN ĐỘ PHÂN GIẢI ---
        # Label hướng dẫn
        lbl_res = Label(self.master, text="Resolution:", height=2)
        lbl_res.grid(row=2, column=0, sticky=E, padx=5)

        # Biến lưu lựa chọn
        self.resolution = StringVar()
        self.resolution.set(self.fileName) # Mặc định là tên file nhập từ dòng lệnh

        # Radio Button 720p (Cần có file movie_720.Mjpeg trong thư mục)
        self.btn720 = Radiobutton(self.master, text="720p", variable=self.resolution, value="movie_720.Mjpeg")
        self.btn720.grid(row=2, column=1, sticky=W)

        # Radio Button 1080p (Cần có file movie_1080.Mjpeg trong thư mục)
        self.btn1080 = Radiobutton(self.master, text="1080p", variable=self.resolution, value="movie_1080.Mjpeg")
        self.btn1080.grid(row=2, column=2, sticky=W)
        
        # --- THÊM KHU VỰC HIỂN THỊ THÔNG SỐ (STATS) ---
        # Label hiển thị Băng thông (Bitrate)
        self.lblRate = Label(self.master, text="Rate: 0 kbps", font=("Helvetica", 10, "bold"))
        self.lblRate.grid(row=3, column=0, padx=5, pady=5)
        
        # Label hiển thị Tổng dữ liệu (Total Data)
        self.lblBytes = Label(self.master, text="Data: 0 MB", font=("Helvetica", 10))
        self.lblBytes.grid(row=3, column=1, padx=5, pady=5)
        
        # Label hiển thị Tỉ lệ mất gói (Loss)
        self.lblLoss = Label(self.master, text="Loss: 0%", font=("Helvetica", 10, "bold"), fg="red")
        self.lblLoss.grid(row=3, column=2, padx=5, pady=5)
        

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
        if self.state == INIT:
            try:
                # Tạo UDP socket dùng nhận RTP và bind vào rtpPort
                self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.rtpSocket.bind(('', self.rtpPort))
                self.rtpSocket.settimeout(0.5)  # timeout 0.5s như yêu cầu
                
                self.sendRtspRequest(SETUP)
            except Exception as e:
                tkinter.messagebox.Message(
                    self.master,
                    title="RTP Socket Error",
                    message=f"Cannot bind RTP port {self.rtpPort}.\n{e}"
                ).show()

    def handlerPlay(self):
        """Gửi yêu cầu PLAY."""
        if self.state == READY:
            # Tạo thread mới
            self.playEvent.set()
            self.stopEvent.clear()
            
            # Chỉ tạo thread nếu chưa có hoặc đã chết
            if self.listenThread is None or not self.listenThread.is_alive():
                self.listenThread = threading.Thread(target=self.listenRtp)
                self.listenThread.daemon = True
                self.listenThread.start()

            self.sendRtspRequest(PLAY)

    def handlerPause(self):
        """Gửi yêu cầu PAUSE."""
        if self.state == PLAYING:
            self.playEvent.clear()
            self.sendRtspRequest(PAUSE)

    def handlerTeardown(self):
        """Gửi yêu cầu TEARDOWN."""
        self.sendRtspRequest(TEARDOWN)
        
        self.stopEvent.set()
        self.playEvent.clear()
        
        # Đóng socket RTP
        try:
            self.rtpSocket.close()
        except:
            pass
            
        # Đóng socket RTSP
        try:
             self.rtspSocket.shutdown(socket.SHUT_RDWR)
             self.rtspSocket.close()
        except:
             pass
        
        self.master.destroy()

    def handler(self):
        """Xử lý khi người dùng tắt cửa sổ."""
        self.handlerTeardown()

    # ================== Nhận dữ liệu RTP ==================

    def listenRtp(self):
            """Nhận dữ liệu RTP và tính toán thống kê (Stats)."""
            current_frame_buffer = bytearray()
            
            # Ghi nhận thời gian bắt đầu
            self.startTime = time.time()
            
            while True:
                self.playEvent.wait()
                if self.stopEvent.is_set(): break
                
                try:
                    data, addr = self.rtpSocket.recvfrom(20480)
                    if data:
                        # 1. CẬP NHẬT THÔNG SỐ MẠNG (NETWORK USAGE)
                        cur_time = time.time()
                        self.totalBytes += len(data) # Cộng dồn số byte nhận được
                        
                        # Tính tốc độ (kbps) = (Tổng bit / Tổng thời gian) / 1000
                        duration = cur_time - self.startTime
                        if duration > 0:
                            bitrate = (self.totalBytes * 8) / duration / 1000 
                            # Cập nhật Label Băng thông
                            self.lblRate.configure(text=f"Rate: {int(bitrate)} kbps")
                            
                            # Cập nhật Label Tổng dữ liệu (MB)
                            mbytes = self.totalBytes / (1024 * 1024)
                            self.lblBytes.configure(text=f"Data: {mbytes:.1f} MB")

                        rtpPacket = RtpPacket()
                        rtpPacket.decode(data)
                        current_frame_buffer.extend(rtpPacket.getPayload())

                        if rtpPacket.getMarker() == 1:
                            currFrameNbr = rtpPacket.seqNum()
                            
                            # 2. CẬP NHẬT THÔNG SỐ MẤT GÓI (FRAME LOSS)
                            # Nếu đây là frame mới
                            if currFrameNbr > self.frameNbr:
                                # Tính số frame bị nhảy cóc (Loss)
                                # Ví dụ: Đang frame 5, nhận được frame 7 -> Mất frame 6
                                diff = currFrameNbr - self.frameNbr
                                if diff > 1:
                                    self.lostFrames += (diff - 1)
                                
                                self.expectedFrames = currFrameNbr # Giả sử frame hiện tại là max
                                
                                # Tính tỉ lệ % mất
                                if self.expectedFrames > 0:
                                    loss_rate = (self.lostFrames / self.expectedFrames) * 100
                                    self.lblLoss.configure(text=f"Loss: {loss_rate:.1f}%")

                                self.frameNbr = currFrameNbr
                                self.totalFrames += 1
                                
                                self.updateMovie(bytes(current_frame_buffer))
                            
                            current_frame_buffer = bytearray()
                except:
                    if self.playEvent.isSet(): break

    def updateMovie(self, image_data):
            """Cập nhật giao diện với frame mới (đã resize)."""
            try:
                # 1. Đọc ảnh từ dữ liệu nhận được
                img = Image.open(io.BytesIO(image_data))
                
                # --- [FIX MẤT NÚT] THU NHỎ ẢNH ---
                # Ép ảnh về chiều ngang 640px (hoặc 800px) để vừa cửa sổ
                fixed_width = 640 
                
                # Tính toán chiều cao tự động theo tỷ lệ để ảnh không bị méo
                width_percent = (fixed_width / float(img.size[0]))
                height_size = int((float(img.size[1]) * float(width_percent)))
                
                # Thực hiện resize (LANCZOS giúp ảnh nét đẹp)
                img = img.resize((fixed_width, height_size), Image.Resampling.LANCZOS)
                # ---------------------------------
                
                # 2. Hiển thị lên giao diện
                photo = ImageTk.PhotoImage(img)
                self.label.configure(image=photo)
                self.label.image = photo 
            except Exception:
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

        # --- [NÂNG CAO] CẬP NHẬT TÊN FILE NẾU CHỌN HD ---
        if requestCode == SETUP:
            try:
                # Lấy tên file từ Radio Button
                if self.resolution.get():
                    self.fileName = self.resolution.get()
            except:
                pass 
        # -----------------------------------------------

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
            # --- IN LOG CHUẨN ĐỀ BÀI (C: Client) ---
            print('\n'.join(['C: ' + line for line in request.split('\n') if line]))
            # ---------------------------------------
            
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
        
        # --- IN LOG CHUẨN ĐỀ BÀI (S: Server) ---
        print('\n'.join(['S: ' + line for line in reply.split('\n') if line]))
        # ---------------------------------------

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
                # print("State -> READY")

            elif self.requestSent == PLAY:
                self.state = PLAYING
                # print("State -> PLAYING")

            elif self.requestSent == PAUSE:
                self.state = READY
                # print("State -> READY")

            elif self.requestSent == TEARDOWN:
                self.state = INIT
                # print("State -> INIT (teardown)")
                # Không gọi self.cleanup() ở đây để tránh lỗi GUI, 
                # việc đóng cửa sổ đã được xử lý ở handlerTeardown

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