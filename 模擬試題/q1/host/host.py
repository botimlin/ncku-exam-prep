#!/usr/bin/env python3
"""host.py — 電腦端：把資料一筆一筆送給板子算，收回結果。

    python3 host.py --input in.bin --output out.txt --dev /dev/pts/5 [--dev /dev/pts/6 ...]

輸入：in.bin = N 筆 16 byte 的資料，直接接在一起。
輸出：out.txt = N 行，第 i 行是第 i 筆的結果，8 位小寫十六進位（例：0badc0de）。
judge 可能會給 1～2 個 --dev。

規格在 q1/README.md。這是可以改的檔案（proto.py 也可以改）。
"""
import argparse
import struct
import sys
import time

import link
import proto

RECORD = 16


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--dev", action="append", required=True)
    a = ap.parse_args()

    data = open(a.input, "rb").read()
    records = [data[i:i + RECORD] for i in range(0, len(data), RECORD)]

    fd = link.open_port(a.dev[0])
    t0 = time.perf_counter()

    results = []
    for i, rec in enumerate(records):
        proto.send_frame(fd, proto.CMD_CALC_ONE, i, rec)
        cmd, seq, payload = proto.recv_frame(fd)
        if cmd != (proto.CMD_CALC_ONE | proto.RSP_FLAG) or seq != i:
            raise SystemExit(f"第 {i} 筆的回應不對：cmd=0x{cmd:02X} seq={seq}")
        (r,) = struct.unpack("<I", payload)
        results.append(r)

    with open(a.output, "w") as f:
        for r in results:
            f.write(f"{r:08x}\n")
    print(f"{len(records)} 筆，{time.perf_counter() - t0:.2f} 秒", file=sys.stderr)


if __name__ == "__main__":
    main()
