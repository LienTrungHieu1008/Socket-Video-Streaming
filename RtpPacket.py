from time import time

HEADER_SIZE = 12


class RtpPacket:
    """Lớp gói RTP: dùng để đóng gói (server) và giải gói (client)."""

    def __init__(self):
        self.header = bytearray(HEADER_SIZE)
        self.payload = b""

    # =============== Server side ===============

    def encode(self, version, padding, extension, cc,
               seqnum, marker, pt, ssrc, payload: bytes):
        """
        Tạo gói RTP với các field đã cho.
        - version: RTP version, phải = 2
        - padding, extension, cc, marker: trong lab đều = 0
        - seqnum: số thứ tự frame (frameNbr từ VideoStream)
        - pt: payload type (26 cho MJPEG)
        - ssrc: định danh nguồn (tuỳ chọn 32-bit int)
        - payload: dữ liệu JPEG của frame
        """

        # Timestamp (32-bit), dùng giây hiện tại
        timestamp = int(time())

        # Byte 0: V(2) | P(1) | X(1) | CC(4)
        # V=2 (10), P=0, X=0, CC=0 => 1000 0000 = 0x80
        self.header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc

        # Byte 1: M(1) | PT(7)
        self.header[1] = (marker << 7) | (pt & 0x7F)

        # Byte 2-3: Sequence Number (16-bit)
        self.header[2] = (seqnum >> 8) & 0xFF
        self.header[3] = seqnum & 0xFF # 00000000 .......
        # Byte 4-7: Timestamp (32-bit)
        self.header[4] = (timestamp >> 24) & 0xFF
        self.header[5] = (timestamp >> 16) & 0xFF
        self.header[6] = (timestamp >> 8) & 0xFF
        self.header[7] = timestamp & 0xFF

        # Byte 8-11: SSRC (32-bit)
        self.header[8] = (ssrc >> 24) & 0xFF
        self.header[9] = (ssrc >> 16) & 0xFF
        self.header[10] = (ssrc >> 8) & 0xFF
        self.header[11] = ssrc & 0xFF

        # Payload
        self.payload = payload

    # =============== Client side ===============

    def decode(self, byteStream: bytes):
        """Giải mã một byte stream thành header + payload."""
        self.header = bytearray(byteStream[:HEADER_SIZE])
        self.payload = byteStream[HEADER_SIZE:]

    # =============== Getter ===============

    def version(self):
        return int(self.header[0] >> 6)

    def seqNum(self):
        return int(self.header[2] << 8 | self.header[3])

    def timestamp(self):
        return int(
            self.header[4] << 24
            | self.header[5] << 16
            | self.header[6] << 8
            | self.header[7]
        )

    def payloadType(self):
        return int(self.header[1] & 0x7F)

    def getPayload(self):
        return self.payload

    def getPacket(self):
        """Trả về toàn bộ gói RTP (header + payload)."""
        return self.header + self.payload
