class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except Exception:
            raise IOError(f"Cannot open video file {filename}")
        self.frameNum = 0

    def nextFrame(self):
        """Đọc frame kế tiếp từ file MJPEG."""
        # Độ dài frame được lưu ở 5 byte đầu (ASCII)
        data = self.file.read(5)
        if data:
            frameLength = int(data)

            # Đọc đúng frameLength byte cho frame hiện tại
            data = self.file.read(frameLength)
            self.frameNum += 1
        return data

    def frameNbr(self):
        """Trả về số thứ tự frame hiện tại."""
        return self.frameNum
