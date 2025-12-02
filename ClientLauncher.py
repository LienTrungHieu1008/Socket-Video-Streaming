import sys
from tkinter import Tk
from Client import Client

if __name__ == "__main__":
    try:
        serverAddr = sys.argv[1]
        serverPort = sys.argv[2]
        rtpPort = sys.argv[3]
        fileName = sys.argv[4]
    except:
        print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]")
        serverAddr = 'localhost'
        serverPort = '6900'
        rtpPort = '25000'
        fileName = 'movie.Mjpeg'
    
    root = Tk()
    
    # Create a new client
    app = Client(root, serverAddr, serverPort, rtpPort, fileName)
    app.master.title("RTPClient")
    
    # --- [SỬA ĐỔI] ---
    # Xóa hoặc comment dòng geometry đi để cửa sổ tự co giãn ôm sát video
    # root.geometry("850x600") 
    
    # Vẫn cho phép người dùng kéo giãn nếu muốn
    root.resizable(True, True)
    # -----------------
    
    root.mainloop()