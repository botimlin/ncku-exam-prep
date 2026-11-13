#!/usr/bin/env python3
"""解答：host.py — 批次（每 frame 64 筆）+ 多片板子平行（一片一條執行緒）。

改了什麼：
  1. seq 只有 1 byte：原本 seq = i，第 256 筆 struct.pack 就爆掉 → seq & 0xFF。
  2. CALC_ONE 每筆都要付一次約 1 ms 的 USB 來回 → 改成 CALC_BATCH 一次 64 筆（payload 1024 byte，規格上限）。
  3. 有幾片板子就開幾條執行緒，資料切成連續的幾段，各自送給一片，最後依原順序合併。
     （每片板子各自用一個 fd，一條執行緒只碰自己的 fd，所以不用鎖。）
"""
import argparse
import struct
import sys
import threading
import time

import link
import proto

RECORD = 16
BATCH = 64          # 1024 / 16：裝置 MAX_PAYLOAD 的上限


def run_device(path, records, out, err):
    try:
        fd = link.open_port(path)
        seq = 0
        for start in range(0, len(records), BATCH):
            chunk = records[start:start + BATCH]
            proto.send_frame(fd, proto.CMD_CALC_BATCH, seq, b"".join(chunk))
            cmd, rseq, payload = proto.recv_frame(fd)
            if cmd != (proto.CMD_CALC_BATCH | proto.RSP_FLAG) or rseq != seq or len(payload) != 4 * len(chunk):
                raise proto.ProtoError(f"{path}：回應不對 cmd=0x{cmd:02X} seq={rseq} len={len(payload)}")
            out.extend(struct.unpack(f"<{len(chunk)}I", payload))
            seq = (seq + 1) & 0xFF
    except Exception as e:          # 讓主執行緒知道哪一片出事
        err.append(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--dev", action="append", required=True)
    a = ap.parse_args()

    data = open(a.input, "rb").read()
    records = [data[i:i + RECORD] for i in range(0, len(data), RECORD)]
    t0 = time.perf_counter()

    n = len(a.dev)
    per = (len(records) + n - 1) // n
    parts = [records[k * per:(k + 1) * per] for k in range(n)]
    outs = [[] for _ in range(n)]
    errs = []
    th = [threading.Thread(target=run_device, args=(a.dev[k], parts[k], outs[k], errs)) for k in range(n)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    if errs:
        raise SystemExit(f"失敗：{errs[0]}")

    with open(a.output, "w") as f:
        for part in outs:
            for r in part:
                f.write(f"{r:08x}\n")
    print(f"{len(records)} 筆，{n} 片板子，{time.perf_counter() - t0:.2f} 秒", file=sys.stderr)


if __name__ == "__main__":
    main()
