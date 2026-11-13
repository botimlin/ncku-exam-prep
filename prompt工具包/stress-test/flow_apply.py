"""flow_apply.py — 模擬操作者「照模型寫的字手動改檔」，再驗證改完的檔案。

考場模型不能上傳、也不能給可下載的檔案，操作者只能照文字改。所以這裡完全照人會做的事：
  - 「原本 / 修改前」那行 → 在檔案裡 Ctrl-F（忽略空白）找到 → 換成「改成 / 修改後」。
  - 「原本：（無）」＋「第 N 行之後（新增）」→ 插在第 N 行後面。
  - 「（刪除）」→ 刪掉那行。
  - 給了整個檔案（≥ 15 行的程式區塊，前面提到檔名）→ 整檔取代。
  - 找不到「原本」那行 → 這一處改不了（記 fail）。
"""
import os, re, subprocess, tempfile, py_compile

FILE_RE = r"[\w./\-]+\.(?:c|h|py|cpp|S|pio|txt)"


def _n(x):
    return re.sub(r"\s+", "", x)


def _strip_code(x):
    # 網頁聊天會把 `code`、```區塊``` 顯示成程式樣式，複製時不會帶反引號 → 這裡也拿掉
    x = x.strip()
    x = re.sub(r"^```\w*\n?", "", x)
    x = re.sub(r"\n?```$", "", x)
    return "\n".join(l.strip().strip("`") if l.strip().startswith("`") else l for l in x.split("\n")).strip("\n")


def _pick_file(files, text_before, default):
    names = re.findall(FILE_RE, text_before)
    for nm in reversed(names):
        for p in files:
            if p.endswith(nm) or os.path.basename(p) == os.path.basename(nm):
                return p
    return default


def parse_changes(text):
    """回傳 [(檔名提示文字, 位置文字, 原本, 改成)]，照出現順序。"""
    out = []
    pat = re.compile(r"(?:原本|修改前)[ \t]*[:：][ \t]*(.*?)\n\s*(?:改成|修改後)[ \t]*[:：][ \t]*(.*?)(?=\n\s*(?:【改|【驗證|檔案\s*[:：]|檔名|位置\s*[:：]|行號|原本|修改前|驗證|成功|\*\*|（每處)|\n\s*\n|\Z)", re.S)
    for m in pat.finditer(text):
        ctx = text[max(0, m.start() - 300):m.start()]
        pos = ""
        pm = re.findall(r"(?:位置|行號)\s*[:：]?\s*([^\n]*)", ctx)
        if pm:
            pos = pm[-1]
        out.append((ctx, pos, _strip_code(m.group(1)), _strip_code(m.group(2))))
    # 斜線一行式：檔名:行號 / 原本 / 改成
    for m in re.finditer(rf"({FILE_RE}):\s*(\d+)\s*/\s*(.+?)\s*/\s*(.+)", text):
        out.append((m.group(1), f"第 {m.group(2)} 行（取代）", m.group(3).strip().strip("`"), m.group(4).strip().strip("`")))
    return out


def apply(case, texts):
    files = dict(case.get("files", {}))
    main = (case.get("main_files") or list(files))[0]
    st = {"applied": 0, "failed": 0, "already": 0, "whole": 0}
    for t in texts:
        # 整檔
        for m in re.finditer(r"```\w*\n(.*?)```", t, re.S):
            code = m.group(1)
            if code.count("\n") >= 15:
                p = _pick_file(files, t[max(0, m.start() - 200):m.start()], None)
                if p:
                    files[p] = code
                    st["whole"] += 1
        for ctx, pos, before, after in parse_changes(t):
            p = _pick_file(files, ctx, main)
            lines = files[p].split("\n")
            if (re.search(r"刪除", pos) and not after.strip()) or re.fullmatch(r"[（(]?\s*刪除\s*[)）]?", after.strip()):
                after = ""
            empty_before = (not before.strip()) or re.match(r"^[（(]?\s*(無|沒有|none|空|新增)", before.strip(), re.I)
            if empty_before:
                nm = re.search(r"(\d+)", pos)
                if not nm:
                    st["failed"] += 1
                    continue
                k = int(nm.group(1))
                if _n(after) and _n(after) in _n(files[p]):
                    st["already"] += 1
                    continue
                idx = k if re.search(r"之後|後|after", pos) or not re.search(r"之前|前", pos) else k - 1
                lines[idx:idx] = after.split("\n")
                files[p] = "\n".join(lines)
                st["applied"] += 1
                continue
            # 人會把 cat -n 抄進來的行號去掉再 Ctrl-F
            before = "\n".join(re.sub(r"^\s*\d+[\t ]+(?=\S)", "", x) for x in before.split("\n"))
            bl = [_n(x) for x in before.split("\n") if _n(x)]
            hit = None
            for i in range(len(lines)):
                if bl and bl[0] and bl[0] in _n(lines[i]) and all(
                        i + j < len(lines) and b in _n(lines[i + j]) for j, b in enumerate(bl)):
                    hit = i
                    break
            if hit is None:
                if _n(after) and _n(after) in _n(files[p]):
                    st["already"] += 1
                else:
                    st["failed"] += 1
                continue
            indent = re.match(r"\s*", lines[hit]).group(0)
            new = [indent + x.lstrip() if x.strip() else x for x in after.split("\n")] if after else []
            lines[hit:hit + len(bl)] = new
            files[p] = "\n".join(lines)
            st["applied"] += 1
    return files, st


# ------------------------------------------------------------------ validators
def _gcc_run(src_files, main_c, args=()):
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, txt in src_files.items():
            fp = os.path.join(d, os.path.basename(name))
            open(fp, "w").write(txt)
            if fp.endswith(".c"):
                paths.append(fp)
        mp = os.path.join(d, "t_main.c"); open(mp, "w").write(main_c); paths.append(mp)
        exe = os.path.join(d, "t")
        r = subprocess.run(["gcc", "-O1", "-w", "-I", d, *paths, "-o", exe], capture_output=True, text=True)
        if r.returncode:
            return False, "編譯失敗：\n" + "\n".join(l.replace(d + "/", "") for l in r.stderr.strip().split("\n") if "error" in l)[:600]
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=20)
        return r.returncode == 0, r.stdout.strip()[-200:]


BITS_TEST = r"""
#include <stdio.h>
#include <stdlib.h>
#include "decode.h"
int main(void){ srand(1); int bad=0;
 for(int k=0;k<1000;k++){ unsigned ver=rand()&7, type=rand()&31, len=rand()&0xFFF; int temp=(rand()&0xFFF)-2048;
  unsigned w=(ver<<29)|(type<<24)|(len<<12)|((unsigned)temp&0xFFF);
  unsigned char b[4]={w&255,(w>>8)&255,(w>>16)&255,w>>24}; struct hdr h; decode_header(b,&h);
  if(h.ver!=ver||h.type!=type||h.len!=len||h.temp!=temp){ if(bad<1) printf("bad %u %u %u %d -> %u %u %u %d\n",ver,type,len,temp,h.ver,h.type,h.len,h.temp); bad++; } }
 printf("bad=%d\n",bad); return bad!=0; }
"""


def _pico_build(files, src_name, extra_libs):
    sdk = os.environ.get("PICO_SDK_PATH", "/workspace/pico-sdk")
    if not os.path.isdir(sdk):
        return None, "沒有 pico-sdk，跳過編譯"
    imp = os.path.join(os.path.dirname(__file__), "..", "..", "預製程式碼", "pico", "pico_sdk_import.cmake")
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "main.c"), "w").write(files[src_name])
        open(os.path.join(d, "pico_sdk_import.cmake"), "w").write(open(imp).read())
        open(os.path.join(d, "CMakeLists.txt"), "w").write(
            "cmake_minimum_required(VERSION 3.13)\ninclude(pico_sdk_import.cmake)\nproject(t C CXX ASM)\npico_sdk_init()\n"
            f"add_executable(t main.c)\ntarget_link_libraries(t pico_stdlib {' '.join(extra_libs)})\n")
        env = dict(os.environ, PICO_SDK_PATH=sdk)
        r = subprocess.run(["cmake", "-S", d, "-B", d + "/b", "-DPICO_BOARD=pico2"], capture_output=True, text=True, env=env)
        if r.returncode:
            return False, "cmake 失敗：" + r.stderr.strip()[-160:]
        r = subprocess.run(["cmake", "--build", d + "/b", "-j16"], capture_output=True, text=True, env=env)
        if r.returncode:
            err = [l for l in r.stdout.split("\n") + r.stderr.split("\n") if "error:" in l or "undefined reference" in l]
            return False, "編譯失敗：\n" + ("\n".join(e.replace(d + "/", "") for e in err[:6]) if err else r.stderr[-400:])
        return True, "編譯通過"


def validate(case, files, build=False):
    cid = case["id"]
    checks = []
    if cid == "bits_fields":
        ok, msg = _gcc_run({"decode.c": files["src/decode.c"], "decode.h": files["src/decode.h"]}, BITS_TEST)
        checks.append(("1000 組測資", ok, msg))
    elif cid == "dma_copy":
        f = files["pico/copy.c"]
        checks += [("write_increment 開", bool(re.search(r"write_increment\(\s*&c\s*,\s*true", f)), ""),
                   ("count = N（不是 bytes）", bool(re.search(r"dma_channel_configure\([^;]*,\s*N\s*,", f)) and "N * 4" not in f and "N*4" not in f, ""),
                   ("有 unclaim", "dma_channel_unclaim" in f, "")]
        if build:
            ok, msg = _pico_build(files, "pico/copy.c", ["hardware_dma"])
            if ok is not None:
                checks.append(("pico-sdk 編譯", ok, msg))
    elif cid == "multicore_race":
        f = files["pico/counter.c"]
        checks.append(("有同步（鎖 / atomic）", bool(re.search(r"spin_lock_blocking|critical_section_enter_blocking|mutex_enter_blocking|__atomic|atomic_fetch_add", f)), ""))
        if build:
            ok, msg = _pico_build(files, "pico/counter.c", ["pico_multicore", "hardware_sync"])
            if ok is not None:
                checks.append(("pico-sdk 編譯", ok, msg))
    elif cid == "ros2_topic":
        f = files["ros2_ws/src/q21/q21/consumer.py"]
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
                tf.write(f)
            py_compile.compile(tf.name, doraise=True); syn = True
        except py_compile.PyCompileError:
            syn = False
        checks += [("Python 語法", syn, ""),
                   ("訂閱 /numbers", bool(re.search(r"create_subscription\([^)]*[\"']/?numbers[\"']", f, re.S)), ""),
                   ("QoS 配合 BEST_EFFORT", bool(re.search(r"BEST_EFFORT|qos_profile_sensor_data|ReliabilityPolicy\.BEST", f)), "")]
    elif cid == "serial_batch":
        h, p = files["host/send.py"], files["pico/main.c"]
        checks += [("電腦端改二進位", bool(re.search(r"struct\.pack|to_bytes|array\(|tobytes|pack\(", h)), ""),
                   ("不再每筆等 ok", not re.search(r"for .*\n(?:.*\n)?\s*.*readline\(\).*ok", h), ""),
                   ("Pico 端不用 scanf", "scanf" not in p, "")]
        if build:
            ok, msg = _pico_build(files, "pico/main.c", [])
            if ok is not None:
                checks.append(("pico-sdk 編譯", ok, msg))
    return all(c[1] for c in checks) if checks else False, checks
