import sys
import socket

from ServerWorker import ServerWorker


class Server:
    def main(self):
        try:
            server_port = int(sys.argv[1])
        except (IndexError, ValueError):
            print("[Usage: Server.py Server_port]")
            sys.exit(1)

        # Tạo socket TCP lắng nghe RTSP
        rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rtspSocket.bind(('', server_port))
        rtspSocket.listen(5)
        print(f"RTSP server listening on port {server_port}...")

        # Nhận kết nối từ client
        while True:
            clientInfo = {}
            clientInfo['rtspSocket'] = rtspSocket.accept()
            print("Client connected:", clientInfo['rtspSocket'][1])
            ServerWorker(clientInfo).run()


if __name__ == "__main__":
    Server().main()
