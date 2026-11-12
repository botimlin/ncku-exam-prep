#!/usr/bin/env python3
"""analyze.py — 把一輪的 raw.jsonl 整理成「案例 × 模型」通過矩陣 + 每個案例最常失敗的檢查。

用法：python3 analyze.py out/r1            # 讀 out/r1/*/raw.jsonl
      python3 analyze.py out/r1 --show t5   # 另外印出案例 id 含 t5 的各模型回答
"""
import collections
import glob
import json
import os
import sys

run_dir = sys.argv[1]
show = sys.argv[sys.argv.index("--show") + 1] if "--show" in sys.argv else None
rows = []
for f in sorted(glob.glob(os.path.join(run_dir, "*", "raw.jsonl"))):
    if os.path.basename(os.path.dirname(f)).startswith("_"):
        continue
    rows += [json.loads(l) for l in open(f, encoding="utf-8")]
rows = [r for r in rows if r.get("status") in ("ok", "scored", None) or "passed" in r]
if "--rescore" in sys.argv:  # 用目前的 run.py 檢查規則重新評分（不用重跑模型）
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("runmod", os.path.join(here, "run.py"))
    R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
    cards, _ = R.parse_cards()
    cases = {c["id"]: c for c in R.load_cases(os.path.join(here, "cases", "*.yaml"))}
    for r in rows:
        c = cases.get(r["case"])
        if not c or r.get("response") is None:
            continue
        b = R.build_case(c, cards, variant=r.get("variant") or "card")
        res, ok = R.evaluate(c, r["response"], b)
        r["checks"], r["passed"] = res, ok
models = sorted({r["model"] for r in rows}, key=lambda m: [x for x in m.replace(":", " ").split()])
cases = sorted({r["case"] for r in rows})
by = collections.defaultdict(list)
for r in rows:
    by[(r["case"], r["model"])].append(r)

short = {m: m.replace("qwen2.5", "q2.5").replace("llama", "ll").replace("mistral-nemo", "nemo") for m in models}
print("| case | " + " | ".join(short[m] for m in models) + " | 通過率 |")
print("|---|" + "---|" * (len(models) + 1))
tot = collections.Counter()
for c in cases:
    cells, ok = [], 0
    for m in models:
        rs = by[(c, m)]
        p = sum(1 for r in rs if r.get("passed"))
        cells.append("✅" if rs and p == len(rs) else ("·" if not rs else ("❌" if p == 0 else f"{p}/{len(rs)}")))
        ok += p / len(rs) if rs else 0
        tot[m] += p / len(rs) if rs else 0
    print(f"| {c} | " + " | ".join(cells) + f" | {ok / len(models):.0%} |")
print("| **模型總分** | " + " | ".join(f"{tot[m] / len(cases):.0%}" for m in models) + " | |")

print("\n## 每個案例最常失敗的檢查（跨模型）")
for c in cases:
    cnt = collections.Counter()
    for m in models:
        for r in by[(c, m)]:
            for k in r.get("checks", []):
                if not k.get("passed") and not k.get("skipped"):
                    cnt[k["name"]] += 1
    if cnt:
        print(f"- {c}: " + ", ".join(f"{n}×{k}" for n, k in cnt.most_common(4)))

if show:
    for c in cases:
        if show not in c:
            continue
        for m in models:
            for r in by[(c, m)]:
                print(f"\n##### {c} / {m} / {'PASS' if r.get('passed') else 'FAIL'}")
                print((r.get("response") or "")[:700])
                for k in r.get("checks", []):
                    if not k.get("passed") and not k.get("skipped"):
                        print(f"   x {k['name']}: {k['detail'][:110]}")
