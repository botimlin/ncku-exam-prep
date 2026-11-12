#!/usr/bin/env python3
"""bench.py — 量「一包多大最划算」: 不同 payload 大小的來回延遲 (RTT) 與吞吐量 (bytes/s)

用 ECHO (0x01): 送 N bytes，Pico 原樣回傳，檢查內容一樣。
結論通常是: 小包 → 每包固定開銷 (USB 輪詢 ~1ms、Python 呼叫) 主宰，吞吐量很低；
            大包 (batch) → 開銷被攤平，吞吐量高很多。這就是「批次 + 二進位」比「一行一行文字」快的原因。

用法:
  python3 bench.py /dev/ttyACM0
  python3 bench.py /dev/pts/5 --sizes 4,64,1024,4096 --iters 200     (配 fake_pico.py)
"""
import argparse
import os
import time

import serial

from frame import CMD_ECHO, transact


def bench(ser, size, iters):
    """回傳 (平均 RTT 秒, 單向吞吐量 bytes/s)"""
    payload = os.urandom(size)
    t0 = time.perf_counter()
    for i in range(iters):
        reply = transact(ser, CMD_ECHO, payload, seq=i)
        if reply != payload:
            raise RuntimeError(f"size={size} 第 {i} 次 ECHO 內容不一樣!")
    dt = time.perf_counter() - t0
    return dt / iters, size * iters / dt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", default="/dev/ttyACM0")       # TODO(改這裡)
    ap.add_argument("--sizes", default="4,16,64,256,1024,4096")      # TODO(改這裡) 不要超過 Pico buffer
    ap.add_argument("--iters", type=int, default=100)
    args = ap.parse_args()

    ser = serial.Serial(args.port, timeout=0.05)
    print(f"{'payload(B)':>10} {'RTT(ms)':>9} {'吞吐量(KB/s)':>12}")
    for size in [int(s) for s in args.sizes.split(",")]:
        rtt, bps = bench(ser, size, args.iters)
        print(f"{size:>10} {rtt * 1000:>9.3f} {bps / 1024:>12.1f}")
    ser.close()
