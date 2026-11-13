#!/usr/bin/env python3
"""把工具包的 Markdown 排成可列印的 A4 PDF（需要 markdown-it-py 與 Google Chrome / Chromium）。

用法（在工具包根目錄）：
    python3 print/build_print.py          # 全部重做
    python3 print/build_print.py 05       # 只做檔名開頭是 05 的那本
輸出：print/*.pdf
"""
import html
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from markdown_it import MarkdownIt

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "print"

# 每本 PDF：(檔名, 標題, 副標, 章節清單)
BOOKS = [
    (
        "01-考場隨身手冊.pdf",
        "考場隨身手冊",
        "精簡版：開場設定、流程、文件導航、各領域速查",
        [
            "lite/00-starter.md",
            "lite/08-docs-map.md",
            "lite/02-read-spec.md",
            "lite/03-optimize.md",
            "lite/04-debug.md",
            "lite/07-unknown-tech.md",
            "lite/05-submit-and-time.md",
            "lite/domain/pico-sdk.md",
            "lite/domain/pico-dma.md",
            "lite/domain/pio.md",
            "lite/domain/riscv-hazard3.md",
            "lite/domain/arm-cortex-m33.md",
            "lite/domain/multicore-sync.md",
            "lite/domain/ros2.md",
            "lite/domain/pico-peripherals.md",
            "lite/domain/host-mcu-comm.md",
            "lite/domain/control-dsp.md",
            "lite/domain/freertos.md",
            "lite/domain/c-linux-perf.md",
            "lite/domain/python-perf.md",
            "lite/domain/algorithms-ds.md",
            "lite/domain/parallel-distributed.md",
            "lite/domain/git-env.md",
        ],
    ),
    (
        "02-官方文件導航圖.pdf",
        "官方文件導航圖",
        "RP2350 datasheet 章節、pico-sdk / ROS 2 文件網址、搜尋方法",
        ["full/08-docs-map.md"],
    ),
    (
        "03-流程詳細版.pdf",
        "流程詳細版",
        "讀題、優化、除錯、提交、時間策略、陌生技術",
        [
            "full/00-index.md",
            "full/02-read-spec.md",
            "full/03-optimize.md",
            "full/04-debug.md",
            "full/05-submit-check.md",
            "full/06-time-plan.md",
            "full/07-unknown-tech.md",
        ],
    ),
    (
        "04-提示詞卡.pdf",
        "提示詞卡（貼上用）",
        "壓力測試過的提示卡：開場、開考、讀題、建置、除錯、工具、優化、範本、查詢、實作、驗證、提交、速學",
        [
            "cards/00-starter.md",
            "cards/10-exam-day-flow.md",
            "cards/02-read-spec.md",
            "cards/05-cmake-build.md",
            "cards/04-debug.md",
            "cards/06-tools-debug.md",
            "cards/03-optimize.md",
            "cards/09-template-adapt.md",
            "cards/11-ask-reference.md",
            "cards/12-implement.md",
            "cards/13-verify-submit.md",
            "cards/07-unknown-tech.md",
        ],
    ),
    (
        "05-給模型的說明書.pdf",
        "給模型的說明書",
        "總說明、資源目錄、要資料（代號與指令）、預製範本規格卡",
        [
            "model/README.md",
            "model/00-總說明.md",
            "model/02-要資料.md",
            "model/01-資源目錄.md",
            "model/spec-ros2.md",
            "model/spec-pico.md",
            "model/spec-micro-ros.md",
            "model/spec-algo.md",
            "model/spec-bits-riscv.md",
            "model/spec-linux-perf.md",
        ],
    ),
    (
        "06-軍火庫.pdf",
        "軍火庫",
        "照抄用：API 簽名（pico-sdk、rclc、rclpy、pyserial）、程式片段、優化食譜",
        [
            "arsenal/README.md",
            "arsenal/recipes-optimize.md",
            "arsenal/api-pico.md",
            "arsenal/api-sync-ros.md",
            "arsenal/snippets-pico.md",
            "arsenal/snippets-host.md",
        ],
    ),
]

CSS = r"""
pre.card { white-space: pre-wrap; word-break: break-all; font-size: 8.6pt; line-height: 1.42;
  border: 1px solid #999; border-radius: 4px; padding: 6px 8px; margin: 8px 0; break-inside: avoid;
  font-family: "Noto Sans Mono CJK TC", "Noto Sans CJK TC", monospace; background: #fafafa; }
@page {
  size: A4;
  margin: 12mm 11mm 14mm 11mm;
  @bottom-center { content: counter(page) " / " counter(pages); font: 8pt "Noto Sans CJK TC", sans-serif; color: #666; }
  @top-right { content: string(chap); font: 7.5pt "Noto Sans CJK TC", sans-serif; color: #888; }
}
@page :first { @top-right { content: none; } }
html { font-family: "Noto Sans CJK TC", "Noto Sans CJK JP", sans-serif; font-size: 9pt; line-height: 1.42; color: #111; }
body { margin: 0; }
h1 { font-size: 14pt; margin: 0 0 4pt; padding-bottom: 2pt; border-bottom: 1.5pt solid #222; string-set: chap content(); break-after: avoid; }
h2 { font-size: 11pt; margin: 9pt 0 3pt; border-bottom: 0.5pt solid #999; break-after: avoid; }
h3 { font-size: 10pt; margin: 7pt 0 2pt; break-after: avoid; }
h4 { font-size: 9.5pt; margin: 6pt 0 2pt; break-after: avoid; }
p { margin: 2pt 0 4pt; }
ul, ol { margin: 2pt 0 4pt; padding-left: 15pt; }
li { margin: 0.5pt 0; }
blockquote { margin: 3pt 0; padding: 2pt 6pt; border-left: 2pt solid #bbb; color: #444; background: #f6f6f6; }
code { font-family: "Noto Sans Mono CJK TC", "DejaVu Sans Mono", monospace; font-size: 8pt; background: #f1f1f1; padding: 0 1.5pt; border-radius: 2pt; }
pre { font-family: "Noto Sans Mono CJK TC", "DejaVu Sans Mono", monospace; font-size: 7.6pt; line-height: 1.32; background: #f4f4f4; border: 0.5pt solid #ccc; padding: 3pt 5pt; margin: 3pt 0 5pt; white-space: pre-wrap; word-break: break-all; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 3pt 0 6pt; font-size: 8.2pt; break-inside: auto; }
th, td { border: 0.5pt solid #999; padding: 1.5pt 3pt; vertical-align: top; word-break: break-word; }
th { background: #e9e9e9; }
tr { break-inside: avoid; }
hr { border: 0; border-top: 0.5pt dashed #bbb; margin: 6pt 0; }
a { color: #0645ad; text-decoration: none; word-break: break-all; }
.chapter { break-before: page; }
.chapter:first-of-type { break-before: auto; }
body.flow .chapter { break-before: auto; margin-top: 10pt; padding-top: 6pt; border-top: 2.5pt solid #222; }
body.flow .chapter:first-of-type { border-top: 0; margin-top: 0; padding-top: 0; }
.src { font-size: 7pt; color: #888; margin: -2pt 0 4pt; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; text-align: center; break-after: page; }
.cover .t { font-size: 24pt; font-weight: bold; margin-bottom: 8pt; }
.cover .s { font-size: 11pt; color: #444; margin-bottom: 18pt; }
.cover .d { font-size: 9pt; color: #666; }
.toc { break-after: page; }
.toc h1 { string-set: none; }
.toc ol { font-size: 9.5pt; line-height: 1.7; }
"""


def md_to_html(md: str) -> str:
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table").enable("strikethrough")
    out = renderer.render(md)
    # 節號（如 §3.1.10.1）不折行
    return re.sub(r"(§\s?\d+(?:\.\d+)*)", r"<span style='white-space:nowrap'>\1</span>", out)


def chapter_title(md: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else fallback


def build_html(title: str, subtitle: str, files: list[str], flow: bool) -> str:
    parts, toc = [], []
    for rel in files:
        path = ROOT / rel
        if not path.exists():
            print(f"  缺少 {rel}，略過", file=sys.stderr)
            continue
        md = path.read_text(encoding="utf-8")
        t = chapter_title(md, rel)
        toc.append(f"<li>{html.escape(t)} <span class='src'>（{html.escape(rel)}）</span></li>")
        if rel.startswith(("cards/", "model/", "arsenal/")) and not rel.endswith("README.md"):
            # 貼上卡要「逐行照原樣」：每張卡用 <pre> 排，不讓 Markdown 把換行合併、把 * 當斜體
            chunks = re.split(r"\n---\n", md)
            body = md_to_html(chunks[0]) + "".join(
                f"<pre class='card'>{html.escape(c.strip())}</pre>" if c.strip().startswith("【") else md_to_html(c)
                for c in chunks[1:] if c.strip())
        else:
            body = md_to_html(md)
        # 在第一個 h1 後面標出來源檔
        body = body.replace("</h1>", f"</h1><div class='src'>{html.escape(rel)}</div>", 1)
        parts.append(f"<section class='chapter'>{body}</section>")
    cover = (
        f"<div class='cover'><div class='t'>{html.escape(title)}</div>"
        f"<div class='s'>{html.escape(subtitle)}</div>"
        f"<div class='d'>上機考 prompt 工具包｜最後更新 2026-11｜以官方文件與題目為準</div></div>"
    )
    tocs = f"<div class='toc'><h1>目錄</h1><ol>{''.join(toc)}</ol></div>" if len(toc) > 1 else ""
    return (
        "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body class='{'flow' if flow else ''}'>"
        f"{cover}{tocs}{''.join(parts)}</body></html>"
    )


def find_chrome() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    sys.exit("找不到 Chrome / Chromium")


RENDER_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const [src, dst] = process.argv.slice(1);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + src, { waitUntil: 'load' });
  await p.pdf({ path: dst, preferCSSPageSize: true, printBackground: true });
  await b.close();
})();
"""


def have_node_playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True).returncode == 0


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    use_pw = have_node_playwright()          # 有 playwright 就用它（headless Chrome 的 --print-to-pdf 在某些容器會卡住）
    chrome = None if use_pw else find_chrome()
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for fname, title, subtitle, files in BOOKS:
            if only and not fname.startswith(only):
                continue
            src = pathlib.Path(tmp) / (fname + ".html")
            src.write_text(build_html(title, subtitle, files, flow=fname.startswith("01-")), encoding="utf-8")
            dst = OUT / fname
            if use_pw:
                subprocess.run(["node", "-e", RENDER_JS, str(src), str(dst)], check=True)
            else:
                subprocess.run(
                    [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                     f"--user-data-dir={tmp}/profile", f"--print-to-pdf={dst}", src.as_uri()],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            print(f"{dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
