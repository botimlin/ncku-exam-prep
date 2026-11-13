#!/usr/bin/env python3
"""judge.py — 模擬試題的本地評分（模擬 GitLab CI 上的 judge）

    python3 judge.py            # 全部
    python3 judge.py q1         # 只評第一大題（也可以 q2-1、q2-2、q2-3，可以一次給好幾個）
    python3 judge.py q1 -v      # 失敗時多印一些細節

judge 的程式和 judge/ 資料夾不用看（真的考試看不到 judge）。卡住時看 README 和各題的 README。
2-1 需要 ROS 2（在 srecruit-demo 容器裡跑）；沒有 ROS 2 時會跳過。
"""
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(ROOT, "judge")
sys.path.insert(0, os.path.join(ROOT, "tools"))

VERBOSE = "-v" in sys.argv
with open(os.path.join(JUDGE, "vectors.json")) as _f:
    V = json.load(_f)


class Score:
    def __init__(self, name, total):
        self.name, self.total, self.got, self.lines = name, total, 0, []

    def item(self, ok, pts, desc, why=""):
        if ok:
            self.got += pts
        mark = "PASS" if ok else "FAIL"
        self.lines.append(f"  [{mark}] {pts if ok else 0:>2}/{pts:<2} {desc}" + (f"\n           → {why}" if why and not ok else ""))

    def note(self, s):
        self.lines.append(f"           {s}")

    def show(self):
        print(f"\n===== {self.name}：{self.got}/{self.total} =====")
        print("\n".join(self.lines))


def sh(cmd, cwd=None, timeout=120, env=None, input=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env, input=input)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return "timeout", out, err


def tail(s, n=6):
    lines = [l for l in (s or "").strip().splitlines() if l.strip()]
    return " | ".join(lines[-n:]) if lines else "（沒有輸出）"


def check_protected(prefix):
    bad = []
    for rel, h in V["protected"].items():
        if rel.startswith(prefix):
            p = os.path.join(ROOT, rel)
            if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != h:
                bad.append(rel)
    return bad


# ---------------------------------------------------------------- 第一大題
def judge_q1():
    S = Score("第一大題（主機 ↔ 裝置）", 40)
    bad = check_protected("q1/")
    if bad:
        S.item(False, 40, "不能改的檔案沒有被改", "被改過：" + "、".join(bad) + "（用 git checkout 還原）")
        return S
    dev_dir = os.path.join(ROOT, "q1", "device")
    rc, out, err = sh(["make", "-C", dev_dir, "-B"])
    if rc != 0:
        S.item(False, 40, "裝置程式編譯", tail(out + err))
        return S
    import fake_link
    device = os.path.join(dev_dir, "build", "device")
    host = os.path.join(ROOT, "q1", "host", "host.py")
    tmp = tempfile.mkdtemp(prefix="judge_q1_")
    try:
        def run_case(n_rec, n_dev, seed, data_seed, timeout):
            rnd = random.Random(data_seed)
            data = bytes(rnd.getrandbits(8) for _ in range(16 * n_rec))
            inp, outp = os.path.join(tmp, f"in{n_rec}.bin"), os.path.join(tmp, f"out{n_rec}.txt")
            open(inp, "wb").write(data)
            if os.path.exists(outp):
                os.remove(outp)
            sb = struct.pack("<I", seed)
            exp = [f"{zlib.crc32(sb + data[16 * i:16 * i + 16]):08x}" for i in range(n_rec)]
            devs = fake_link.start_devices(device, n_dev, seed)
            try:
                cmd = [sys.executable, host, "--input", inp, "--output", outp]
                for _, path, _ in devs:
                    cmd += ["--dev", path]
                t0 = time.perf_counter()
                rc, o, e = sh(cmd, cwd=os.path.dirname(host), timeout=timeout)
                dt = time.perf_counter() - t0
            finally:
                fake_link.stop_devices(devs)
            if rc == "timeout":
                return False, None, f"超過 {timeout} 秒沒跑完"
            if rc != 0:
                return False, None, f"host.py 結束碼 {rc}：{tail(e, 3)}"
            if not os.path.exists(outp):
                return False, None, "沒有產生輸出檔"
            got = [l.strip() for l in open(outp) if l.strip()]
            if len(got) != n_rec:
                return False, dt, f"輸出 {len(got)} 行，應該 {n_rec} 行"
            for i, (g, x) in enumerate(zip(got, exp)):
                if g.lower() != x:
                    return False, dt, f"第 {i} 行（從 0 算）是 {g}，應該是 {x}"
            return True, dt, ""

        seed = random.getrandbits(32) | 1
        ok_s, _, why_s = run_case(37, 1, seed, 1, 30)
        S.item(ok_s, 6, "小測資：37 筆、1 片板子，結果全部正確", why_s)
        ok, dt, why = run_case(4000, 2, seed, 2, 60)
        S.item(ok, 14, "大測資：4000 筆、2 片板子，結果全部正確", why)
        if ok:
            S.note(f"大測資花了 {dt:.2f} 秒")
            S.item(dt <= 2.5, 6, "效能 1：≤ 2.5 秒", f"{dt:.2f} 秒")
            S.item(dt <= 0.75, 6, "效能 2：≤ 0.75 秒", f"{dt:.2f} 秒")
            S.item(dt <= 0.45, 8, "效能 3：≤ 0.45 秒", f"{dt:.2f} 秒")
        else:
            S.item(False, 20, "效能（大測資要先正確）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return S


# ---------------------------------------------------------------- 2-1
def judge_q2_1():
    S = Score("2-1（ROS 2）", 20)
    rc, _, _ = sh([sys.executable, "-c", "import rclpy, std_msgs.msg"], timeout=30)
    if rc != 0:
        S.lines.append("  [SKIP] 找不到 rclpy：請在 srecruit-demo 容器裡、source /opt/ros/jazzy/setup.bash 之後再跑")
        S.total = 0
        return S
    bad = check_protected("q2-1/")
    if bad:
        S.item(False, 17, "不能改的檔案沒有被改", "被改過：" + "、".join(bad))
        return S
    d = os.path.join(ROOT, "q2-1")
    tmp = tempfile.mkdtemp(prefix="judge_q21_")
    log = os.path.join(tmp, "monitor.log")
    env = dict(os.environ, ROS_DOMAIN_ID=str(random.randint(60, 99)), ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",
               PYTHONUNBUFFERED="1")
    procs = []
    try:
        def start(name):
            f = open(os.path.join(tmp, name + ".out"), "w")
            p = subprocess.Popen([sys.executable, os.path.join(d, name + ".py")], cwd=d, env=env,
                                 stdout=f, stderr=subprocess.STDOUT)
            procs.append(p)
            return p
        start("filter_node")
        mon = subprocess.Popen([sys.executable, os.path.join(d, "monitor_node.py"), "--count", "40",
                                "--timeout", "30", "--log", log], cwd=d, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(3)                       # 先讓 filter 和 monitor 互相發現
        start("sensor_node")
        try:
            mon.wait(timeout=45)
        except subprocess.TimeoutExpired:
            mon.kill()
        rows = []
        if os.path.exists(log):
            for line in open(log):
                p = line.split()
                if len(p) == 3:
                    rows.append((int(p[0]), int(p[1]), float(p[2])))
        S.item(len(rows) >= 40, 8, "monitor 在 30 秒內收到 40 筆 /sensor/filtered",
               f"只收到 {len(rows)} 筆")
        if rows:
            v = lambda s: (s * 37) % 101
            full = [(s, a) for s, a, _ in rows if s >= 3]
            good = sum(1 for s, a in full if a == sum(v(k) for k in range(s - 3, s + 1)) // 4)
            ok = bool(full) and good >= 0.9 * len(full)
            first_bad = next(((s, a) for s, a in full if a != sum(v(k) for k in range(s - 3, s + 1)) // 4), None)
            S.item(ok, 6, "移動平均的值正確（seq ≥ 3 的筆數至少 90% 正確）",
                   f"{good}/{len(full)} 正確" + (f"；例：seq={first_bad[0]} 收到 {first_bad[1]}，"
                                                 f"應該是 {sum(v(k) for k in range(first_bad[0] - 3, first_bad[0] + 1)) // 4}"
                                                 if first_bad else ""))
            if len(rows) >= 10:
                hz = (len(rows) - 1) / max(1e-6, rows[-1][2] - rows[0][2])
                S.item(15 <= hz <= 25, 3, "頻率 15～25 Hz", f"量到 {hz:.1f} Hz")
            else:
                S.item(False, 3, "頻率 15～25 Hz", "收到的筆數太少，量不出頻率")
        else:
            S.item(False, 9, "值與頻率（要先收得到資料）")
        if VERBOSE:
            for name in ("filter_node", "sensor_node"):
                p = os.path.join(tmp, name + ".out")
                if os.path.exists(p):
                    S.note(f"{name} 的輸出：{tail(open(p).read(), 4)}")
        S.lines.append("  [自評] 3 分：ANSWERS.md 的 3 題（每題 1 分，寫出實際用的指令和看到的關鍵輸出）")
        S.total = 17
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    return S


# ---------------------------------------------------------------- 2-2
def judge_q2_2():
    S = Score("2-2（位元欄位 / PIO / RISC-V）", 20)
    bad = check_protected("q2-2/") + check_protected("tools/") + check_protected("judge/q2_2")
    if bad:
        S.item(False, 20, "不能改的檔案沒有被改", "被改過：" + "、".join(bad))
        return S
    d = os.path.join(ROOT, "q2-2")
    tmp = tempfile.mkdtemp(prefix="judge_q22_")
    try:
        exe = os.path.join(tmp, "h")
        rc, o, e = sh(["cc", "-O2", "-std=c11", "-w", "-I", d, "-o", exe, os.path.join(JUDGE, "q2_2_harness.c"),
                       os.path.join(d, "packet.c"), os.path.join(d, "rv_imm.c")])
        if rc != 0:
            S.item(False, 14, "packet.c / rv_imm.c 編譯", tail(o + e))
        else:
            def ask(lines):
                rc, o, e = sh([exe], input="\n".join(lines) + "\n", timeout=20)
                if rc != 0:
                    return None, f"程式結束碼 {rc}：{tail(e, 2)}"
                return o.splitlines(), ""

            cases = V["parse"]
            out, why = ask(["P " + " ".join(f"{b:02x}" for b in c["bytes"]) for c in cases])
            fail = why
            if out is not None:
                for c, line in zip(cases, out):
                    p = list(map(int, line.split()))
                    hexb = " ".join(f"{b:02X}" for b in c["bytes"])
                    if p[0] != c["ret"]:
                        fail = f"輸入 {hexb}：回傳 {p[0]}，應該是 {c['ret']}"
                        break
                    if c["fields"] and p[1:] != c["fields"]:
                        fail = f"輸入 {hexb}：欄位 (ver type len seq flags) = {p[1:]}，應該是 {c['fields']}"
                        break
                if len(out) != len(cases) and not fail:
                    fail = "輸出筆數不對"
            S.item(not fail, 4, f"A parse_header（{len(cases)} 組，含 CRC 錯、版本錯）", fail)

            cases = V["build"]
            out, why = ask(["B " + " ".join(map(str, c["fields"])) for c in cases])
            fail = why
            if out is not None:
                for c, line in zip(cases, out):
                    want = "".join(f"{b:02x}" for b in c["bytes"])
                    if line.strip() != want:
                        fail = f"欄位 {c['fields']}：得到 {line.strip()}，應該是 {want}"
                        break
            S.item(not fail, 3, f"A build_header（{len(cases)} 組，含超過寬度的值）", fail)

            cases = V["imm"]
            out, why = ask([f"I {c['insn']:08x}" for c in cases])
            for k, name in ((1, "imm_s"), (2, "imm_b"), (3, "imm_j")):
                fail = why
                if out is not None:
                    for c, line in zip(cases, out):
                        g = int(line.split()[k])
                        if g != c["imms"][k]:
                            fail = f"insn 0x{c['insn']:08x}：{name} 得到 {g}，應該是 {c['imms'][k]}"
                            break
                S.item(not fail, 1, f"C {name}（{len(cases)} 組）", fail)

            cases = V["enc"]
            out, why = ask(["E " + " ".join(map(str, c["args"])) for c in cases])
            fail = why
            if out is not None:
                for c, line in zip(cases, out):
                    if int(line, 16) != c["insn"]:
                        fail = f"enc_b{tuple(c['args'])}：得到 0x{line.strip()}，應該是 0x{c['insn']:08x}"
                        break
            S.item(not fail, 2, f"C enc_b（{len(cases)} 組，含 ±4096 邊界）", fail)

        import pio_sim
        for name, pts in (("unpack8", 3), ("unpack12", 3)):
            path = os.path.join(d, "pio", name + ".pio")
            vec = V["pio"][name]
            try:
                rx, cyc = pio_sim.run(open(path, encoding="utf-8").read(), vec["words"])
                fail = ""
                if len(rx) != len(vec["expect"]):
                    fail = f"輸出 {len(rx)} 個 word，應該 {len(vec['expect'])} 個"
                for i, (g, x) in enumerate(zip(rx, vec["expect"])):
                    if g != x:
                        fail = f"RX[{i}] = 0x{g:08x}，應該是 0x{x:08x}" + (f"（{fail}）" if fail else "")
                        break
            except pio_sim.PioError as ex:
                fail, cyc = f"模擬器錯誤：{ex}", None
            label = "B-1 unpack8.pio 輸出正確" if name == "unpack8" else "B-2 unpack12.pio 輸出正確"
            S.item(not fail, pts, label, fail)
            if name == "unpack12":
                if not fail:
                    per = cyc / len(vec["expect"])
                    S.item(per <= 3.0, 2, "B-2 效能：平均每個樣本 ≤ 3 cycle", f"{per:.2f} cycle / 樣本")
                else:
                    S.item(False, 2, "B-2 效能（要先正確）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return S


# ---------------------------------------------------------------- 2-3
def judge_q2_3():
    S = Score("2-3（雙核心 / spinlock / DMA）", 20)
    bad = check_protected("q2-3/") + check_protected("judge/calib")
    if bad:
        S.item(False, 20, "不能改的檔案沒有被改", "被改過：" + "、".join(bad))
        return S
    d = os.path.join(ROOT, "q2-3")
    tmp = tempfile.mkdtemp(prefix="judge_q23_")
    srcs = [os.path.join(d, f) for f in ("main.c", "work.c", "pico_sim/pico_sim.c")]
    try:
        exe = os.path.join(tmp, "p")
        rc, o, e = sh(["cc", "-O2", "-std=c11", "-pthread", "-o", exe] + srcs)
        if rc != 0:
            S.item(False, 20, "編譯", tail(o + e))
            return S
        cal = os.path.join(tmp, "c")
        sh(["cc", "-O2", "-std=c11", "-pthread", "-I", d, "-o", cal, os.path.join(JUDGE, "calib.c"),
            os.path.join(d, "work.c"), os.path.join(d, "pico_sim", "pico_sim.c")])
        want = V["q2-3"]
        times, fail = [], ""
        for k in range(5):
            rc, o, e = sh([exe], timeout=20)
            if rc == "timeout":
                fail = f"第 {k + 1} 次執行超過 20 秒（死結？）"
                break
            if rc != 0:
                fail = f"第 {k + 1} 次執行結束碼 {rc}：{tail(o + e, 3)}"
                break
            m = re.search(r"RESULT packets=(\d+) bytes=(\d+) xor=0x([0-9a-fA-F]+)", o)
            t = re.search(r"TIME ms=([\d.]+)", o)
            if not m or not t:
                fail = f"第 {k + 1} 次沒有印出 RESULT / TIME：{tail(o, 3)}"
                break
            got = (int(m.group(1)), int(m.group(2)), int(m.group(3), 16))
            if got != (want["packets"], want["bytes"], want["xor"]):
                fail = (f"第 {k + 1} 次結果 packets={got[0]} bytes={got[1]} xor=0x{got[2]:08x}，"
                        f"應該是 packets={want['packets']} bytes={want['bytes']} xor=0x{want['xor']:08x}")
                break
            times.append(float(t.group(1)))
        S.item(not fail, 12, "結果正確（連跑 5 次都要對）", fail)

        tsan = os.path.join(tmp, "t")
        rc, o, e = sh(["cc", "-O1", "-g", "-std=c11", "-pthread", "-fsanitize=thread", "-o", tsan] + srcs)
        if rc != 0:
            S.lines.append("  [SKIP]  0/3  這台電腦不能用 ThreadSanitizer，這 3 分不計")
            S.total -= 3
        else:
            env = dict(os.environ, TSAN_OPTIONS="report_thread_leaks=0")
            rc, o, e = sh([tsan], timeout=120, env=env)
            races = (o + e).count("WARNING: ThreadSanitizer: data race")
            S.item(rc != "timeout" and races == 0 and "RESULT" in o, 3,
                   "ThreadSanitizer 沒有回報 data race（make tsan）",
                   "超時" if rc == "timeout" else f"{races} 個 data race 警告" if races else tail(o + e, 2))

        if not fail:
            rc, o, _ = sh([cal], timeout=30)
            m = re.search(r"SERIAL ms=([\d.]+)", o)
            serial = float(m.group(1)) if m else None
            med = statistics.median(times)
            if serial:
                S.note(f"你的時間（5 次中位數）{med:.1f} ms；單核心依序做完 {serial:.1f} ms；比例 {med / serial:.2f}")
                S.item(med <= 0.85 * serial, 2, "效能 1：≤ 單核心的 0.85 倍", f"{med / serial:.2f} 倍")
                S.item(med <= 0.65 * serial, 3, "效能 2：≤ 單核心的 0.65 倍", f"{med / serial:.2f} 倍")
            if (os.cpu_count() or 1) < 2:
                S.note("⚠ 這台電腦只有 1 顆 CPU，兩個「核心」無法真的同時跑，效能分拿不到是正常的")
        else:
            S.item(False, 5, "效能（結果要先正確）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return S


def main():
    want = [a for a in sys.argv[1:] if not a.startswith("-")] or ["q1", "q2-1", "q2-2", "q2-3"]
    table = {"q1": judge_q1, "q2-1": judge_q2_1, "q2-2": judge_q2_2, "q2-3": judge_q2_3}
    for w in want:
        if w not in table:
            raise SystemExit(f"不認得 {w}：可以用 {' '.join(table)}")
    results = [table[w]() for w in want]
    for r in results:
        r.show()
    got, total = sum(r.got for r in results), sum(r.total for r in results)
    print(f"\n總分：{got}/{total}（2-1 的 3 分自評不算在內）")


if __name__ == "__main__":
    main()
