class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except:
            raise IOError
        self.frameNum = 0

    def nextFrame(self):
        """Get next frame."""
        # Thử đọc 5 byte đầu
        data = self.file.read(5)
        if len(data) < 5:
            return None # Hết file

        try:
            # TRƯỜNG HỢP 1: File chuẩn Lab cũ (có header text độ dài)
            framelength = int(data)
            self.frameNum += 1
            return self.file.read(framelength)
            
        except ValueError:
            # TRƯỜNG HỢP 2: File HD MJPEG Raw (bắt đầu bằng 0xFF 0xD8)
            frame_data = bytearray(data)
            
            while True:
                byte = self.file.read(1)
                if not byte: return None # Hết file
                
                frame_data.extend(byte)
                
                # Tìm dấu kết thúc JPEG (0xFF 0xD9)
                if len(frame_data) >= 2 and frame_data[-2] == 0xFF and frame_data[-1] == 0xD9:
                    self.frameNum += 1
                    return bytes(frame_data)

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum