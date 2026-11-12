#!/usr/bin/env python3
"""把《預製程式碼 使用說明書》排成 A4 PDF。

用法（在 預製程式碼/ 執行）：
    python3 說明書/gen_todo_index.py      # 先更新 TODO 總表
    python3 說明書/build_pdf.py           # 產生 說明書/預製程式碼使用說明書.pdf

需要：markdown-it-py；以及下列其中一種
    (a) Node.js + playwright（`require('playwright')` 能用）
    (b) Google Chrome / Chromium（headless --print-to-pdf）
版面沿用 ../prompt工具包/print/build_print.py 的 CSS 與 Markdown 轉換。
"""
import html
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent                                   # 預製程式碼/
sys.path.insert(0, str(ROOT.parent / "prompt工具包" / "print"))
from build_print import CSS, md_to_html, chapter_title  # noqa: E402

OUT = HERE / "預製程式碼使用說明書.pdf"
CHAPTERS = [
    "說明書/00-總覽.md",
    "說明書/01-考場情境演練.md",
    "說明書/02-ros2.md",
    "說明書/03-pico.md",
    "說明書/04-micro-ros.md",
    "說明書/05-algo.md",
    "說明書/06-bits-riscv.md",
    "說明書/07-linux-perf.md",
    "說明書/08-tools導讀.md",
    "說明書/09-附錄.md",
]
APPENDICES = [  # (標題前綴, 檔案)
    ("附錄 A", "tools/cmake.md"),
    ("附錄 B", "tools/debug-host.md"),
    ("附錄 C", "tools/debug-pico.md"),
    ("附錄 D", "tools/debug-ros2.md"),
    ("附錄 E", "tools/vscode.md"),
]
EXTRA_CSS = """
.toc ol { font-size: 9pt; line-height: 1.6; }
h1 { font-size: 15pt; }
"""

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


def build_html() -> str:
    parts, toc = [], []
    for prefix, rel in [(None, c) for c in CHAPTERS] + APPENDICES:
        path = ROOT / rel
        if not path.exists():
            print(f"  缺少 {rel}，略過", file=sys.stderr)
            continue
        md = path.read_text(encoding="utf-8")
        if prefix:  # tools/ 手冊：在標題前加「附錄 X」
            md = md.replace("# ", f"# {prefix}　", 1)
        t = chapter_title(md, rel)
        toc.append(f"<li>{html.escape(t)} <span class='src'>（{html.escape(rel)}）</span></li>")
        body = md_to_html(md).replace("</h1>", f"</h1><div class='src'>{html.escape(rel)}</div>", 1)
        parts.append(f"<section class='chapter'>{body}</section>")
    cover = ("<div class='cover'><div class='t'>預製程式碼 使用說明書</div>"
             "<div class='s'>ROS 2、Pico 2（RP2350）、micro-ROS、演算法、位元與 RISC-V、效能、工具</div>"
             "<div class='d'>成大資工特殊選才上機考｜最後核對 2026-11-12｜以題目與官方文件為準</div></div>")
    tocs = f"<div class='toc'><h1>目錄</h1><ol>{''.join(toc)}</ol></div>"
    return ("<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
            f"<title>預製程式碼 使用說明書</title><style>{CSS}{EXTRA_CSS}</style></head><body>"
            f"{cover}{tocs}{''.join(parts)}</body></html>")


def have_node_playwright() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    r = subprocess.run([node, "-e", "require('playwright')"], capture_output=True)
    return r.returncode == 0


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / "manual.html"
        src.write_text(build_html(), encoding="utf-8")
        if have_node_playwright():
            subprocess.run(["node", "-e", RENDER_JS, str(src), str(OUT)], check=True)
        else:
            chrome = next((shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "chrome")
                           if shutil.which(n)), None)
            if not chrome:
                sys.exit("找不到 playwright 或 Chrome / Chromium")
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                            f"--user-data-dir={tmp}/profile", f"--print-to-pdf={OUT}", src.as_uri()],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
