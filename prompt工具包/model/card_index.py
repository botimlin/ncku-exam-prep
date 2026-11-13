#!/usr/bin/env python3
"""卡片編號（index）：每張貼上卡一個固定編號，例 L02-02 = 參考卡 RP2350 DMA 2/8。

編號 = 字母 + 兩位數系列 + "-" + 兩位數號碼（號碼 = 卡片標題裡的 n/N 的 n）。
字母避開資料代號用的 K B R T P S（K1、B1、R1、T1、P1、S1），模型才不會搞混：
  G 開頭（總說明、開題、開場）  H 要資料（給操作者的取法）  M 目錄
  E 規格卡（預製範本）  A API卡  C 片段卡  F 食譜卡  Q 提示卡  L 參考卡

編號不寫進卡片本文（卡片 ≤ 1200 字元、壓力測試的標題格式都不動），而是：
  - 編號卡/ 的查找檔：每張卡前面一行「## L02-02」，Ctrl-F 只會找到一處
  - 目錄卡、總說明 2/3、分級版、PDF 都標出編號
新增系列一定要加進 SERIES，否則 build_index() 會報錯（避免出現沒有編號的卡）。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent          # prompt工具包/

# (系列代號, 卡別, 系列名（標題裡 n/N 前面那段；沒有就 ""）, 檔案)
SERIES = [
    ("G01", "總說明", "", "model/00-總說明.md"),
    ("G02", "提示卡", "開題", "model/00-總說明.md"),
    ("G03", "開場", "", "cards/00-starter.md"),
    ("H01", "要資料", "", "model/02-要資料.md"),
    ("M01", "目錄", "", "model/01-資源目錄.md"),
    ("E01", "規格卡", "ROS", "model/spec-ros2.md"),
    ("E02", "規格卡", "PICO", "model/spec-pico.md"),
    ("E03", "規格卡", "UROS", "model/spec-micro-ros.md"),
    ("E04", "規格卡", "ALGO", "model/spec-algo.md"),
    ("E05", "規格卡", "BITS", "model/spec-bits-riscv.md"),
    ("E06", "規格卡", "PERF", "model/spec-linux-perf.md"),
    ("A01", "API卡", "DMA", "arsenal/api-pico.md"),
    ("A02", "API卡", "SNIFF", "arsenal/api-pico.md"),
    ("A03", "API卡", "PIO", "arsenal/api-pico.md"),
    ("A04", "API卡", "SYNC", "arsenal/api-sync-ros.md"),
    ("A05", "API卡", "PICO-IO", "arsenal/api-sync-ros.md"),
    ("A06", "API卡", "UROS", "arsenal/api-sync-ros.md"),
    ("A07", "API卡", "HOST-PY", "arsenal/api-sync-ros.md"),
    ("C01", "片段卡", "PICO-DMA", "arsenal/snippets-pico.md"),
    ("C02", "片段卡", "PICO-SNIFF", "arsenal/snippets-pico.md"),
    ("C03", "片段卡", "PICO-DMAPIO", "arsenal/snippets-pico.md"),
    ("C04", "片段卡", "PICO-PIO", "arsenal/snippets-pico.md"),
    ("C05", "片段卡", "PICO-MC", "arsenal/snippets-pico.md"),
    ("C06", "片段卡", "PICO-TIME", "arsenal/snippets-pico.md"),
    ("C07", "片段卡", "PICO-SERIAL", "arsenal/snippets-pico.md"),
    ("C08", "片段卡", "HOST-SERIAL", "arsenal/snippets-host.md"),
    ("C09", "片段卡", "HOST-MULTI", "arsenal/snippets-host.md"),
    ("C10", "片段卡", "HOST-ROS", "arsenal/snippets-host.md"),
    ("C11", "片段卡", "HOST-UROS", "arsenal/snippets-host.md"),
    ("C12", "片段卡", "ALGO", "arsenal/snippets-host.md"),
    ("C13", "片段卡", "PERF", "arsenal/snippets-host.md"),
    ("F01", "食譜卡", "優化", "arsenal/recipes-optimize.md"),
    ("Q01", "提示卡", "開考", "cards/10-exam-day-flow.md"),
    ("Q02", "提示卡", "讀題", "cards/02-read-spec.md"),
    ("Q03", "提示卡", "建置", "cards/05-cmake-build.md"),
    ("Q04", "提示卡", "工具", "cards/06-tools-debug.md"),
    ("Q05", "提示卡", "除錯", "cards/04-debug.md"),
    ("Q06", "提示卡", "優化", "cards/03-optimize.md"),
    ("Q07", "提示卡", "範本", "cards/09-template-adapt.md"),
    ("Q08", "提示卡", "查詢", "cards/11-ask-reference.md"),
    ("Q09", "提示卡", "實作", "cards/12-implement.md"),
    ("Q10", "提示卡", "驗證", "cards/13-verify-submit.md"),
    ("Q11", "提示卡", "提交", "cards/13-verify-submit.md"),
    ("Q12", "提示卡", "速學", "cards/07-unknown-tech.md"),
    ("Q13", "提示卡", "套用", "arsenal/recipes-optimize.md"),
    ("L01", "參考卡", "RP2350 pico-sdk", "cards/pico-sdk.md"),
    ("L02", "參考卡", "RP2350 DMA", "cards/pico-dma.md"),
    ("L03", "參考卡", "RP2350 PIO", "cards/pio.md"),
    ("L04", "參考卡", "RP2350 週邊", "cards/pico-peripherals.md"),
    ("L05", "參考卡", "多核同步", "cards/multicore-sync.md"),
    ("L06", "參考卡", "RISC-V Hazard3", "cards/riscv-hazard3.md"),
    ("L07", "參考卡", "Cortex-M33", "cards/arm-cortex-m33.md"),
    ("L08", "參考卡", "ROS 2", "cards/ros2.md"),
    ("L09", "參考卡", "主機↔MCU", "cards/host-mcu-comm.md"),
    ("L10", "參考卡", "演算法", "cards/algorithms-ds.md"),
    ("L11", "參考卡", "C/Linux 效能", "cards/c-linux-perf.md"),
    ("L12", "參考卡", "Python 效能", "cards/python-perf.md"),
    ("L13", "參考卡", "平行", "cards/parallel-distributed.md"),
    ("L14", "參考卡", "git/環境", "cards/git-env.md"),
    ("L15", "參考卡", "控制DSP", "cards/control-dsp.md"),
    ("L16", "參考卡", "FreeRTOS", "cards/freertos.md"),
    ("L17", "參考卡", "官方文件導航", "cards/08-docs-map.md"),
    ("L18", "參考卡", "讀題", "cards/02-read-spec.md"),
    ("L19", "參考卡", "建置", "cards/05-cmake-build.md"),
    ("L20", "參考卡", "工具", "cards/06-tools-debug.md"),
    ("L21", "參考卡", "除錯", "cards/04-debug.md"),
    ("L22", "參考卡", "優化", "cards/03-optimize.md"),
    ("L23", "參考卡", "速學", "cards/07-unknown-tech.md"),
]

TITLE = re.compile(r"^【([^｜】]+)｜([^｜】]*?)\s*(\d+)/(\d+)｜([^】]*)】")


def code_of(kind, series):
    for code, k, s, _ in SERIES:
        if k == kind and s == series:
            return code
    return None


def parse_title(line):
    """回傳 (卡別, 系列名, n, N, 主題) 或 None。"""
    m = TITLE.match(line.strip())
    if not m:
        return None
    kind, series, n, total, topic = m.groups()
    return kind.strip(), series.strip(), int(n), int(total), topic.strip()


def card_id(kind, series, n):
    code = code_of(kind, series)
    return f"{code}-{n:02d}" if code else None


def blocks(rel):
    """一個檔案裡的所有卡片（每張 = 標題那行起到下一條 --- 之前）。"""
    text = (ROOT / rel).read_text(encoding="utf-8")
    for chunk in re.split(r"\n---\n", text):
        s = chunk.strip()
        if s.startswith("【"):
            yield s


def build_index():
    """依 SERIES 順序回傳 [ {id, code, kind, series, n, total, topic, file, text} ]；有卡沒有編號就報錯。"""
    files = list(dict.fromkeys(f for *_, f in SERIES))
    found = {}
    problems = []
    for rel in files:
        if not (ROOT / rel).exists():
            continue
        for text in blocks(rel):
            t = parse_title(text.splitlines()[0])
            if not t:
                continue
            kind, series, n, total, topic = t
            code = code_of(kind, series)
            if not code:
                problems.append(f"{rel}: 沒有編號的系列「{kind}｜{series}」→ 加進 model/card_index.py 的 SERIES")
                continue
            cid = f"{code}-{n:02d}"
            if cid in found:
                problems.append(f"{rel}: 編號重複 {cid}")
            found[cid] = dict(id=cid, code=code, kind=kind, series=series, n=n, total=total, topic=topic,
                              file=rel, text=text)
    if problems:
        raise SystemExit("\n".join(problems))
    order = {code: i for i, (code, *_) in enumerate(SERIES)}
    return sorted(found.values(), key=lambda c: (order[c["code"]], c["n"]))


def name_of(c):
    """卡名（給人看）：例「參考卡 RP2350 DMA 2/8」、「總說明 1/3」。"""
    mid = f" {c['series']}" if c["series"] else ""
    return f"{c['kind']}{mid} {c['n']}/{c['total']}"


def id_by_title_line(line, _cache={}):
    """標題行 → 編號（build_print 用）。"""
    t = parse_title(line)
    return card_id(t[0], t[1], t[2]) if t else None


if __name__ == "__main__":
    idx = build_index()
    print(f"{len(idx)} 張卡有編號")
    for c in idx[:5]:
        print(c["id"], name_of(c), c["topic"][:20])
