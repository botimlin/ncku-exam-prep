#!/usr/bin/env python3
"""multi_device.py — 把一份工作切塊，同時丟給 N 塊板子算，再依順序合併 (split -> send -> gather)

2025 年考古: 「分兩塊板子平行算再收結果」是加分關鍵。不需要 ROS 也能用。
每個 port 一條執行緒；所有 chunk 放在共用佇列，誰先算完誰就拿下一塊 (快的板子會多做)。
結果存在 results[chunk 編號] → 不管誰先回來，合併時順序一定正確。

測試 (不用板子):
  終端機1: python3 fake_pico.py -n 2 --link /tmp/ttyFAKE --us-per-byte 1
  終端機2: python3 multi_device.py /tmp/ttyFAKE0 /tmp/ttyFAKE1
真的板子: python3 multi_device.py /dev/ttyACM0 /dev/ttyACM1
"""
import queue
import random
import sys
import threading
import time

import serial  # pip install pyserial  /  apt install python3-serial

from frame import CHUNK_BYTES, CMD_SUM_U32, pack_u32, transact, unpack_u32


def split(data, chunk_bytes=CHUNK_BYTES, align=4):
    """bytes 切成多塊，每塊 <= chunk_bytes，且長度是 align 的倍數 (u32 不能被切一半!)"""
    step = max(align, chunk_bytes // align * align)
    return [data[i:i + step] for i in range(0, len(data), step)]


def worker(port, jobs, results, cmd, stats):
    """一塊板子一條執行緒: 自己開 port、從佇列拿 chunk、送出、把結果放回 results[idx]"""
    ser = serial.Serial(port, timeout=0.05)   # USB CDC 不看 baudrate，隨便填
    done = 0
    try:
        while True:
            try:
                idx, chunk = jobs.get_nowait()
            except queue.Empty:
                break
            try:
                results[idx] = transact(ser, cmd, chunk, seq=idx)   # seq 用 chunk 編號 (只取低 8 bit)
            except TimeoutError as e:
                print(f"[{port}] chunk {idx} 失敗: {e}")
                results[idx] = None
            done += 1
    finally:
        ser.close()
        stats[port] = done


def run_parallel(ports, chunks, cmd):
    """把 chunks 分給所有 ports 平行處理，回傳依 chunk 順序排好的 reply payload list"""
    jobs = queue.Queue()
    for i, c in enumerate(chunks):
        jobs.put((i, c))
    results = [None] * len(chunks)
    stats = {}
    threads = [threading.Thread(target=worker, args=(p, jobs, results, cmd, stats)) for p in ports]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("  每個 port 做了幾塊:", stats)
    if any(r is None for r in results):
        raise RuntimeError("有 chunk 失敗，見上方訊息")
    return results


def merge_sum(replies):
    """TODO(改這裡) 合併方式依題目而定。SUM: 各塊總和再加起來 (mod 2^32)。
    排序題: 各塊排好後要做 k-way merge (heapq.merge)；CRC32 不能直接相加，要整份一次算或用 crc32 的續算參數。"""
    return sum(unpack_u32(r)[0] for r in replies) & 0xFFFFFFFF


if __name__ == "__main__":
    ports = sys.argv[1:] or ["/dev/ttyACM0"]            # TODO(改這裡) 你的 port 們
    values = [random.getrandbits(32) for _ in range(200_000)]  # TODO(改這裡) 換成題目給的資料
    data = pack_u32(values)
    chunks = split(data)
    expect = sum(values) & 0xFFFFFFFF
    print(f"資料 {len(data)} bytes，切成 {len(chunks)} 塊，每塊 <= {CHUNK_BYTES} bytes")

    for use in ([ports[0]], ports) if len(ports) > 1 else ([ports[0]],):
        t0 = time.perf_counter()
        ans = merge_sum(run_parallel(use, chunks, CMD_SUM_U32))
        dt = time.perf_counter() - t0
        print(f"{len(use)} 個 port: 答案={ans} 正確={ans == expect} 花 {dt * 1000:.1f} ms")
