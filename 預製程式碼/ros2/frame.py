#!/usr/bin/env python3
"""frame.py — 主機 <-> Pico 的二進位封包格式 (encode / decode / 串流解析 / 收發)

封包格式 (多位元組欄位一律 little-endian，要跟 Pico 端一模一樣):
  [0]=0xAA [1]=0x55 [2]=cmd(u8) [3]=seq(u8) [4..5]=len(u16) [6..]=payload[len]
  最後 4 bytes = crc32(u32)，範圍 = 從 cmd 到 payload 結尾 (不含 AA 55)
cmd: 0x01 ECHO 原樣回傳 / 0x02 SUM_U32 回傳 u32 總和 / 0x03 CRC32 回傳 u32 crc
用法:  from frame import encode, FrameParser, transact, pack_u32, unpack_u32
自我測試:  python3 frame.py
"""
import struct
import sys
import time
import zlib

HDR = b"\xAA\x55"
CMD_ECHO, CMD_SUM_U32, CMD_CRC32 = 0x01, 0x02, 0x03  # TODO(改這裡) 題目若有新指令加在這
MAX_LEN = 8192           # = Pico 端 FRAME_MAX_PAYLOAD（pico/serial_proto.h）；len 比這大的封包當壞包丟掉（跟 Pico 一樣）。Pico 那邊改了這裡也要改
CHUNK_BYTES = 4096       # TODO(改這裡) 一包 payload 最多幾 bytes，要 <= Pico 端 FRAME_MAX_PAYLOAD (pico/serial_proto.h，目前 8192)


def encode(cmd, seq, payload=b""):
    """組一個封包 -> bytes。'<BBH' = u8 cmd, u8 seq, u16 len (小端)"""
    body = struct.pack("<BBH", cmd, seq & 0xFF, len(payload)) + bytes(payload)
    return HDR + body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def pack_u32(values):
    """整數 list -> u32 小端 bytes (負數會變成二補數，跟 C 的 uint32_t 一樣)"""
    return struct.pack(f"<{len(values)}I", *[v & 0xFFFFFFFF for v in values])


def unpack_u32(data):
    """u32 小端 bytes -> 整數 list"""
    return list(struct.unpack(f"<{len(data) // 4}I", data[: len(data) // 4 * 4]))


class FrameParser:
    """串流解析器: 資料可能一次來半包、或夾雜垃圾，丟進 feed() 就好。
    feed(bytes) 回傳 [(cmd, seq, payload), ...]，CRC 錯或 len > max_len 的包會被丟掉並重新對齊 AA 55。"""

    def __init__(self, max_len=MAX_LEN):
        self.buf = bytearray()
        self.max_len = max_len
        self.bad_crc = 0  # 統計 CRC 錯誤次數 (除錯用)
        self.bad_len = 0  # 統計 len 太大的次數 (Pico 會丟掉這種包、不回覆)

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(HDR)
            if i < 0:                       # 找不到表頭: 只留最後 1 byte (可能是半個 AA)
                del self.buf[:-1]
                return out
            del self.buf[:i]                # 丟掉表頭前的垃圾
            if len(self.buf) < 6:
                return out                  # 表頭還沒收齊，等下次
            cmd, seq, n = struct.unpack_from("<BBH", self.buf, 2)
            if n > self.max_len:            # 跟 Pico 的 proto_feed 一樣：len 太大 = 壞包（也避免為了垃圾 len 一直等）
                self.bad_len += 1
                del self.buf[:1]
                continue
            total = 6 + n + 4
            if len(self.buf) < total:
                return out                  # payload 還沒收齊，等下次
            body = bytes(self.buf[2:6 + n])
            (crc,) = struct.unpack_from("<I", self.buf, 6 + n)
            if zlib.crc32(body) & 0xFFFFFFFF == crc:
                out.append((cmd, seq, body[4:]))
                del self.buf[:total]
            else:
                self.bad_crc += 1
                del self.buf[:1]            # 壞包: 往後挪 1 byte 重新找 AA 55 (resync)


def transact(ser, cmd, payload, seq=0, timeout=1.0, retries=3):
    """送一包、等同 cmd 同 seq 的回覆，回傳回覆 payload。逾時就重送，全失敗丟 TimeoutError。
    ser = serial.Serial(port, timeout=0.05)  ← timeout 要小，read 才不會卡住"""
    pkt = encode(cmd, seq, payload)
    for attempt in range(retries):
        parser = FrameParser()
        ser.reset_input_buffer()            # 清掉上一次殘留的舊回覆
        ser.write(pkt)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = ser.read(ser.in_waiting or 1)
            for c, s, p in parser.feed(data):
                if c == cmd and s == (seq & 0xFF):
                    return p
        print(f"[transact] cmd={cmd:#x} seq={seq} 逾時，重試 {attempt + 1}/{retries}")
    raise TimeoutError(f"cmd={cmd:#x} seq={seq} 沒有回覆 (port 對嗎? Pico 有在跑嗎?)")


def split_fields(raw):
    """把一包 bytes 依封包格式切成 [(欄位, bytes)]；len 用「實際收到的 bytes」切，方便看出多/少了幾個"""
    if len(raw) < 6:
        return [("太短", raw)]
    n = len(raw) - 10                       # 2 sync + 4 header + 4 crc 以外的就是 payload
    return [("sync", raw[0:2]), ("cmd", raw[2:3]), ("seq", raw[3:4]), ("len", raw[4:6]),
            ("payload", raw[6:6 + max(n, 0)]), ("crc32", raw[6 + max(n, 0):])]


def diff(exp_hex, act_hex):
    """逐欄位比對預期 / 實際封包 → 印表格 + 第一個不同 + 線索（給小模型判斷原因，不要讓它自己數 byte）"""
    e, a = bytes.fromhex(exp_hex.replace(" ", "")), bytes.fromhex(act_hex.replace(" ", ""))
    print("| 欄位 | 預期 | 實際 | 相同? |")
    first = None
    for (k, ev), (_, av) in zip(split_fields(e), split_fields(a)):
        same = ev == av
        print(f"| {k} | {ev.hex(' ')} | {av.hex(' ')} | {'是' if same else '否'} |")
        first = first or (None if same else k)
    print(f"第一個不同：{first or '無'}（預期 {len(e)} bytes，實際 {len(a)} bytes）")
    hints = []
    if b"\r\n" in a and b"\r\n" not in e:
        hints.append("實際有 0d 0a、預期沒有 → CRLF 轉換沒關")
    if len(a) >= 6 and a[4:6] == e[4:6][::-1] and a[4:6] != e[4:6]:
        hints.append("len 兩個 byte 對調 → 大小端顛倒")
    if a[:2] != HDR:
        hints.append("開頭不是 aa 55 → 混入文字（printf）或少收 / 錯位")
    if len(a) >= 10 and zlib.crc32(a[2:-4]) & 0xFFFFFFFF != struct.unpack("<I", a[-4:])[0]:
        hints.append("實際封包的 crc32 對不上它自己的內容")
    print("線索：" + ("；".join(hints) if hints else "無"))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "diff":
    # 用法: python3 frame.py diff "aa 55 01 ..." "aa 55 01 ..."   (預期, 實際)
    if len(sys.argv) != 4:
        sys.exit('用法: python3 frame.py diff "預期 hex" "實際 hex"（兩個都要加引號）')
    diff(sys.argv[2], sys.argv[3])
    sys.exit(0)

if __name__ == "__main__":          # ---- 自我測試 (不需要板子) ----
    pkt = encode(CMD_ECHO, 7, b"hi")
    print("ECHO 'hi' =", pkt.hex(" "))
    p = FrameParser()
    # 1) 一次一 byte 慢慢餵 (模擬半包)
    got = [f for b in pkt for f in p.feed(bytes([b]))]
    assert got == [(CMD_ECHO, 7, b"hi")], got
    # 2) 前面有垃圾 + 一個壞 CRC 的包 + 兩個好包黏在一起
    bad = bytearray(encode(CMD_SUM_U32, 1, b"xxxx")); bad[-1] ^= 0xFF
    stream = b"\x00\xAA\x13" + bytes(bad) + encode(CMD_CRC32, 2, b"abc") + encode(CMD_ECHO, 3, b"")
    got = p.feed(stream[:10]) + p.feed(stream[10:])
    assert got == [(CMD_CRC32, 2, b"abc"), (CMD_ECHO, 3, b"")], got
    assert p.bad_crc == 1
    # 3) len 太大的包要丟掉並重新對齊（Pico 也是這樣）；後面的好包照收
    big = encode(CMD_ECHO, 4, b"z" * (MAX_LEN + 1))
    got = p.feed(big + encode(CMD_ECHO, 5, b"ok"))
    assert got == [(CMD_ECHO, 5, b"ok")] and p.bad_len == 1, got
    assert FrameParser().feed(encode(CMD_ECHO, 6, b"z" * MAX_LEN)) == [(CMD_ECHO, 6, b"z" * MAX_LEN)]
    # 4) u32 打包 / 解包
    assert unpack_u32(pack_u32([1, 2, -1])) == [1, 2, 0xFFFFFFFF]
    print("frame.py 自我測試 OK")
