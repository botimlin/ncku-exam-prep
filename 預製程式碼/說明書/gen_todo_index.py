#!/usr/bin/env python3
"""重新產生 09-附錄.md 的「9.1 TODO(改這裡) 總表」。

用法（在 預製程式碼/ 執行）：
    python3 說明書/gen_todo_index.py
會改寫 說明書/09-附錄.md 裡 "## 9.1" 到 "## 9.2" 之間的內容。README.md 裡的說明文字不算。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPX = ROOT / "說明書" / "09-附錄.md"
MARK = "TODO(改這裡)"
ORDER = ["ros2", "pico", "micro-ros", "algo", "bits-riscv", "linux-perf", "tools"]
CHAPTER = {"ros2": 2, "pico": 3, "micro-ros": 4, "algo": 5, "bits-riscv": 6, "linux-perf": 7, "tools": 8}


def cell(s: str) -> str:
    s = s.strip().replace("|", "\\|")
    return s if len(s) <= 110 else s[:107] + "…"


def collect():
    rows = {d: [] for d in ORDER}
    for d in ORDER:
        for p in sorted((ROOT / d).rglob("*")):
            if not p.is_file() or p.name == "README.md" or p.suffix not in {
                    ".c", ".h", ".py", ".pio", ".S", ".md", ".txt", ".cmake"}:
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if MARK not in line:
                    continue
                code, _, note = line.partition(MARK)
                code = re.sub(r"(//|/\*|#|;)\s*$", "", code.rstrip()).rstrip()
                note = re.sub(r"^[：:\s]+|\s*\*/\s*$", "", note).strip()
                rows[d].append((str(p.relative_to(ROOT)), n, code.strip(), note))
    return rows


def render(rows) -> str:
    total = sum(len(v) for v in rows.values())
    out = [f"全部 {total} 處（不含 README 的說明文字）。由 `說明書/gen_todo_index.py` 從程式碼自動產生；"
           "程式改過之後重跑一次，行號才會對。", ""]
    out.append("| 資料夾 | 處數 | 詳細說明 |")
    out.append("|---|---|---|")
    for d in ORDER:
        out.append(f"| `{d}/` | {len(rows[d])} | 第 {CHAPTER[d]} 章 |")
    out.append("")
    for d in ORDER:
        if not rows[d]:
            continue
        out.append(f"### `{d}/`（{len(rows[d])} 處，見第 {CHAPTER[d]} 章）")
        out.append("")
        out.append("| 位置 | 那一行的程式 | 說明 |")
        out.append("|---|---|---|")
        for f, n, code, note in rows[d]:
            c = f"`{cell(code)}`" if code and code not in ('"""', "'''") else "（註解行）"
            out.append(f"| `{f}:{n}` | {c} | {cell(note) or '—'} |")
        out.append("")
    return "\n".join(out)


def main():
    text = APPX.read_text(encoding="utf-8")
    start = text.index("## 9.1")
    end = text.index("## 9.2")
    head_end = text.index("\n", start) + 1
    new = text[:head_end] + "\n" + render(collect()) + "\n" + text[end:]
    APPX.write_text(new, encoding="utf-8")
    print(f"updated {APPX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
