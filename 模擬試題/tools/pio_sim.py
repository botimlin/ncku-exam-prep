#!/usr/bin/env python3
"""pio_sim.py — 模擬試題用的 PIO 狀態機模擬器（單一 SM，只模擬資料路徑）

用途：沒有板子也能驗證 .pio 程式「把 TX FIFO 的資料變成什麼 RX FIFO 的資料」，並數 cycle。

    python3 pio_sim.py 程式.pio 0x12345678 0xdeadbeef ...      # 直接給輸入 word
    python3 pio_sim.py 程式.pio --file words.txt                # 一行一個 word（十六進位或十進位）
    python3 pio_sim.py 程式.pio 0x12345678 --trace              # 每個 cycle 印出 X/Y/OSR/ISR

設定從 .pio 檔的 `% c-sdk { ... %}` 區塊讀（跟真的 pioasm 專案一樣寫在 init 函式裡）：
    sm_config_set_out_shift(&c, shift_right, autopull, pull_threshold);
    sm_config_set_in_shift (&c, shift_right, autopush, push_threshold);
沒寫的就用 SDK 預設值：兩邊都 shift_right=true、auto 關閉、threshold 32。

支援的指令：out、in、push、pull（含 iffull / ifempty / block / noblock）、set x|y、
mov（x y isr osr null，可加 ! 或 ~ 反相、:: 位元反轉）、jmp（!x x-- !y y-- x!=y !osre）、nop、
延遲 [n]、.wrap_target / .wrap、標籤。
不支援（遇到會報錯）：pins、side-set、wait、irq、exec、status。

模型（和 RP2350 datasheet 的 PIO 章節一致的部分）：
  - 啟動時 OSR 是「空」的（output shift count = 32），ISR 是空的（input shift count = 0）。
  - out：shift_right 時取 OSR 的低位元、OSR 右移；shift_left 時取高位元、OSR 左移。
    shift count 加 n，最多到 32；OSR 剩下的 bit 不夠時，不夠的部分是 0（資料不會自動跨 word 接起來）。
  - autopull：要執行 out 時如果 count >= pull_threshold，先從 TX FIFO 補一個 word（FIFO 空就 stall）。
  - in：shift_left 時 ISR 左移、新資料從低位元進來；shift_right 時 ISR 右移、新資料從高位元進來。
  - autopush：in 之後如果 count >= push_threshold，把 ISR 推進 RX FIFO，ISR 和 count 清 0。
  - TX FIFO 由 CPU 一直補滿（不會因為 CPU 慢而 stall），RX FIFO 由 CPU 一直讀走（不會滿）。
  - 輸入用完、狀態機 stall 在 pull / autopull 上，就結束。
  - cycle = 執行的指令數 + 延遲 [n]，不含最後那次 stall。
"""
import re
import sys

MASK32 = 0xFFFFFFFF


class PioError(Exception):
    pass


def _bits(n):
    return MASK32 if n >= 32 else (1 << n) - 1


def _rev32(v):
    return int(f"{v & MASK32:032b}"[::-1], 2)


def _parse_bool(s):
    s = s.strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    raise PioError(f"看不懂的布林值：{s}")


def _parse_int(s):
    return int(s.strip().rstrip("uU"), 0)


def parse_config(text):
    cfg = {"out_right": True, "autopull": False, "pull_thresh": 32,
           "in_right": True, "autopush": False, "push_thresh": 32}
    m = re.search(r"%\s*c-sdk\s*\{(.*?)%\}", text, re.S)
    if not m:
        return cfg
    body = re.sub(r"//[^\n]*", "", m.group(1))
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    for name, keys in (("sm_config_set_out_shift", ("out_right", "autopull", "pull_thresh")),
                       ("sm_config_set_in_shift", ("in_right", "autopush", "push_thresh"))):
        calls = re.findall(name + r"\s*\(([^)]*)\)", body)
        if len(calls) > 1:
            raise PioError(f"{name} 出現了 {len(calls)} 次，模擬器只接受一次")
        if calls:
            args = [a.strip() for a in calls[0].split(",")]
            if len(args) != 4:
                raise PioError(f"{name} 要 4 個參數：(&c, shift_right, auto, threshold)")
            cfg[keys[0]] = _parse_bool(args[1])
            cfg[keys[1]] = _parse_bool(args[2])
            th = _parse_int(args[3])
            if not 1 <= th <= 32:
                raise PioError(f"{name} 的 threshold 要是 1..32，收到 {th}")
            cfg[keys[2]] = th
    return cfg


def assemble(text):
    """回傳 (指令清單, wrap_target, wrap)。每個指令是 dict。"""
    m = re.search(r"%\s*c-sdk", text)
    src = text[:m.start()] if m else text
    lines = []
    for raw in src.splitlines():
        line = raw.split(";", 1)[0].split("//", 1)[0].strip()
        if line:
            lines.append(line)
    labels, prog = {}, []
    wrap_target, wrap = None, None
    seen_program = False
    for line in lines:
        if line.startswith("."):
            d = line.split()
            if d[0] == ".program":
                if seen_program:
                    raise PioError("一個檔案只能有一個 .program")
                seen_program = True
            elif d[0] == ".wrap_target":
                wrap_target = len(prog)
            elif d[0] == ".wrap":
                wrap = len(prog) - 1
            elif d[0] in (".side_set", ".origin", ".define", ".lang_opt", ".word", ".pio_version",
                          ".clock_div", ".fifo", ".mov_status", ".in", ".out", ".set"):
                raise PioError(f"模擬器不支援 {d[0]}")
            else:
                raise PioError(f"看不懂的指示：{line}")
            continue
        while True:
            lm = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.*)$", line)
            if not lm:
                break
            labels[lm.group(1)] = len(prog)
            line = lm.group(2).strip()
        if not line:
            continue
        delay = 0
        dm = re.search(r"\[\s*(\d+)\s*\]\s*$", line)
        if dm:
            delay = int(dm.group(1))
            line = line[:dm.start()].strip()
            if delay > 31:
                raise PioError(f"延遲最多 31：{line}")
        if re.search(r"\bside\b", line):
            raise PioError("模擬器不支援 side-set")
        prog.append({"text": line, "delay": delay})
    if not prog:
        raise PioError("沒有任何指令")
    if len(prog) > 32:
        raise PioError(f"PIO 指令記憶體只有 32 條，這個程式有 {len(prog)} 條")
    for ins in prog:
        ins.update(_decode(ins["text"], labels))
    if wrap_target is None:
        wrap_target = 0
    if wrap is None:
        wrap = len(prog) - 1
    return prog, wrap_target, wrap


def _decode(t, labels):
    parts = re.split(r"[\s,]+", t.strip())
    op = parts[0].lower()
    args = [p for p in parts[1:] if p]

    def count(s):
        n = _parse_int(s)
        if not 1 <= n <= 32:
            raise PioError(f"bit 數要 1..32：{t}")
        return n

    if op == "out":
        if len(args) != 2 or args[0] not in ("x", "y", "null", "isr", "osr"):
            raise PioError(f"模擬器的 out 只支援 x y null isr（不支援 pins 等）：{t}")
        if args[0] == "osr":
            raise PioError(f"out osr 沒有意義：{t}")
        return {"op": "out", "dst": args[0], "n": count(args[1])}
    if op == "in":
        if len(args) != 2 or args[0] not in ("x", "y", "null", "isr", "osr"):
            raise PioError(f"模擬器的 in 只支援 x y null isr osr（不支援 pins）：{t}")
        return {"op": "in", "src": args[0], "n": count(args[1])}
    if op in ("push", "pull"):
        flags = set(a.lower() for a in args)
        bad = flags - {"block", "noblock", "iffull", "ifempty"}
        if bad:
            raise PioError(f"看不懂 {op} 的選項 {bad}：{t}")
        if op == "push" and "ifempty" in flags or op == "pull" and "iffull" in flags:
            raise PioError(f"{op} 不能用這個選項：{t}")
        return {"op": op, "block": "noblock" not in flags,
                "cond": ("iffull" in flags) or ("ifempty" in flags)}
    if op == "set":
        if len(args) != 2 or args[0] not in ("x", "y"):
            raise PioError(f"模擬器的 set 只支援 x、y（不支援 pins、pindirs）：{t}")
        v = _parse_int(args[1])
        if not 0 <= v <= 31:
            raise PioError(f"set 的值只有 5 bit（0..31）：{t}")
        return {"op": "set", "dst": args[0], "v": v}
    if op == "nop":
        return {"op": "mov", "dst": "y", "src": "y", "inv": False, "rev": False}
    if op == "mov":
        m = re.match(r"^mov\s+(\w+)\s*,\s*([!~]|::)?\s*(\w+)\s*$", t.strip(), re.I)
        if not m:
            raise PioError(f"看不懂的 mov：{t}")
        dst, mod, src = m.group(1).lower(), m.group(2), m.group(3).lower()
        if dst not in ("x", "y", "isr", "osr") or src not in ("x", "y", "isr", "osr", "null"):
            raise PioError(f"模擬器的 mov 只支援 x y isr osr null：{t}")
        return {"op": "mov", "dst": dst, "src": src, "inv": mod in ("!", "~"), "rev": mod == "::"}
    if op == "jmp":
        if len(args) == 1:
            cond, target = "always", args[0]
        elif len(args) == 2:
            cond, target = args[0].lower(), args[1]
            if cond not in ("!x", "x--", "!y", "y--", "x!=y", "!osre"):
                raise PioError(f"模擬器不支援這個 jmp 條件（pin 不支援）：{t}")
        else:
            raise PioError(f"看不懂的 jmp：{t}")
        if target in labels:
            addr = labels[target]
        else:
            try:
                addr = _parse_int(target)
            except ValueError:
                raise PioError(f"找不到標籤 {target}：{t}")
        return {"op": "jmp", "cond": cond, "addr": addr}
    raise PioError(f"模擬器不支援的指令：{t}")


class Stall(Exception):
    pass


def run(text, words, max_cycles=5_000_000, trace=False):
    """回傳 (rx_words, cycles)。"""
    cfg = parse_config(text)
    prog, wrap_target, wrap = assemble(text)
    tx = list(words)
    ti = 0
    rx = []
    x = y = 0
    osr, osr_cnt = 0, 32
    isr, isr_cnt = 0, 0
    pc = 0
    cycles = 0

    def tx_pop():
        nonlocal ti
        if ti >= len(tx):
            raise Stall()
        v = tx[ti] & MASK32
        ti += 1
        return v

    def do_push():
        nonlocal isr, isr_cnt
        rx.append(isr & MASK32)
        isr, isr_cnt = 0, 0

    def shift_in(data, n):
        nonlocal isr, isr_cnt
        data &= _bits(n)
        if n == 32:
            isr = data
        elif cfg["in_right"]:
            isr = ((isr >> n) | (data << (32 - n))) & MASK32
        else:
            isr = ((isr << n) | data) & MASK32
        isr_cnt = min(32, isr_cnt + n)

    try:
        while True:
            if cycles > max_cycles:
                raise PioError(f"超過 {max_cycles} cycle 還沒結束（無窮迴圈？）")
            ins = prog[pc]
            op = ins["op"]
            nxt = wrap_target if pc == wrap else pc + 1
            if op == "out":
                if cfg["autopull"] and osr_cnt >= cfg["pull_thresh"]:
                    osr, osr_cnt = tx_pop(), 0
                n = ins["n"]
                if cfg["out_right"]:
                    data = osr & _bits(n)
                    osr = 0 if n == 32 else (osr >> n)
                else:
                    data = (osr >> (32 - n)) & _bits(n)
                    osr = 0 if n == 32 else (osr << n) & MASK32
                osr_cnt = min(32, osr_cnt + n)
                d = ins["dst"]
                if d == "x":
                    x = data
                elif d == "y":
                    y = data
                elif d == "isr":
                    isr, isr_cnt = data, n
            elif op == "in":
                s = ins["src"]
                data = {"x": x, "y": y, "null": 0, "isr": isr, "osr": osr}[s]
                shift_in(data, ins["n"])
                if cfg["autopush"] and isr_cnt >= cfg["push_thresh"]:
                    do_push()
            elif op == "push":
                if not ins["cond"] or isr_cnt >= cfg["push_thresh"]:
                    do_push()
            elif op == "pull":
                if not ins["cond"] or osr_cnt >= cfg["pull_thresh"]:
                    if ti < len(tx):
                        osr, osr_cnt = tx_pop(), 0
                    elif ins["block"]:
                        raise Stall()
                    else:
                        osr, osr_cnt = x, 0
            elif op == "set":
                if ins["dst"] == "x":
                    x = ins["v"]
                else:
                    y = ins["v"]
            elif op == "mov":
                v = {"x": x, "y": y, "isr": isr, "osr": osr, "null": 0}[ins["src"]]
                if ins["inv"]:
                    v = ~v & MASK32
                if ins["rev"]:
                    v = _rev32(v)
                d = ins["dst"]
                if d == "x":
                    x = v
                elif d == "y":
                    y = v
                elif d == "isr":
                    isr, isr_cnt = v, 0
                elif d == "osr":
                    osr, osr_cnt = v, 0
            elif op == "jmp":
                c = ins["cond"]
                take = False
                if c == "always":
                    take = True
                elif c == "!x":
                    take = x == 0
                elif c == "!y":
                    take = y == 0
                elif c == "x--":
                    take = x != 0
                    x = (x - 1) & MASK32
                elif c == "y--":
                    take = y != 0
                    y = (y - 1) & MASK32
                elif c == "x!=y":
                    take = x != y
                elif c == "!osre":
                    take = osr_cnt < cfg["pull_thresh"]
                if take:
                    nxt = ins["addr"]
            cycles += 1 + ins["delay"]
            if trace:
                print(f"{cycles:6d} pc={pc:2d} {ins['text']:<18} X={x:08x} Y={y:08x} "
                      f"OSR={osr:08x}({osr_cnt:2d}) ISR={isr:08x}({isr_cnt:2d}) RX={len(rx)}")
            pc = nxt
    except Stall:
        pass
    return rx, cycles


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = argv[1]
    rest = argv[2:]
    trace = "--trace" in rest
    rest = [a for a in rest if a != "--trace"]
    words = []
    if rest and rest[0] == "--file":
        with open(rest[1]) as f:
            words = [_parse_int(l) for l in f if l.strip()]
    else:
        words = [_parse_int(a) for a in rest]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        cfg = parse_config(text)
        rx, cycles = run(text, words, trace=trace)
    except PioError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1
    print(f"設定：out_shift {'right' if cfg['out_right'] else 'left'} autopull={int(cfg['autopull'])} "
          f"thresh={cfg['pull_thresh']}；in_shift {'right' if cfg['in_right'] else 'left'} "
          f"autopush={int(cfg['autopush'])} thresh={cfg['push_thresh']}")
    print(f"輸入 {len(words)} 個 word，輸出 {len(rx)} 個 word，{cycles} cycles")
    for i, v in enumerate(rx):
        print(f"  RX[{i}] = 0x{v:08x}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
