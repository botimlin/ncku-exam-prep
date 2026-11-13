#!/usr/bin/env python3
"""從卡片標題自動產生 01-資源目錄.md（給模型看的卡片名稱清單），
再把給模型看的檔案合成一份 print/05-給模型的說明書.md（給 local model 一次載入用）。

用法（在 prompt工具包/ 執行）：  python3 model/gen_catalog.py
卡片有增減、改標題後重跑一次。每張目錄卡 ≤ 1200 字元，放不下就自動拆成下一張。
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import card_index  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent       # prompt工具包/
OUT = ROOT / "model" / "01-資源目錄.md"
ALL = ROOT / "print" / "05-給模型的說明書.md"
ARS = ROOT / "print" / "06-軍火庫.md"
ARS_PARTS = ["arsenal/recipes-optimize.md", "arsenal/api-pico.md", "arsenal/api-sync-ros.md",
             "arsenal/snippets-pico.md", "arsenal/snippets-host.md"]
ARS_HEAD = """# 軍火庫（合併版，給 local model 一次載入）

> 這份是 `prompt工具包/arsenal/` 的卡片合成的一份（`model/gen_catalog.py` 自動產生，不要手改）。整份約 {n} 字元。
> 用法：和 `05-給模型的說明書.md` 一起放進 local model 的 system prompt 或知識檔；context 放不下就只放需要的那一區，或改用單張卡片一次貼一張。
> 操作者說明在 `arsenal/README.md`（沒有放進這份）。

## 給模型：怎麼用軍火庫

- **函式名、參數順序、列舉值、常數、數字一律照這裡抄**，不要憑記憶。這裡沒有的，標【推測】並跟操作者要官方 header 那一行。
- 要寫程式：先找「片段卡」，照抄，只換 `<尖括號>` 的值；呼叫的每個 API 都要能在「API 卡」找到同樣的簽名。
- 要優化：先看「食譜卡 優化 0」選食譜編號，再照那張食譜的「修改後」改；改完附驗證指令和量測指令。
- 引用時寫卡片名稱（例：「API卡 DMA 2/4」）當證據。

"""
ALL_PARTS = ["model/00-總說明.md", "model/02-要資料.md", "model/01-資源目錄.md", "model/spec-ros2.md",
             "model/spec-pico.md", "model/spec-micro-ros.md", "model/spec-algo.md",
             "model/spec-bits-riscv.md", "model/spec-linux-perf.md"]
ALL_HEAD = """# 給模型的說明書（合併版，給 local model 一次載入）

> 這份是 `prompt工具包/model/` 給模型看的檔案合成的一份（`model/gen_catalog.py` 自動產生，不要手改）。
> 用法：放進 local model 的 system prompt 或知識檔。整份約 {n} 字元；context 放不下時改用 `model/` 的單張卡片，一次貼一張。
> 操作者說明在 `model/README.md`（沒有放進這份）。

## 給模型：整份都在你的 context 裡時

- 規格卡、目錄、資料代號你都已經看得到，**不用再跟操作者要卡片**；直接引用卡片名稱（例：「規格卡 PICO 6/13」）當證據。
- 還是要跟操作者要的：程式碼本身（`【要資料】程式 檔名 起-迄`）、考場的資料（`【要資料】B1` 這類代號）、指令輸出（`【要資料】指令 …`）。
- 每次最多要 2 樣；資料夠了就直接回答，缺的標【推測】。
- 規格卡的行號是考前版本；操作者在考場改過的檔案，行號以操作者貼的為準。

"""
BUDGET = 1200
TOPIC_MAX = 20                                               # 每張卡的主題最多取幾個字

# (群組標題, [(顯示名稱, 檔案)])；顯示名稱 = 模型在【要卡】裡要寫的前綴
GROUPS = [
    ("規格卡：預製範本（ROS、PICO、UROS）", [
        ("規格卡 ROS", "model/spec-ros2.md"), ("規格卡 PICO", "model/spec-pico.md"),
        ("規格卡 UROS", "model/spec-micro-ros.md")]),
    ("規格卡：預製範本（ALGO、BITS、PERF）", [
        ("規格卡 ALGO", "model/spec-algo.md"), ("規格卡 BITS", "model/spec-bits-riscv.md"),
        ("規格卡 PERF", "model/spec-linux-perf.md")]),
    ("軍火庫：API 卡（照抄的函式簽名、參數順序、列舉值）", [
        ("", "arsenal/api-pico.md"), ("", "arsenal/api-sync-ros.md")]),
    ("軍火庫：片段卡（照抄的程式，只換 <> 的值）", [
        ("", "arsenal/snippets-pico.md"), ("", "arsenal/snippets-host.md")]),
    ("軍火庫：優化食譜卡（先看 0 號選哪個）、套用卡", [
        ("", "arsenal/recipes-optimize.md")]),
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
        for kind, name, topic in cards_in(path, 34 if path.startswith(("model/", "arsenal/")) else TOPIC_MAX):
            m = re.match(r"(.+?)\s*(\d+)/(\d+)$", name)
            base, num = (m.group(1), m.group(2)) if m else (name, "")
            code = card_index.code_of(kind, base.strip())
            label = f"{code} {kind} {base}" if code else (prefix or f"{kind} {base}")
            series.setdefault(label, []).append(f"{int(num):02d} {topic}" if num else topic)
        for label, items in series.items():
            lines.append(f"- {label}（{len(items)} 張）：" + "｜".join(items))
    return lines


def main():
    head = ("# 目錄卡：我手上所有卡片的名稱（給模型看）\n"
            "> 用法：模型說「【要卡】目錄 n」時貼第 n 張。由 `model/gen_catalog.py` 從卡片標題自動產生；卡片改了就重跑。"
            "每張 ≤ 1200 字元。\n> 模型要卡片時寫「【要卡】編號」，例：「E01-02」「L02-02」「Q03-02」。"
            "操作者到 `編號卡/` 對應的查找檔 Ctrl-F 那個編號，複製下面那張。\n")
    raw = []                                  # (群組標題, 行)
    for title, entries in GROUPS:
        for line in group_lines(entries):
            raw.append((title, line))
    # 依預算切卡：同一群組盡量放同一張，放不下就開新卡
    cards, cur, cur_title = [], [], None
    intro = "以下是我手上的卡片。要哪張就寫「【要卡】編號」：編號＝系列代號-兩位數號碼，例：L02-02＝參考卡 RP2350 DMA 第 02 張。\n"
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
    update_tool_list(cards)
    write_lookup()
    parts = []
    for rel in ALL_PARTS:
        text = with_ids((ROOT / rel).read_text(encoding="utf-8").strip())
        text = re.sub(r"^# ", "## ", text, count=1)        # 每個檔案的標題降一級
        parts.append(f"<!-- 來源：{rel} -->\n{text}")
    joined = "\n\n---\n\n".join(parts) + "\n"
    aparts = []
    for rel in ARS_PARTS:
        if (ROOT / rel).exists():
            text = re.sub(r"^# ", "## ", with_ids((ROOT / rel).read_text(encoding="utf-8").strip()), count=1)
            aparts.append(f"<!-- 來源：{rel} -->\n{text}")
    if aparts:
        ajoined = "\n\n---\n\n".join(aparts) + "\n"
        ARS.write_text(ARS_HEAD.format(n=f"{len(ajoined) // 1000 * 1000:,}") + ajoined, encoding="utf-8")
        print(f"{ARS.relative_to(ROOT)}  ({len(ARS.read_text(encoding='utf-8')):,} 字元)")
    ALL.write_text(ALL_HEAD.format(n=f"{len(joined) // 1000 * 1000:,}") + joined, encoding="utf-8")
    print(f"{ALL.relative_to(ROOT)}  ({len(ALL.read_text(encoding='utf-8')):,} 字元)")


def with_ids(text):
    """合併版給 local model：每張卡標題前加一行「編號：L02-02」，模型才能用編號要卡。"""
    out = []
    for line in text.split("\n"):
        cid = card_index.id_by_title_line(line) if line.startswith("【") else None
        if cid:
            out.append(f"編號：{cid}")
        out.append(line)
    return "\n".join(out)


def update_tool_list(catalog_cards):
    """總說明 2/3 最後一行：目錄頁碼（M01-xx）會隨卡片增減變動，這裡自動重寫。"""
    pages = {}
    for i, (title, _) in enumerate(catalog_cards, 1):
        key = "規格卡" if title.startswith("規格卡") else "API / 片段 / 食譜" if title.startswith("軍火庫") \
            else "參考卡" if title.startswith("參考卡") else "提示卡"
        pages.setdefault(key, []).append(i)
    span = lambda ns: f"M01-{ns[0]:02d}" + (f"～{ns[-1]:02d}" if len(ns) > 1 else "")
    line = "每個系列有哪幾號、主題是什麼：目錄 " + "、".join(f"{span(v)} {k}" for k, v in pages.items()) + "。"
    p = ROOT / "model" / "00-總說明.md"
    s = p.read_text(encoding="utf-8")
    s2 = re.sub(r"^每個系列有哪幾號、主題是什麼：.*$", line, s, count=1, flags=re.M)
    if s2 == s and line not in s:
        raise SystemExit("00-總說明.md 找不到「每個系列有哪幾號、主題是什麼：」那一行")
    p.write_text(s2, encoding="utf-8")


LOOKUP = ROOT / "編號卡"
LOOKUP_FILES = [  # (檔名, 標題, 包含的字母)
    ("1-G開頭_H要資料_M目錄_E規格卡.md", "開頭、要資料、目錄、規格卡", "GHME"),
    ("2-A_API卡_C片段卡_F食譜卡.md", "軍火庫：API 卡、片段卡、食譜卡", "ACF"),
    ("3-Q提示卡.md", "提示卡（固定流程）", "Q"),
    ("4-L參考卡.md", "參考卡（硬體 / 軟體事實）", "L"),
]
LOOKUP_HEAD = """# {title}

> 由 `model/gen_catalog.py` 自動產生，不要手改（改原始卡片後重跑）。
> 用法：**Ctrl-F 編號**（例 `{ex}`）→ 跳到「## 編號」那一行 → 複製下面那張卡（從【 到下一條 --- 之前）。
> 模型寫 `【要卡】編號` 時來這裡找；看不清楚就開 GitHub 的 Raw 檢視再 Ctrl-F。全部編號一覽：`00-編號總表.md`。
> 包法：卡片包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡，最後一行寫「繼續」；**提示卡（Q、G02）直接貼，不要包**。
"""


def write_lookup():
    idx = card_index.build_index()
    LOOKUP.mkdir(exist_ok=True)
    rows = ["# 編號總表（全部卡片）", "",
            "> 由 `model/gen_catalog.py` 自動產生。編號＝系列代號-兩位數號碼。字母：G 開頭｜H 要資料｜M 目錄｜E 規格卡｜"
            "A API卡｜C 片段卡｜F 食譜卡｜Q 提示卡｜L 參考卡。",
            "> 找卡：看編號的字母 → 開下表「查找檔」那一份 → Ctrl-F 編號。", "",
            "| 查找檔 | 字母 |", "|---|---|"]
    rows += [f"| `{f}` | {', '.join(letters)} |" for f, _, letters in LOOKUP_FILES]
    rows += ["", "| 編號 | 卡名 | 主題 | 原始檔 |", "|---|---|---|---|"]
    for c in idx:
        rows.append(f"| {c['id']} | {card_index.name_of(c)} | {c['topic']} | `{c['file']}` |")
    (LOOKUP / "00-編號總表.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    for fname, title, letters in LOOKUP_FILES:
        cs = [c for c in idx if c["id"][0] in letters]
        body = [LOOKUP_HEAD.format(title=title, ex=cs[0]["id"] if cs else "")]
        for c in cs:
            body.append(f"## {c['id']}\n\n{c['text']}")
        (LOOKUP / fname).write_text("\n\n---\n\n".join(body) + "\n", encoding="utf-8")
        size = len((LOOKUP / fname).read_bytes())
        print(f"編號卡/{fname}  {len(cs)} 張  {size // 1024} KB")


if __name__ == "__main__":
    main()
