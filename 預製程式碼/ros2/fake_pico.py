#!/usr/bin/env python3
"""fake_pico.py — 在電腦上假裝是 Pico (沒有板子也能測 serial_bridge / multi_device / bench)

原理: os.openpty() 開一對虛擬序列埠 (pty)。我們拿 master 端，
      你的程式像開 /dev/ttyACM0 一樣去開 slave 端 (例如 /dev/pts/5)。
支援 cmd: 0x01 ECHO / 0x02 SUM_U32 / 0x03 CRC32 (格式見 frame.py)

用法:
  python3 fake_pico.py                     # 開 1 個，印出路徑 (例如 /dev/pts/5)
  python3 fake_pico.py -n 2 --link /tmp/ttyFAKE   # 開 2 個，並建捷徑 /tmp/ttyFAKE0, /tmp/ttyFAKE1
  python3 fake_pico.py --us-per-byte 2     # 模擬 Pico 算很慢: 每 byte 多花 2 微秒 (看平行加速用)
"""
import argparse
import os
import signal
import sys
import threading
import time
import tty
import zlib

from frame import CMD_CRC32, CMD_ECHO, CMD_SUM_U32, FrameParser, encode, pack_u32, unpack_u32


def handle(cmd, payload):
    """模擬 Pico 的運算。回傳 reply payload；不認得的 cmd 回 None (不回覆)"""
    if cmd == CMD_ECHO:
        return payload
    if cmd == CMD_SUM_U32:
        return pack_u32([sum(unpack_u32(payload))])   # pack_u32 內部會 & 0xFFFFFFFF (溢位繞回)
    if cmd == CMD_CRC32:
        return pack_u32([zlib.crc32(payload)])
    # TODO(改這裡) 題目若有新 cmd (例如排序)，在這裡加，跟 Pico 端邏輯一致
    return None


def serve(name, fd, us_per_byte):
    """一顆假 Pico 的主迴圈: 讀 -> 解析 -> 算 -> 回覆"""
    parser = FrameParser()
    while True:
        try:
            data = os.read(fd, 65536)
        except OSError:          # 對方剛關掉 port，等它下次再開
            time.sleep(0.05)
            continue
        for cmd, seq, payload in parser.feed(data):
            reply = handle(cmd, payload)
            if reply is None:
                print(f"[{name}] 不認得的 cmd={cmd:#x}，不回覆", flush=True)
                continue
            if us_per_byte:
                time.sleep(len(payload) * us_per_byte / 1e6)
            out = memoryview(encode(cmd, seq, reply))
            while out:                       # os.write 可能只寫一部分，要寫到完
                out = out[os.write(fd, out):]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=1, help="開幾個假 Pico")
    ap.add_argument("--link", default="", help="建立捷徑前綴，例如 /tmp/ttyFAKE -> /tmp/ttyFAKE0")
    ap.add_argument("--us-per-byte", type=float, default=0.0, help="每 byte 額外延遲 (微秒)")
    args = ap.parse_args()

    keep = []  # slave fd 要一直開著，不然對方關掉 port 時 master 會讀到 EIO
    for i in range(args.n):
        master, slave = os.openpty()
        tty.setraw(slave)   # 很重要: raw 模式，不然終端機會把 0x0A/0x0D 之類的 byte 改掉
        tty.setraw(master)
        keep.append(slave)
        path = os.ttyname(slave)
        if args.link:
            link = f"{args.link}{i}"
            if os.path.lexists(link):
                os.unlink(link)
            os.symlink(path, link)
            path = f"{path}  (捷徑 {link})"
        print(f"[fake_pico] fake{i}: {path}", flush=True)
        # 每個假 Pico 一條執行緒 → 多顆真的會「同時」算 (模擬多塊板子平行)
        threading.Thread(target=serve, args=(f"fake{i}", master, args.us_per_byte), daemon=True).start()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # 被 kill 時也會清掉捷徑
    print("[fake_pico] 等待封包中... Ctrl+C 結束", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if args.link:
            for i in range(args.n):
                if os.path.islink(f"{args.link}{i}"):
                    os.unlink(f"{args.link}{i}")


if __name__ == "__main__":
    main()
