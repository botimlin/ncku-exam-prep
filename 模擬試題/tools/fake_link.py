#!/usr/bin/env python3
"""fake_link.py — 把「模擬 Pico」接到虛擬序列埠（pty）上，像插了 N 片板子。

    python3 tools/fake_link.py -n 2
    → 印出 /dev/pts/5 /dev/pts/6（每次不一樣），保持執行；Ctrl-C 結束
    另一個終端機：python3 q1/host/host.py --input in.bin --output out.txt --dev /dev/pts/5 --dev /dev/pts/6

選項：
    -n N            幾片板子（預設 1，最多 4）
    --device PATH   裝置程式（預設 q1/device/build/device，會先自動 make）
    --seed S        板子序號（預設 0x13572468；judge 用的序號不一樣）
"""
import argparse
import os
import signal
import subprocess
import sys
import tty

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def build_device(device_dir):
    r = subprocess.run(["make", "-s", "-C", device_dir], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("裝置程式編譯失敗")


def start_devices(device, n, seed, log=None):
    """回傳 [(proc, slave_path, slave_fd)]。slave_fd 要一直開著（關掉的話 pty 的 raw 設定可能會不見）。"""
    devs = []
    env = dict(os.environ, DEVICE_SEED=str(seed))
    for _ in range(n):
        master, slave = os.openpty()
        tty.setraw(slave)               # 像 pyserial 一樣：不轉換 \n、不 echo、不緩衝
        path = os.ttyname(slave)
        p = subprocess.Popen([device], stdin=master, stdout=master, stderr=log or subprocess.DEVNULL,
                             env=env, close_fds=True)
        os.close(master)
        devs.append((p, path, slave))
    return devs


def stop_devices(devs):
    for p, _, fd in devs:
        p.kill()
        p.wait()
        try:
            os.close(fd)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=1)
    ap.add_argument("--device", default=os.path.join(ROOT, "q1", "device", "build", "device"))
    ap.add_argument("--seed", default="0x13572468")
    a = ap.parse_args()
    if not 1 <= a.n <= 4:
        raise SystemExit("-n 要是 1..4")
    if a.device.endswith(os.path.join("q1", "device", "build", "device")):
        build_device(os.path.dirname(os.path.dirname(a.device)))
    devs = start_devices(a.device, a.n, int(a.seed, 0), log=sys.stderr)
    print(" ".join(path for _, path, _ in devs), flush=True)
    print("（Ctrl-C 結束）", file=sys.stderr)
    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        stop_devices(devs)


if __name__ == "__main__":
    main()
