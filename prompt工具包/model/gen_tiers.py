#!/usr/bin/env python3
"""產生「分級版」：給不同 context 大小的 local model 一次載入的合併檔。

用法（在 prompt工具包/ 執行）：
    python3 model/gen_tiers.py                        # 用估算的 token 數
    TOKCOUNT=/path/count_tokens.js python3 model/gen_tiers.py  # 用真的 tokenizer（Qwen2.5、Gemma3、o200k 取最大；安裝方法見 model/count_tokens.js 開頭）

輸出：print/分級版/給模型_{4k,8k,16k,32k,64k}.md 和 print/分級版/README.md（各版實際 token 數）。
每一版的開頭都是同一套「給模型的導引」：先告訴它手上有什麼、還能跟操作者要什麼、怎麼要，
再照優先順序塞卡片，直到用完這一版的預算（context 的約 55%，剩下留給題目、程式和回答）。
"""
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import card_index  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent           # prompt工具包/
OUTDIR = ROOT / "print" / "分級版"
TIERS = [("4k", 4096, 2200), ("8k", 8192, 4500), ("16k", 16384, 9000), ("32k", 32768, 18000), ("64k", 65536, 36000)]
SOURCES = ["arsenal/recipes-optimize.md", "model/spec-ros2.md", "model/spec-pico.md", "model/spec-micro-ros.md",
           "model/spec-algo.md", "model/spec-bits-riscv.md", "model/spec-linux-perf.md", "arsenal/api-pico.md",
           "arsenal/api-sync-ros.md", "arsenal/snippets-pico.md", "arsenal/snippets-host.md"]
REF_SOURCES = ["cards/pico-dma.md", "cards/multicore-sync.md", "cards/pio.md", "cards/ros2.md", "cards/pico-sdk.md",
               "cards/host-mcu-comm.md", "cards/riscv-hazard3.md", "cards/algorithms-ds.md"]
TITLE = re.compile(r"^【([^｜】]+)｜([^｜】]+?)\s*(\d+)/(\d+)｜([^】]+)】", re.M)

# 優先順序：考題最可能用到、最容易幻覺的放前面（名稱 = 卡別 系列 號碼）
PRIORITY = """
食譜卡 優化 0
規格卡 ROS 1; 規格卡 PICO 1; 規格卡 UROS 1; 規格卡 ALGO 1; 規格卡 BITS 1; 規格卡 PERF 1; 提示卡 套用 1
規格卡 ROS 2; 規格卡 PICO 3; 規格卡 PICO 2
API卡 DMA 5; API卡 DMA 2; 片段卡 PICO-DMA 1; 食譜卡 優化 7
API卡 SYNC 1; API卡 SYNC 2; API卡 SYNC 3; 片段卡 PICO-MC 3; 片段卡 PICO-MC 2; 片段卡 PICO-MC 4; 食譜卡 優化 4; 食譜卡 優化 5
食譜卡 優化 1; 規格卡 ROS 4; 片段卡 HOST-SERIAL 1; 片段卡 HOST-SERIAL 2; 食譜卡 優化 2; 片段卡 HOST-MULTI 1; 片段卡 HOST-MULTI 2
API卡 SNIFF 2; 片段卡 PICO-SNIFF 1; 食譜卡 優化 9; 食譜卡 優化 8; 規格卡 ALGO 2; 規格卡 ALGO 3
規格卡 BITS 2; 規格卡 BITS 4; 規格卡 BITS 5; 規格卡 BITS 6; 片段卡 ALGO 5; 片段卡 ALGO 6
API卡 PIO 1; API卡 PIO 3; API卡 PIO 4; API卡 PIO 5; 片段卡 PICO-PIO 1; 片段卡 PICO-PIO 2; 規格卡 PICO 9
規格卡 PICO 4; 片段卡 PICO-SERIAL 1; 片段卡 PICO-SERIAL 2; 規格卡 PICO 5; 規格卡 PICO 6; 規格卡 PICO 7
API卡 DMA 1; API卡 DMA 3; API卡 DMA 6; API卡 SNIFF 1; 片段卡 PICO-DMA 2; 片段卡 PICO-DMA 3; 片段卡 PICO-DMAPIO 1; 片段卡 PICO-DMAPIO 2
API卡 PICO-IO 1; API卡 PICO-IO 2; API卡 PICO-IO 4; 片段卡 PICO-TIME 1; 規格卡 PICO 12; 規格卡 PICO 13
規格卡 ROS 7; 片段卡 HOST-ROS 1; 片段卡 HOST-ROS 2; API卡 HOST-PY 1; API卡 HOST-PY 2; 規格卡 ROS 8; 規格卡 ROS 10
規格卡 UROS 4; 規格卡 UROS 5; 規格卡 UROS 8; 規格卡 UROS 9; 食譜卡 優化 3; API卡 UROS 6; 片段卡 HOST-UROS 1; 片段卡 HOST-UROS 2; 片段卡 HOST-UROS 4
食譜卡 優化 10; 食譜卡 優化 11; 規格卡 ALGO 5; 片段卡 ALGO 1; 片段卡 ALGO 2; 規格卡 ALGO 8; 規格卡 ALGO 9
規格卡 BITS 7; 規格卡 BITS 8; 規格卡 BITS 3; 規格卡 BITS 9; 規格卡 BITS 11
食譜卡 優化 12; 食譜卡 優化 13; 食譜卡 優化 6; 片段卡 PERF 1; 片段卡 PERF 2; 片段卡 PERF 3; 片段卡 PERF 4; 規格卡 PERF 2; 規格卡 PERF 3
"""

# 1.2 用的系列說明（沒放進來的卡，讓模型知道裡面大概有什麼）
SERIES_DESC = {
    "食譜卡 優化": "0 依現象選食譜；1 序列埠批次、2 多板、3 micro-ROS、4 雙核 pipeline、5 縮小鎖、6 pthread、7 DMA 取代複製、8 CRC 查表、9 CRC 用 sniffer、10 radix 排序、11 多段合併、12 拿掉 printf、13 編譯選項 / 放 RAM、14 popcount",
    "提示卡 套用": "把食譜 / 片段套到操作者的程式（最小修改）",
    "規格卡 ROS": "ros2/ 範本：封包格式與 CRC、frame.py、serial_bridge、fake_pico、測速與多板、node 範本、CLI 除錯、自訂 msg、陷阱",
    "規格卡 PICO": "pico/ 範本：CMake、序列埠協定、指令分派、雙核鎖與 queue、DMA、sniffer CRC、DMA+PIO、PIO 程式、計時、陷阱",
    "規格卡 UROS": "micro-ros/ 範本：build 與 APP_SRC、agent、rclc 順序與大小上限、陣列計算、雙核、pingpong、host_driver、陷阱",
    "規格卡 ALGO": "algo/：CRC 函式與規格表、SHA-0/1/256、排序合併、BNN、校驗碼、放進 Pico、測試",
    "規格卡 BITS": "bits-riscv/：bitops 巨集、封包欄位、位元流、RV32 格式與立即值、編解碼與模擬器、組語、Hazard3",
    "規格卡 PERF": "linux-perf/：計時、pthread 8 種寫法、SPSC pipeline、改法、陷阱",
    "API卡 DMA": "pico-sdk DMA 完整簽名：claim、預設值、遞增與 DREQ、chain/ring、configure 與 count、start/wait、IRQ",
    "API卡 SNIFF": "DMA sniffer：函式、mode 值、zlib CRC32 組合",
    "API卡 PIO": "PIO：載入程式、claim SM、sm_config、shift/autopush/clkdiv、GPIO 與 init、FIFO 與 DREQ",
    "API卡 SYNC": "雙核與同步：launch、FIFO、queue_t、spinlock、critical_section、mutex、semaphore",
    "API卡 PICO-IO": "時間、stdio、GPIO、header → CMake 庫名",
    "API卡 UROS": "micro-ROS rclc：support/node、pub/sub、timer/executor、callback、transport、Int32MultiArray",
    "API卡 HOST-PY": "rclpy、QoS、pyserial、struct / array",
    "片段卡 PICO-DMA": "DMA 複製、填值、先不等、兩通道、claim 規矩", "片段卡 PICO-SNIFF": "sniffer 算 zlib CRC32、軟體對照",
    "片段卡 PICO-DMAPIO": "DMA 餵 PIO TX、收 RX", "片段卡 PICO-PIO": "載入 + 設定 SM、put/get、歸還",
    "片段卡 PICO-MC": "啟動 core1、FIFO 握手、queue pipeline、區域累加再合併、短臨界區",
    "片段卡 PICO-TIME": "量微秒與 cycle", "片段卡 PICO-SERIAL": "封包接收迴圈、加新指令",
    "片段卡 HOST-SERIAL": "開 port 送收、數字轉 bytes 批次、文字 vs 二進位", "片段卡 HOST-MULTI": "N 板平行、合併結果",
    "片段卡 HOST-ROS": "rclpy 節點、main、MultiArray 快速填、量 callback", "片段卡 HOST-UROS": "Pico 端陣列收算發、電腦端分派",
    "片段卡 ALGO": "CRC、排序合併、SHA、BNN、位元欄位、位元流", "片段卡 PERF": "pthread 區域累加、SPSC 佇列、計時",
}
REF_DESC = ("參考卡（硬體 / SDK / ROS 2 事實，每系列 4～8 張）：L01 RP2350 pico-sdk、L02 RP2350 DMA、L03 RP2350 PIO、"
            "L04 RP2350 週邊、L05 多核同步、L06 RISC-V Hazard3、L07 Cortex-M33、L08 ROS 2、L09 主機↔MCU、L10 演算法、"
            "L11 C/Linux 效能、L12 Python 效能、L13 平行、L14 git/環境、L15 控制DSP、L16 FreeRTOS、L17 官方文件導航、"
            "L19 CMake/colcon、L20 gdb 與板子、L21 症狀→原因、L22 瓶頸與量測；提示卡（固定流程）：Q03 建置、Q04 工具、Q05 除錯、"
            "Q06 優化、Q07 範本、Q09 實作、Q10 驗證、Q11 提交、Q12 速學、Q13 套用。號碼不確定就要「目錄 M01-01」。")

CODES_FULL = """| 代號 | 內容 |
|---|---|
| K1～K6 | 題目全文（分段）、出題 repo 檔案清單、.gitlab-ci.yml、README 段落、TODO/FIXME 清單、環境版本與 /dev/ttyACM* |
| B1～B4 | build 的第一個錯誤（前後 15 行）、CMakeLists.txt、CI 的 build 指令、colcon log |
| R1～R5 | 輸入 / 預期 / 實際、sanitizer 報告、當掉的 backtrace、Python traceback、卡住時各執行緒在哪 |
| T1～T7 | ros2 node list、node info、topic info -v、topic echo 一筆、topic hz、frame.py diff 結果、序列埠原始 bytes |
| P1～P6 | Pico 序列埠輸出、picotool info、LED 狀態、micro-ROS agent log、ros2 topic list、範本設定值 |
| S1～S4 | 各階段時間、CI 第一個錯誤與分數、git status 與 log、題目的效能要求 |"""
CODES_SHORT = ("K 開考（K1 題目、K3 CI 設定）｜B build（B1 第一個錯誤、B2 CMakeLists）｜R 執行錯誤（R1 輸入/預期/實際、R3 backtrace）｜"
               "T ROS 與序列埠（T1 node list、T3 topic info -v、T6 frame.py diff）｜P Pico / micro-ROS（P1 輸出、P4 agent log）｜"
               "S 效能與提交（S1 各階段時間、S2 CI log）")


def parse_cards(paths):
    cards = []
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for chunk in re.split(r"\n---\n", text):
            m = TITLE.search(chunk)
            if not m or not chunk.strip().startswith("【"):
                continue
            kind, series, num, total, topic = m.groups()
            cid = card_index.card_id(kind.strip(), series.strip(), int(num))
            cards.append({"key": f"{kind} {series.strip()} {int(num)}", "series": f"{kind} {series.strip()}",
                          "code": cid.split("-")[0], "id": cid,
                          "num": int(num), "topic": topic.strip(), "text": f"編號：{cid}\n" + chunk.strip(), "file": rel})
    return cards


def count_tokens(texts):
    js = os.environ.get("TOKCOUNT")
    if js and pathlib.Path(js).exists():
        out = subprocess.run(["node", js], input=json.dumps(texts), capture_output=True, text=True,
                             cwd=str(pathlib.Path(js).parent))
        if out.returncode == 0:
            return [r["max"] for r in json.loads(out.stdout)], "實測（Qwen2.5 / Gemma3 / o200k 取最大）"
    est = [round(1.5 * len(re.findall(r"[　-鿿＀-￯]", t)) + 0.35 * len(re.sub(r"[　-鿿＀-￯]", "", t))) for t in texts]
    return est, "估算（中日韓字 ×1.5、其他 ×0.35，偏保守）"


def ranges(nums):
    nums, out, i = sorted(nums), [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"{nums[i]:02d}" if i == j else f"{nums[i]:02d}～{nums[j]:02d}")
        i = j + 1
    return "、".join(out)


SERIES_ORDER = {}                                     # 系列的固定順序（照 SOURCES 檔案順序）；main() 填


def guide(tier, ctx, included, missing, compact):
    def by(cs):
        names = sorted(dict.fromkeys(c["series"] for c in cs), key=lambda s: SERIES_ORDER.get(s, 999))
        return {s: [c for c in cs if c["series"] == s] for s in names}
    inc_series = {c["series"] for c in included}
    missing = [c for c in missing if c["file"].startswith(("model/", "arsenal/"))]   # 參考卡用一行總述
    inc_lines = [f"- {cs[0]['code']} {s}：" + "｜".join(f"{c['id']} {c['topic'][:26]}" for c in sorted(cs, key=lambda c: c["num"]))
                 for s, cs in by(included).items()]
    miss_lines = []
    for s, cs in by(missing).items():
        if compact:
            miss_lines.append(f"{cs[0]['code']}-{ranges([c['num'] for c in cs])} {s}")
        elif s in inc_series:                              # 這個系列有一部分已經放進來：只列缺的那幾張
            miss_lines.append(f"- {cs[0]['code']} {s}：" + "｜".join(f"{c['id']} {c['topic'][:20]}" for c in sorted(cs, key=lambda c: c["num"])))
        else:
            miss_lines.append(f"- {cs[0]['code']}-{ranges([c['num'] for c in cs])} {s}：{SERIES_DESC.get(s, '')}")
    head = f"""# 給模型的工具箱（{tier} context 版）

Task (EN): You are my exam assistant. FIRST read section 1: what you already have here and what you can ask me for. Never guess function names, parameter order, enum values, constants or numbers — copy them from the cards. When something is missing, answer what you can first, then add at most 2 request lines (【要資料】 or 【要卡】) at the end. Answer in Traditional Chinese.

## 0. 先讀這段
- 你是我的上機考助教。硬體 Raspberry Pi Pico 2（RP2350，不是 RP2040）、pico-sdk 2.x、ROS 2 Jazzy；限時，Online Judge 評分，先交能動的版本再優化。
- 我是操作者：題目和所有檔案我看得到、你看不到；我只能貼文字給你。
- 這份文件是你的工具箱。**先看第 1 節，知道你手上有什麼、還能跟我要什麼**，再回答。
- 這一版放了 {len(included)} 張卡（第 5 節）；其他 {len(missing)} 張和我電腦上的程式、考場資料，要用【要卡】、【要資料】跟我要（第 2 節）。
"""
    sec1 = "\n## 1. 你拿得到什麼\n\n### 1.1 已經在這份文件裡（在第 5 節；引用編號當證據，不用再要）\n"
    sec1 += ("\n".join(inc_lines) if inc_lines else "- （這一版沒有放卡片，全部都要跟我要）") + "\n"
    sec1 += "\n### 1.2 沒放進來、可以跟我要的卡（寫編號＝系列代號-兩位數號碼，例 E02-06）\n"
    sec1 += ("、".join(miss_lines) if compact else "\n".join(miss_lines)) + "\n"
    if compact:
        sec1 += "\n另有參考卡 L01～L23（L01 pico-sdk、L02 DMA、L03 PIO、L05 多核同步、L06 RISC-V、L08 ROS 2、L09 主機↔MCU…）與提示卡 Q01～Q13：號碼不確定就要「目錄 M01-01」。\n"
    else:
        sec1 += f"- {REF_DESC}\n"
    sec1 += """
### 1.3 在我電腦上、我去拿的東西
- **預製範本程式**（考前寫好、測過）：`ros2/`（電腦端：封包、序列埠 bridge、多板、node 範本）、`pico/`（Pico C：序列埠協定、雙核、DMA、PIO、計時）、`micro-ros/`、`algo/`（CRC、SHA、排序、BNN）、`bits-riscv/`（位元欄位、RV32）、`linux-perf/`（pthread、pipeline）。要程式就寫檔名和行號範圍（規格卡上有函式的行號），一次 ≤ 60 行。
- **考場資料**：題目、出題 repo、錯誤訊息、指令輸出 → 用【要資料】加下面的代號要。
"""
    sec1 += ("\n### 1.4 資料代號（我照代號去跑指令再貼給你）\n" + (CODES_SHORT if compact else CODES_FULL) + "\n")
    sec2 = """
## 2. 我的訊息有四種、你怎麼跟我要
- ① 只有 <<<資料 開始>>>…<<<資料 結束>>>、沒有任務（卡片、題目片段）→ 只回「收到」，不分析、不要東西。
- ② 提示卡（有任務和輸出格式）→ 照格式回答。
- ③ 一般問題 → 精簡條列。
- ④ 資料區塊＋最後一行「繼續」＝你要的東西來了 → 用它接著做剛才的事。
缺東西：先答完，最後另起一行，最多 2 行。兩種都缺時先要資料。
【要資料】＝考場和我電腦上的東西（題目、程式幾行、指令輸出、代號）：
【要資料】K1｜為什麼
【要資料】程式 pico/app_dma.c 31-50｜為什麼（一次 ≤ 60 行）
【要資料】指令 ros2 topic info -v /number｜為什麼
【要卡】＝我工具包裡、第 5 節沒有的卡（寫編號）：
【要卡】E02-06｜為什麼
【要卡】A01-05｜為什麼
不知道號碼就寫系列代號＋要什麼（例「【要卡】L02｜要 count 單位」），或要「目錄 M01-01」。資料夠了就直接回答，不要一直要。
"""
    sec3 = """
## 3. 規則
1. 「資料」＝這份文件和這個對話裡我貼過的所有資料區塊。只根據資料；沒有就寫「資料中沒有」。
2. 互相矛盾時：題目原文 > 考場的 header、指令輸出 > 卡片 > 你的記憶。
3. 每個結論附證據：卡名或原文那一行；沒證據的標【推測】。
4. 函式名、參數順序、列舉值、常數、數字：照 API 卡、片段卡抄。卡上沒有的標【推測】，並跟我要那張卡或官方 header 那一行。
5. 寫程式先找片段卡照抄，只換 `<尖括號>` 的值；改我的程式只給最小修改：「檔名:行號 / 修改前 / 修改後」，附 1 行驗證指令和「成功的樣子」；優化還要附量測指令。
"""
    sec4 = """
## 4. 狀況 → 先要什麼（資＝【要資料】，卡＝【要卡】）
- 剛開考：資 K1、K3 → 對照規格卡總覽（E01-01～E06-01）找最像的範本。
- 題目和範本像：卡 那一區的規格卡 → 資 程式那幾行 → 照規則 5 改。
- 要寫 pico-sdk / rclc / rclpy 程式：卡 片段卡 + API 卡，照抄。
- 要優化：資 S1、S4 → 卡 F01-00 選食譜 → 卡 那張食譜 → 照「修改後」改（Q13-01）。
- build 錯誤：資 B1、B2。當掉 / 結果錯 / 卡住：資 R1，再 R2、R3。ROS 收不到：資 T1、T3。封包錯：資 T6、T7。micro-ROS：資 P4、P5。交卷前：資 S3、S2。
"""
    sec5 = ("\n## 5. 卡片（工具箱本體）\n以下都是參考資料。「提示卡」和 F01-00 是工作格式範本：只有我說「用 Q13-01」之類的時候才照它做，"
            "現在不要執行它的 Task。\n\n") if included else ""
    return head + sec1 + sec2 + sec3 + sec4 + sec5


def main():
    cards = parse_cards(SOURCES)
    refs = parse_cards(REF_SOURCES)
    for c in cards + refs:
        SERIES_ORDER.setdefault(c["series"], len(SERIES_ORDER))
    keyed = {c["key"]: c for c in cards}
    order = [k.strip() for line in PRIORITY.strip().splitlines() for k in line.split(";") if k.strip()]
    missing_keys = [k for k in order if k not in keyed]
    if missing_keys:
        raise SystemExit(f"PRIORITY 裡有不存在的卡：{missing_keys}")
    order += [c["key"] for c in cards if c["key"] not in order]          # 其餘照檔案順序
    pool = [keyed[k] for k in order] + refs                              # 參考卡排最後（只有大版本放得下）
    toks, method = count_tokens([c["text"] for c in pool])
    for c, t in zip(pool, toks):
        c["tok"] = t
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for tier, ctx, budget in TIERS:
        compact = ctx <= 8192
        upper = count_tokens([guide(tier, ctx, [], pool, compact)])[0][0]   # 全部沒放進來時的導引（上限）
        inc, used, skipped = [], upper, 0
        for c in pool:                                   # 照優先順序塞；連續 3 張放不下就停（不跳去塞後面不相干的小卡）
            if used + c["tok"] + 4 <= budget:
                inc.append(c); used += c["tok"] + 4; skipped = 0
            else:
                skipped += 1
                if skipped >= 3:
                    break
        while True:
            inc_set = {id(c) for c in inc}
            doc = guide(tier, ctx, inc, [c for c in pool if id(c) not in inc_set], compact) + \
                  "\n\n---\n\n".join(c["text"] for c in inc) + "\n"
            total = count_tokens([doc])[0][0]
            if total <= budget or not inc:
                break
            inc.pop()
        name = f"給模型_{tier}.md"
        (OUTDIR / name).write_text(doc, encoding="utf-8")
        rows.append((tier, ctx, budget, total, len(inc), len(doc)))
        print(f"{name}: {len(inc)} 張卡, {total} tokens（預算 {budget}）, {len(doc)} 字元")
    readme = ["# 分級版：給不同 context 大小的 local model",
              "",
              "> 這是 [`../../../考場SOP.md`](../../../考場SOP.md) 的**附錄 C**：只有能設 system prompt、或單次能貼很長時才用（取代總說明 3 張），08:45 設備檢查時探測。",
              "",
              "由 `model/gen_tiers.py` 產生，不要手改。每一版開頭都是同一套導引（你手上有什麼 → 還能要什麼 → 怎麼要 → 規則 → 狀況表），",
              "再照優先順序塞卡片，直到用完預算。預算 = context 的約 55%，剩下留給題目、程式和回答。沒放進來的卡，導引的 1.2 節會列出名稱，模型可以用【要卡】跟你要。",
              "",
              f"token 數：{method}。",
              "",
              "| 檔案 | 給多大的 context | 文件預算 | 實際 token | 卡片張數 | 字元數 |",
              "|---|---|---|---|---|---|"]
    for tier, ctx, budget, total, n, chars in rows:
        readme.append(f"| `給模型_{tier}.md` | {tier}（{ctx:,} token） | {budget:,} | {total:,} | {n} | {chars:,} |")
    readme += ["| `../05-給模型的說明書.md` + `../06-軍火庫.md` | 128k 以上 | — | 約 100,000（兩份合計） | 全部 | 約 194,000 |",
               "",
               "## 怎麼選",
               "",
               "- 看 local model 的 context 長度（Ollama：`ollama show <模型>` 的 `context length`，或你設定的 `num_ctx`），選**不超過**它的那一版。",
               "- 放在 system prompt（或第一則訊息）。模型第一次回覆時，請它先列出「我手上有的卡、我可能會跟你要的卡」確認它有讀到第 1 節。",
               "- 對話變長、模型開始忘規則：開新對話重新載入同一版。",
               "- 4k 版只有導引、沒有卡片：模型會用【要卡】跟你要卡、用【要資料】跟你要考場資料，你照 `model/README.md` 的兩張對照表貼。"]
    (OUTDIR / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
