from random import randint
import sys
import traceback
import threading
import socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket


class ServerWorker:
    # RTSP request types
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'

    # Server state
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    # RTSP reply codes
    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    clientInfo = {}

    def __init__(self, clientInfo):
        self.clientInfo = clientInfo

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()

    # ================ RTSP ================

    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))

    def processRtspRequest(self, data: str):
        """Process RTSP request sent from the client."""
        # Tách từng dòng
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]

        # Tên file
        filename = line1[1]

        # CSeq
        seq = request[1].split(' ')

        if requestType == self.SETUP:
            if self.state == self.INIT:
                print("processing SETUP\n")

                # Tạo VideoStream
                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                    return

                # Tạo Session ID ngẫu nhiên
                self.clientInfo['session'] = randint(100000, 999999)

                # Gửi reply OK
                self.replyRtsp(self.OK_200, seq[1])

                # Lấy RTP port từ header Transport
                # Transport: RTP/UDP; client_port=XXXX
                transportLine = request[2]    # "Transport: RTP/UDP; client_port=5004"
                for part in transportLine.split(';'):
                    part = part.strip()
                    if part.startswith("client_port"):
                        self.clientInfo['rtpPort'] = part.split('=')[1]
                        break

        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING

                # Tạo socket UDP gửi RTP
                self.clientInfo['rtpSocket'] = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM
                )

                self.replyRtsp(self.OK_200, seq[1])

                # Tạo thread gửi RTP
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker'] = threading.Thread(
                    target=self.sendRtp
                )
                self.clientInfo['worker'].start()

        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY

                self.clientInfo['event'].set()
                self.replyRtsp(self.OK_200, seq[1])

        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            try:
                self.clientInfo['event'].set()
            except Exception:
                pass

            self.replyRtsp(self.OK_200, seq[1])

            # Đóng RTP socket
            try:
                self.clientInfo['rtpSocket'].close()
            except Exception:
                pass

    # ================ RTP ================

    def sendRtp(self):
        """Send RTP packets over UDP."""
        while True:
            self.clientInfo['event'].wait(0.05)  # 50ms

            # Dừng nếu PAUSE hoặc TEARDOWN
            if self.clientInfo['event'].is_set():
                break

            data = self.clientInfo['videoStream'].nextFrame()
            if data:
                frameNumber = self.clientInfo['videoStream'].frameNbr()
                try:
                    address = self.clientInfo['rtspSocket'][1][0]
                    port = int(self.clientInfo['rtpPort'])
                    packet = self.makeRtp(data, frameNumber)
                    self.clientInfo['rtpSocket'].sendto(packet, (address, port))
                except Exception:
                    print("Connection Error")
                    print('-' * 60)
                    traceback.print_exc(file=sys.stdout)
                    print('-' * 60)

    def makeRtp(self, payload: bytes, frameNbr: int) -> bytes:
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26      # MJPEG
        seqnum = frameNbr
        ssrc = 0     # tuỳ chọn

        rtpPacket = RtpPacket()
        rtpPacket.encode(version, padding, extension, cc,
                         seqnum, marker, pt, ssrc, payload)

        return rtpPacket.getPacket()

    # ================ RTSP reply ================

    # ================ RTSP reply ================

    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        connSocket = self.clientInfo['rtspSocket'][0]

        if code == self.OK_200:
            reply = (
                "RTSP/1.0 200 OK\n"
                f"CSeq: {seq}\n"
                f"Session: {self.clientInfo['session']}\n\n"
            )
            connSocket.send(reply.encode())

        elif code == self.FILE_NOT_FOUND_404:
            reply = "RTSP/1.0 404 NOT FOUND\n\n"
            connSocket.send(reply.encode())

        elif code == self.CON_ERR_500:
            reply = "RTSP/1.0 500 CONNECTION ERROR\n\n"
            connSocket.send(reply.encode())

