#!/usr/bin/env python3
"""產生 judge 的隱藏測資（模擬試題/judge/vectors.json）。出題用，考生不用跑。
參考實作故意用 Python 另外寫一份（不重用 C 解答），兩邊互相驗證。"""
import hashlib, json, os, random, struct, zlib

random.seed(20261114)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "模擬試題", "judge", "vectors.json")


def crc16(b):
    c = 0xFFFF
    for x in b:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def build(ver, typ, ln, seq, flags):
    bits = f"{ver & 7:03b}{typ & 31:05b}{ln & 0xFFF:012b}{seq & 0x3FF:010b}{flags & 3:02b}"
    b = list(int(bits[i:i + 8], 2).to_bytes(1, "big")[0] for i in range(0, 32, 8))
    c = crc16(b)
    return b + [c & 0xFF, c >> 8]


def parse(b):
    bits = "".join(f"{x:08b}" for x in b[:4])
    f = [int(bits[0:3], 2), int(bits[3:8], 2), int(bits[8:20], 2), int(bits[20:30], 2), int(bits[30:32], 2)]
    if b[4] | b[5] << 8 != crc16(b[:4]):
        return -1, f
    if f[0] != 5:
        return -2, f
    return 0, f


def sx(v, bits):
    return v - (1 << bits) if v >> (bits - 1) & 1 else v


def bit(x, i):
    return (x >> i) & 1


def imm_b(x):
    v = bit(x, 31) << 12 | bit(x, 7) << 11 | ((x >> 25) & 0x3F) << 5 | ((x >> 8) & 0xF) << 1
    return sx(v, 13)


def imm_j(x):
    v = bit(x, 31) << 20 | ((x >> 12) & 0xFF) << 12 | bit(x, 20) << 11 | ((x >> 21) & 0x3FF) << 1
    return sx(v, 21)


def imms(x):
    return [sx(x >> 20, 12), sx(((x >> 25) << 5) | ((x >> 7) & 0x1F), 12), imm_b(x), imm_j(x)]


def enc_b(f3, rs1, rs2, off):
    i = off & 0x1FFF
    return (bit(i, 12) << 31 | ((i >> 5) & 0x3F) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 |
            ((i >> 1) & 0xF) << 8 | bit(i, 11) << 7 | 0x63)


def pack12(samples):
    acc = 0
    for i, v in enumerate(samples):
        acc |= v << (12 * i)
    return [(acc >> (32 * k)) & 0xFFFFFFFF for k in range(len(samples) * 12 // 32)]


def main():
    parse_cases, build_cases = [], []
    edge = [(5, 0, 0, 0, 0), (5, 31, 0xFFF, 0x3FF, 3), (5, 0x10, 0x800, 0x200, 2), (5, 1, 1, 1, 1)]
    for f in edge + [(5, random.randrange(32), random.randrange(4096), random.randrange(1024),
                      random.randrange(4)) for _ in range(60)]:
        b = build(*f)
        parse_cases.append({"bytes": b, "ret": 0, "fields": list(f)})
    for _ in range(15):    # 版本錯、CRC 對
        f = (random.choice([0, 1, 2, 3, 4, 6, 7]), random.randrange(32), random.randrange(4096),
             random.randrange(1024), random.randrange(4))
        parse_cases.append({"bytes": build(*f), "ret": -2, "fields": None})
    for _ in range(15):    # CRC 錯（含版本也錯的）
        f = (random.choice([5, 5, 5, 2]), random.randrange(32), random.randrange(4096),
             random.randrange(1024), random.randrange(4))
        b = build(*f)
        b[random.randrange(6)] ^= 1 << random.randrange(8)
        r, _ = parse(b)
        parse_cases.append({"bytes": b, "ret": r, "fields": None})
    for c in parse_cases:  # 自我檢查
        r, f = parse(c["bytes"])
        assert r == c["ret"] and (c["fields"] is None or f == c["fields"])
    for _ in range(40):
        f = [random.randrange(8), random.randrange(32), random.randrange(4096), random.randrange(1024),
             random.randrange(4)]
        build_cases.append({"fields": f, "bytes": build(*f)})
    for f in ([5, 40, 0x1234, 0x7FF, 7], [9, 255, 0xFFFF, 0xFFFF, 255]):   # 超過寬度 → 只取低位元
        build_cases.append({"fields": f, "bytes": build(*f)})

    imm_cases = [{"insn": x, "imms": imms(x)} for x in
                 [0xfe059ce3, 0x0080006f, 0x10a02023, 0xfff00513, 0x80000063, 0x7e000fe3, 0x800000ef,
                  0x7ffff06f, 0xfffff06f, 0x00000013] + [random.getrandbits(32) for _ in range(100)]]
    enc_cases = []
    for off in [-4096, 4094, -2, 2, 0, -8, 2048, -2048, 2046]:
        enc_cases.append([random.randrange(8), random.randrange(32), random.randrange(32), off])
    for _ in range(60):
        enc_cases.append([random.randrange(8), random.randrange(32), random.randrange(32),
                          random.randrange(-2048, 2047) * 2])
    enc_cases = [{"args": a, "insn": enc_b(*a)} for a in enc_cases]
    for c in enc_cases:
        assert imm_b(c["insn"]) == c["args"][3]

    words8 = [random.getrandbits(32) for _ in range(64)] + [0, 0xFFFFFFFF, 0x80000001]
    exp8 = [(w >> (8 * k)) & 0xFF for w in words8 for k in range(4)]
    s12 = [random.randrange(4096) for _ in range(8 * 60)] + [0xFFF, 0, 0x800, 1, 0xABC, 0x123, 0xFFF, 0xFFF]
    pio = {"unpack8": {"words": words8, "expect": exp8},
           "unpack12": {"words": pack12(s12), "expect": s12}}

    # 2-3：用 Python 重算 work.c 的資料產生器，得到正確答案
    M = 0xFFFFFFFF
    xor_acc, nbytes = 0, 0
    for idx in range(3000):
        st = [(idx * 2654435761 + 12345) & M]

        def nxt():
            v = st[0]
            v ^= (v << 13) & M
            v ^= v >> 17
            v ^= (v << 5) & M
            st[0] = v
            return v
        n = 16 + nxt() % 49
        words = [nxt() for _ in range(n)]
        xor_acc ^= zlib.crc32(struct.pack(f"<{n}I", *words))
        nbytes += 4 * n
    q23 = {"packets": 3000, "bytes": nbytes, "xor": xor_acc}

    # 不能改的檔案：存 sha256，judge 會檢查
    root = os.path.join(HERE, "..", "模擬試題")
    protected = {}
    for rel in ["q1/device/pico_shim.c", "q1/device/pico_shim.h", "q1/device/compute.c", "q1/device/compute.h",
                "q1/host/link.py", "q2-1/monitor_node.py", "q2-2/packet.h", "q2-2/rv_imm.h",
                "q2-3/work.c", "q2-3/work.h", "q2-3/pico_sim/pico_sim.c", "q2-3/pico_sim/pico_sim.h",
                "tools/pio_sim.py", "judge/q2_2_harness.c", "judge/calib.c"]:
        with open(os.path.join(root, rel), "rb") as f:
            protected[rel] = hashlib.sha256(f.read()).hexdigest()

    with open(OUT, "w") as f:
        json.dump({"parse": parse_cases, "build": build_cases, "imm": imm_cases, "enc": enc_cases,
                   "pio": pio, "q2-3": q23, "protected": protected}, f)
    print(f"寫入 {os.path.relpath(OUT)}：parse {len(parse_cases)}、build {len(build_cases)}、"
          f"imm {len(imm_cases)}、enc {len(enc_cases)}；q2-3 xor=0x{xor_acc:08x}")


if __name__ == "__main__":
    main()
