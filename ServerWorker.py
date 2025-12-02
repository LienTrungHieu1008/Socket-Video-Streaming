from random import randint
import sys, traceback, threading, socket
import time  # <--- [QUAN TRỌNG] THÊM IMPORT NÀY

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2
    
    clientInfo = {}
    
    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        self.clientInfo['event'] = threading.Event()
        
    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()
    
    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:            
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))
    
    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        lines = data.split('\n')
        line1 = lines[0].split(' ')
        requestType = line1[0]
        filename = line1[1]
        seq = lines[1].split(' ')
        
        if requestType == self.SETUP:
            if self.state == self.INIT:
                print("processing SETUP\n")
                try:
                    self.videoStream = VideoStream(filename)
                    self.state = self.READY
                    self.clientInfo['session'] = randint(100000, 999999)
                    self.replyRtsp(self.OK_200, seq[1])
                    for line in lines:
                        if "client_port" in line:
                            self.clientInfo['rtpPort'] = int(line.split('client_port=')[1])
                            break
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
        
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING
                self.clientInfo['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.replyRtsp(self.OK_200, seq[1])
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker'] = threading.Thread(target=self.sendRtp) 
                self.clientInfo['worker'].start()
        
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY
                self.clientInfo['event'].set()
                self.replyRtsp(self.OK_200, seq[1])
        
        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")
            self.clientInfo['event'].set()
            self.replyRtsp(self.OK_200, seq[1])
            if 'rtpSocket' in self.clientInfo:
                self.clientInfo['rtpSocket'].close()

    def sendRtp(self):
        """Send RTP packets."""
        self.rtpPacket = RtpPacket()
        while True:
            self.clientInfo['event'].wait(0.05) 
            if self.clientInfo['event'].isSet(): break 
            
            data = self.videoStream.nextFrame()
            
            if data: 
                frameNumber = self.videoStream.frameNbr()
                try:
                    # --- LOGIC PHÂN MẢNH + CHỐNG FLOOD ---
                    MAX_PAYLOAD_SIZE = 1400 
                    size = len(data)
                    offset = 0
                    
                    while offset < size:
                        end = min(offset + MAX_PAYLOAD_SIZE, size)
                        payload = data[offset:end]
                        marker = 1 if end == size else 0
                        
                        self.rtpPacket.encode(version=2, padding=0, extension=0, cc=0, 
                                              seqnum=frameNumber, marker=marker, 
                                              pt=26, ssrc=0, payload=payload)
                        
                        self.clientInfo['rtpSocket'].sendto(self.rtpPacket.getPacket(), 
                                                            (self.clientInfo['rtspSocket'][1][0], self.clientInfo['rtpPort']))
                        
                        # [FIX LỖI MẤT GÓI 94%]
                        # Nghỉ cực ngắn (0.005s = 5ms) để Client kịp thở
                        # Nếu vẫn mất gói, hãy tăng lên 0.01
                        time.sleep(0.005) 
                        
                        offset = end
                except:
                    print("Connection Error")

    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode("utf-8"))
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")