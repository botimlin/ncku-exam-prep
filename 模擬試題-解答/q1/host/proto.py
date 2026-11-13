"""proto.py — frame 的打包與解析（電腦端）。格式見 q1/README.md §2。

    frame = A5 5A | cmd | seq | len(2, little-endian) | payload(len) | crc32(4, little-endian)
    crc32 = zlib.crc32(cmd seq len_lo len_hi payload)
"""
import os
import select
import struct
import zlib

SOF = b"\xA5\x5A"

CMD_PING = 0x01
CMD_CALC_ONE = 0x10
CMD_CALC_BATCH = 0x11
RSP_FLAG = 0x80
RSP_ERROR = 0xEE

ERR_NAMES = {1: "BAD_CRC", 2: "BAD_LEN", 3: "UNKNOWN_CMD"}


class ProtoError(Exception):
    pass


def encode(cmd, seq, payload=b""):
    body = struct.pack("<BBH", cmd, seq, len(payload)) + payload
    return SOF + body + struct.pack("<I", zlib.crc32(body))


def send_frame(fd, cmd, seq, payload=b""):
    data = encode(cmd, seq, payload)
    off = 0
    while off < len(data):
        off += os.write(fd, data[off:])


def read_exact(fd, n, timeout=2.0):
    buf = b""
    while len(buf) < n:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            raise ProtoError(f"等了 {timeout} 秒只收到 {len(buf)}/{n} byte")
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise ProtoError("序列埠被關掉了")
        buf += chunk
    return buf


def recv_frame(fd, timeout=2.0):
    """回傳 (cmd, seq, payload)。裝置回錯誤（0xEE）時丟 ProtoError。"""
    # 找 SOF（中間有雜訊就跳過）
    prev = b""
    while True:
        b = read_exact(fd, 1, timeout)
        if prev == b"\xA5" and b == b"\x5A":
            break
        prev = b
    hdr = read_exact(fd, 4, timeout)
    cmd, seq, length = struct.unpack("<BBH", hdr)
    payload = read_exact(fd, length, timeout) if length else b""   # 解答 bug：os.read 可能只回傳一部分
    (crc,) = struct.unpack("<I", read_exact(fd, 4, timeout))
    if crc != zlib.crc32(hdr + payload):
        raise ProtoError(f"回應的 CRC 不對（cmd=0x{cmd:02X} seq={seq} len={length}）")
    if cmd == RSP_ERROR:
        orig, code = payload[0], payload[1]
        raise ProtoError(f"裝置回報錯誤：cmd=0x{orig:02X} {ERR_NAMES.get(code, code)}（seq={seq}）")
    return cmd, seq, payload
