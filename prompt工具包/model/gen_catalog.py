#!/usr/bin/env python3
"""從卡片標題自動產生 01-資源目錄.md（給模型看的卡片名稱清單）。

用法（在 prompt工具包/ 執行）：  python3 model/gen_catalog.py
卡片有增減、改標題後重跑一次。每張目錄卡 ≤ 1200 字元，放不下就自動拆成下一張。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent       # prompt工具包/
OUT = ROOT / "model" / "01-資源目錄.md"
BUDGET = 1200
TOPIC_MAX = 20                                               # 每張卡的主題最多取幾個字

# (群組標題, [(顯示名稱, 檔案)])；顯示名稱 = 模型在【需要】裡要寫的前綴
GROUPS = [
    ("規格卡：預製範本（ROS、PICO、UROS）", [
        ("規格卡 ROS", "model/spec-ros2.md"), ("規格卡 PICO", "model/spec-pico.md"),
        ("規格卡 UROS", "model/spec-micro-ros.md")]),
    ("規格卡：預製範本（ALGO、BITS、PERF）", [
        ("規格卡 ALGO", "model/spec-algo.md"), ("規格卡 BITS", "model/spec-bits-riscv.md"),
        ("規格卡 PERF", "model/spec-linux-perf.md")]),
    ("參考卡：RP2350 硬體與 pico-sdk", [
        ("", "cards/pico-sdk.md"), ("", "cards/pico-dma.md"), ("", "cards/pio.md"),
        ("", "cards/multicore-sync.md"), ("", "cards/riscv-hazard3.md"),
        ("", "cards/arm-cortex-m33.md"), ("", "cards/pico-peripherals.md"), ("", "cards/08-docs-map.md")]),
    ("參考卡：ROS 2、通訊、演算法、效能、環境", [
        ("", "cards/ros2.md"), ("", "cards/host-mcu-comm.md"), ("", "cards/algorithms-ds.md"),
        ("", "cards/c-linux-perf.md"), ("", "cards/python-perf.md"), ("", "cards/parallel-distributed.md"),
        ("", "cards/git-env.md"), ("", "cards/control-dsp.md"), ("", "cards/freertos.md")]),
    ("提示卡：固定流程（我貼給你後照格式做）", [
        ("", f"cards/{n}") for n in ("10-exam-day-flow.md", "02-read-spec.md", "05-cmake-build.md",
                                    "06-tools-debug.md", "04-debug.md", "03-optimize.md", "09-template-adapt.md",
                                    "11-ask-reference.md", "12-implement.md", "13-verify-submit.md",
                                    "07-unknown-tech.md")]),
]
TITLE = re.compile(r"^【([^｜】]+)｜([^｜】]+)｜([^】]+)】", re.M)


def cards_in(path, topic_max=TOPIC_MAX):
    text = (ROOT / path).read_text(encoding="utf-8")
    out = []
    for kind, name, topic in TITLE.findall(text):
        topic = re.sub(r"\s+", " ", topic.split("】")[0]).strip()
        out.append((kind.strip(), name.strip(), topic[:topic_max] + ("…" if len(topic) > topic_max else "")))
    return out


def group_lines(entries):
    """把同一系列（例如 RP2350 DMA 1/8～8/8）壓成一行：系列名（n 張）：1 主題｜2 主題…"""
    lines = []
    for prefix, path in entries:
        if not (ROOT / path).exists():
            lines.append(f"- （{path} 還沒有）")
            continue
        series = {}
        for kind, name, topic in cards_in(path, 34 if path.startswith("model/") else TOPIC_MAX):
            m = re.match(r"(.+?)\s*(\d+)/(\d+)$", name)
            base, num = (m.group(1), m.group(2)) if m else (name, "")
            label = prefix or f"{kind} {base}"
            series.setdefault(label, []).append(f"{num} {topic}".strip())
        for label, items in series.items():
            lines.append(f"- {label}（{len(items)} 張）：" + "｜".join(items))
    return lines


def main():
    head = ("# 目錄卡：我手上所有卡片的名稱（給模型看）\n"
            "> 用法：模型說「【需要】目錄 n」時貼第 n 張。由 `model/gen_catalog.py` 從卡片標題自動產生；卡片改了就重跑。"
            "每張 ≤ 1200 字元。\n> 模型要卡片時寫「【需要】<系列名> <號碼>」，例：「規格卡 ROS 2」「參考卡 RP2350 DMA 2/8」"
            "「提示卡 建置 2/7」。操作者照 `model/README.md` 的對照表找到檔案，複製那一張。\n")
    raw = []                                  # (群組標題, 行)
    for title, entries in GROUPS:
        for line in group_lines(entries):
            raw.append((title, line))
    # 依預算切卡：同一群組盡量放同一張，放不下就開新卡
    cards, cur, cur_title = [], [], None
    intro = "以下是我手上的卡片名稱。要哪張就寫「【需要】系列名 號碼」（號碼寫「2」或「2/8」都可以）。\n"
    def size(title, lines):
        return len(f"【目錄｜99/99｜{title}】\n") + len(intro) + sum(len(l) + 1 for l in lines)
    for title, line in raw:
        if cur and (title != cur_title or size(cur_title, cur + [line]) > BUDGET):
            cards.append((cur_title, cur)); cur = []
        cur_title = title
        while size(title, [line]) > BUDGET:     # 單行太長就截斷主題
            line = line[:-10] + "…"
        cur.append(line)
    if cur:
        cards.append((cur_title, cur))
    n = len(cards)
    body = []
    for i, (title, lines) in enumerate(cards, 1):
        body.append(f"【目錄｜{i}/{n}｜{title}】\n{intro}" + "\n".join(lines))
    OUT.write_text(head + "\n---\n\n" + "\n\n---\n\n".join(body) + "\n", encoding="utf-8")
    for i, (title, lines) in enumerate(cards, 1):
        print(f"目錄 {i}/{n}  {title}  ({len(body[i-1])} 字元)")


if __name__ == "__main__":
    main()
