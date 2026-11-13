#!/usr/bin/env python3
"""flow.py — 考場SOP 主流程的多輪實測（stdlib only）。

模擬「操作者」照 考場SOP.md 第 4～6 節做：
  新對話 → G01-01、G01-02、G01-03（各應回「了解」）→ 題目分段（包資料區塊，應回「收到」）
  → G02-01 開題卡 → 模型用【要卡】/【要資料】要東西 → 操作者照 SOP §6 去拿、包起來＋「繼續」貼回
  → 直到模型給出「修改前 / 修改後」或回合用完。
另外跑 SOP §3.2 的「測試 2」（記不記得工具）。

卡片一律從 ../編號卡/ 的查找檔讀（跟考場一樣）；範本程式從 ../../預製程式碼/ 讀（cat -n 格式）。
後端：Ollama 原生 /api/chat（可以逐請求設 num_ctx、think=false）。

  python3 flow.py --base-url http://127.0.0.1:11434 --model gemma4:12b --ctx 4096,8192 --out out/flow/gemma4_12b
  python3 flow.py --report out/flow         # 所有結果的總表
"""
import argparse, glob, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.normpath(os.path.join(HERE, ".."))
PREP = os.path.normpath(os.path.join(KIT, "..", "預製程式碼"))
sys.path.insert(0, HERE)
import flow_cases  # noqa: E402
import flow_apply  # noqa: E402
BUILD = False

ID_RE = re.compile(r"\b([GHMEACFQL]\d{2})-(\d{2})\b")
SERIES_RE = re.compile(r"\b([GHMEACFQL]\d{2})\b")
CODE_RE = re.compile(r"\b([KBRTPS][1-7])\b")
REQ_RE = re.compile(r"【要(卡|資料)】\s*([^\n]*)")
TASK_PREFIX = ("Q", "F01-00", "G02-01")
PROACTIVE = False  # --proactive：題目貼完後主動貼要改的檔
FIX_AFTER = None   # --fix-after N：第 N 輪請求給完後貼修改卡
FIX_CARD = ""
PLAIN = False      # --plain：修 bug 對話裡貼程式不加行號
FIX_ONLY = False   # --fix-only：只跑「修 bug 專用的新對話」
CHECK_CARD = ""    # --check-card：修改卡前先貼陷阱卡＋檢查卡
TRAP_BY_AREA = {"E01": "E01-11", "E02": "E02-13", "E03": "E03-09", "E04": "E04-09", "E05": "L06-08", "E06": "E06-05"}
FEEDBACK = 0       # --feedback N：改完編譯 / 測資失敗時，把錯誤貼回去（SOP §5.2）


# ------------------------------------------------------------------ cards
def load_cards():
    cards = {}
    for f in sorted(glob.glob(os.path.join(KIT, "編號卡", "[1-4]-*.md"))):
        s = open(f, encoding="utf-8").read()
        for m in re.finditer(r"^## ([A-Z]\d{2}-\d{2})\n(.*?)(?=^---$|\Z)", s, re.S | re.M):
            body = m.group(2)
            body = body[body.find("【"):].rstrip()
            cards[m.group(1)] = body
    return cards


CARDS = load_cards()


def is_task(cid):
    return cid.startswith("Q") or cid in ("F01-00", "G02-01")


def wrap(src, text):
    return f"<<<資料 開始>>>\n來源：{src}\n{text.rstrip()}\n<<<資料 結束>>>"


# ------------------------------------------------------------------ operator
def cat_n(text, a, b):
    lines = text.split("\n")
    a = max(1, a); b = min(len(lines), b, a + 59)
    return "\n".join(f"{i:6d}\t{lines[i-1]}" for i in range(a, b + 1))


def find_file(case, path):
    path = path.strip().strip("`'\"").replace("~/prep/", "").replace("預製程式碼/", "")
    if path in case.get("files", {}):
        return case["files"][path]
    for p in case.get("files", {}):
        if p.endswith(path) or path.endswith(p):
            return case["files"][p]
    cand = os.path.join(PREP, path)
    if os.path.isfile(cand):
        return open(cand, encoding="utf-8").read()
    hits = glob.glob(os.path.join(PREP, "**", os.path.basename(path)), recursive=True)
    if hits:
        return open(hits[0], encoding="utf-8").read()
    return None


def fulfil(case, kind, rest, log):
    """Return (message_part, is_task_card, note)."""
    if kind == "卡":
        m = ID_RE.search(rest)
        if m:
            cid = f"{m.group(1)}-{m.group(2)}"
        else:
            s = SERIES_RE.search(rest)
            if not s:
                return wrap("（操作者）", "看不懂要哪張卡，請寫編號（例 E02-01）"), False, "bad-card-ref"
            cid = f"{s.group(1)}-01" if f"{s.group(1)}-01" in CARDS else f"{s.group(1)}-00"
        if cid not in CARDS:
            return wrap("（操作者）", f"沒有 {cid} 這張，請看目錄 M01-01。\n" + CARDS["M01-01"]), False, f"missing:{cid}"
        body = CARDS[cid]
        if is_task(cid):
            body = re.sub(r"\{\{(.*?)\}\}", lambda mm: case.get("fill", {}).get(mm.group(1), "（見上面的資料）"), body, flags=re.S)
            return body, True, f"task:{cid}"
        return wrap(cid, body), False, f"card:{cid}"
    # 資料
    m = re.search(r"題目第\s*(\d+)", rest)
    if m:
        n = int(m.group(1)); segs = case["segments"]
        if 1 <= n <= len(segs):
            return wrap(f"題目第 {n}/{len(segs)} 段", segs[n - 1]), False, f"seg:{n}"
    m = re.search(r"程式\s*[`]?([\w./~\-]+\.\w+)[`]?\s*(\d+)\s*[-–~～]\s*(\d+)", rest)
    if m:
        txt = find_file(case, m.group(1))
        if txt is None:
            return wrap(f"程式 {m.group(1)}", "（沒有這個檔案）"), False, f"nofile:{m.group(1)}"
        a, b = int(m.group(2)), int(m.group(3))
        return wrap(f"程式 {m.group(1)} {a}-{min(b, a+59)}（cat -n）", cat_n(txt, a, b)), False, f"code:{m.group(1)}"
    m = re.search(r"程式\s*[`]?([\w./~\-]+\.\w+)", rest)
    if m:
        txt = find_file(case, m.group(1))
        if txt is None:
            return wrap(f"程式 {m.group(1)}", "（沒有這個檔案）"), False, f"nofile:{m.group(1)}"
        return wrap(f"程式 {m.group(1)} 1-60（cat -n；只先給前 60 行）", cat_n(txt, 1, 60)), False, f"code:{m.group(1)}"
    # 人會看懂「K2｜請給我 copy.c 的內容」這種寫法：請求裡提到題目 repo 的檔名 → 給那個檔（記 code-by-name）
    for p in case.get("files", {}):
        base = os.path.basename(p)
        if base in rest and re.search(r"內容|程式碼|原始碼|全文|code|貼", rest):
            return wrap(f"程式 {p} 1-60（cat -n）", cat_n(case["files"][p], 1, 60)), False, f"code-by-name:{p}"
    m = CODE_RE.search(rest)
    if m:
        code = m.group(1)
        data = case.get("data", {}).get(code) or flow_cases.DEFAULT_DATA.get(code)
        if data:
            return wrap(f"資料 {code}", data), False, f"data:{code}"
        return wrap(f"資料 {code}", "（這個情境拿不到這項資料）"), False, f"nodata:{code}"
    for key, out in case.get("commands", {}).items():
        if key in rest:
            return wrap(f"指令 {key}", out), False, f"cmd:{key}"
    return wrap("（操作者）", "這項我拿不到。請用代號（總說明 3/3）、題目第 n 段、程式 檔名 起-迄 或卡片編號要。"), False, "unknown-req"


# ------------------------------------------------------------------ model
class Client:
    def __init__(self, base, model, ctx, temperature, log_path=None):
        self.base, self.model, self.ctx, self.temp = base.rstrip("/"), model, ctx, temperature
        self.think_ok = True
        self.log_path = log_path

    def chat(self, messages):
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": {"num_ctx": self.ctx, "temperature": self.temp, "num_predict": 1500}}
        if self.think_ok:
            body["think"] = False
        t0 = time.time()
        for attempt in range(3):
            req = urllib.request.Request(self.base + "/api/chat", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    j = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")
                if "think" in msg and self.think_ok:
                    self.think_ok = False; body.pop("think", None); continue
                raise RuntimeError(msg)
        msg = j.get("message", {})
        return {"text": msg.get("content", ""), "thinking": msg.get("thinking", ""),
                "prompt_tokens": j.get("prompt_eval_count"), "out_tokens": j.get("eval_count"),
                "done_reason": j.get("done_reason"), "sec": round(time.time() - t0, 1)}


def trunc_count(log_path):
    if not log_path or not os.path.exists(log_path):
        return None
    return open(log_path, encoding="utf-8", errors="replace").read().count("truncating input prompt")


# ------------------------------------------------------------------ run one conversation
def _norm(x):
    return re.sub(r"\s+", "", x.strip().strip("`").strip())


def explicit_score(case, texts):
    """模型給的修改，操作者能不能照著手動改：
    changes＝找到幾處「原本/修改前 → 改成/修改後」；verbatim＝「原本」在真檔案裡逐字找得到（新增不算）；
    whole_file＝丟出 ≥ 25 行的程式區塊（叫人整檔取代）。"""
    srcs = {p: case["files"][p] for p in case.get("files", {})}
    alltxt = "\n".join(srcs.values())
    lines = {_norm(l) for l in alltxt.split("\n") if _norm(l)}
    changes = verb = 0
    for t in texts:
        for m in re.finditer(r"(?:原本|修改前)\s*[:：]\s*(.*?)\n\s*(?:改成|修改後)\s*[:：]", t, re.S):
            before = m.group(1).strip()
            before = re.sub(r"^```\w*\n?|```$", "", before.strip()).strip()
            changes += 1
            if not before or re.search(r"^[（(]?\s*(無|沒有|none|空)", before, re.I):
                continue
            bl = [_norm(x) for x in before.split("\n") if _norm(x)]
            if bl and all(any(b in L or L in b for L in lines if len(L) > 3) for b in bl):
                verb += 1
    whole = any(c.count("\n") >= 25 for t in texts for c in re.findall(r"```.*?```", t, re.S))
    return changes, verb, whole


def is_solution(text):
    if re.search(r"修改後", text) and re.search(r"修改前", text):
        return True
    if re.search(r"\w+\.(c|py|h|cpp):\s*\d+", text) and re.search(r"驗證", text) and re.search(r"修改", text):
        return True
    code = re.findall(r"```.*?```", text, re.S)
    return any(c.count("\n") >= 5 for c in code) and re.search(r"驗證|預期結果|成功的樣子", text) is not None


def run_case(cli, case, max_rounds, log_path, cont="繼續"):
    msgs, turns, notes = [], [], []

    def send(user, kind):
        before = trunc_count(log_path)
        msgs.append({"role": "user", "content": user})
        r = cli.chat(msgs)
        msgs.append({"role": "assistant", "content": r["text"]})
        after = trunc_count(log_path)
        r["truncated"] = (before is not None and after is not None and after > before)
        r.update(kind=kind, user=user)
        turns.append(r)
        return r["text"]

    res = {"case": case["id"]}
    if FIX_ONLY:
        return run_fix_conversation(case, send, turns, res, log_path)
    acks = [send(CARDS[c], c) for c in ("G01-01", "G01-02", "G01-03")]
    res["ack_ok"] = sum(1 for a in acks if "了解" in a and len(a.strip()) <= 30)
    segs = case["segments"]
    seg_replies = [send(wrap(f"題目第 {i}/{len(segs)} 段", s).replace("來源：", "", 1), f"seg{i}") for i, s in enumerate(segs, 1)]
    res["seg_ok"] = sum(1 for a in seg_replies if "收到" in a and len(a.strip()) <= 30 and "【要" not in a)
    if PROACTIVE:
        for p in case.get("main_files", list(case.get("files", {}))[:1]):
            r = send(wrap(f"程式 {p} 1-60（cat -n，題目要改的檔）", cat_n(case["files"][p], 1, 60)), f"file:{p}")
    g2 = send(CARDS["G02-01"], "G02-01")
    pick = re.search(r"最像的範本區[：:]\s*\**\s*(E0[1-6]|都不像)", g2)
    res["pick"] = pick.group(1) if pick else None
    res["pick_ok"] = bool(pick and pick.group(1) in case["expect_area"])
    res["g02_fields"] = sum(1 for f in ("小題", "評分與提交方式", "最像的範本區", "第一個能動版") if f in g2)
    reqs_all, rounds, patch_round, last = [], 0, None, g2
    asked = set()
    over2 = dups = given_then_again = 0
    proto_miss = [0]
    pushed = False
    fix_sent = False
    while rounds < max_rounds:
        reqs = REQ_RE.findall(last)
        if is_solution(last):
            patch_round = rounds
            break
        if not reqs:
            notes.append(f"r{rounds}: 沒有請求也沒有修改")
            if pushed:      # 已經催過一次還是沒有修改 → 結束
                break
            pushed = True   # 下面會送 SOP §6.3 的催促句
        if len(reqs) > 2:
            over2 += 1
        reqs = reqs[:2]
        parts, task_parts = [], []
        for kind, rest in reqs:
            key = (kind, re.sub(r"｜.*", "", rest).strip())
            if key in asked:
                dups += 1
            asked.add(key)
            part, is_t, note = fulfil(case, kind, rest, notes)
            reqs_all.append({"round": rounds, "kind": kind, "raw": rest.strip()[:120], "note": note,
                             "relevant": flow_cases.is_relevant(case, note)})
            (task_parts if is_t else parts).append(part)
        rounds += 1
        if FIX_AFTER is not None and rounds > FIX_AFTER and not fix_sent:
            fix_sent = True
            extra = ("\n\n".join(parts) + "\n\n") if parts else ""
            if extra:   # 先把這一輪要的東西給它（只回收到也沒關係），再貼修改卡
                send(extra.rstrip(), f"r{rounds}-data")
            if CHECK_CARD:
                pick = res.get("pick") or ""
                trap = TRAP_BY_AREA.get(pick)
                if trap:
                    send(wrap(trap, CARDS[trap]), f"r{rounds}-trap:{trap}")
                send(CHECK_CARD, f"r{rounds}-CHECK")
            last = send(FIX_CARD, f"r{rounds}-FIX")
            continue
        if parts:
            last = send("\n\n".join(parts) + "\n" + cont, f"r{rounds}")
            if last.strip().rstrip("。.") == "收到":   # SOP §6.3：只回收到 → 補一則「繼續」
                proto_miss[0] += 1
                last = send("繼續", f"r{rounds}-繼續")
            if task_parts:
                last = send(task_parts[0], f"r{rounds}-task")
        elif task_parts:
            last = send(task_parts[0], f"r{rounds}-task")
        else:
            last = send("資料已經夠了，請直接用現有資料回答，缺的標【推測】", f"r{rounds}-push")
    if patch_round is None and is_solution(last):
        patch_round = rounds
    after_g2 = "\n".join(t["text"] for t in turns[turns.index(next(t for t in turns if t["kind"] == "G02-01")):])
    checks = case.get("solution_checks", [])
    res["fix_hits"] = sum(1 for c in checks if re.search(c, after_g2))
    res["fix_ok"] = bool(checks) and res["fix_hits"] == len(checks)
    sol_texts = [t["text"] for t in turns[turns.index(next(t for t in turns if t["kind"] == "G02-01")):]]
    res["n_changes"], res["n_verbatim"], res["whole_file"] = explicit_score(case, sol_texts)
    files_after, st = flow_apply.apply(case, sol_texts)
    ok, checks = flow_apply.validate(case, files_after, build=BUILD)
    res["works_first"] = ok
    res["feedback_rounds"] = 0
    for it in range(FEEDBACK):
        if ok:
            break
        bad = [c for c in checks if not c[1] and c[2]]
        if not bad:
            break   # 錯在操作者看不到的地方（沒板子、沒 ROS）→ 考場要靠實機輸出，這裡停
        name, _, msg = bad[0]
        code = "B1" if "編譯" in msg else "R1"
        fb = wrap(f"資料 {code}（照你的修改改完後：{name}）", msg) + "\n繼續"
        r_txt = send(fb, f"fb{it + 1}")
        sol_texts.append(r_txt)
        res["feedback_rounds"] = it + 1
        files_after, st = flow_apply.apply(case, sol_texts)
        ok, checks = flow_apply.validate(case, files_after, build=BUILD)
    res.update(applied=st, works=ok, checks=[[c[0], c[1], c[2]] for c in checks])
    res["_files_after"] = files_after
    res.update(rounds=rounds, patch_round=patch_round, reqs=reqs_all, over2=over2, dups=dups, notes=notes,
               valid_req=sum(1 for r in reqs_all if not r["note"].startswith(("missing", "bad", "unknown", "nofile", "nodata"))),
               relevant_req=sum(1 for r in reqs_all if r["relevant"]), n_req=len(reqs_all),
               patch_file_ok=bool(patch_round is not None and any(f in last for f in case["expect_files"])),
               truncated=any(t["truncated"] for t in turns),
               only_shou_dao=proto_miss[0], n_data_replies=sum(1 for t in turns if re.fullmatch(r"r\d+", t["kind"])),
               last_prompt_tokens=max((t["prompt_tokens"] or 0) for t in turns),
               sec=round(sum(t["sec"] for t in turns), 1))
    return res, turns


def finish(case, turns, res, send, sol_from):
    sol_texts = [t["text"] for t in turns[sol_from:] if t["kind"] not in ("G01-01",)]
    checks = case.get("solution_checks", [])
    res["fix_hits"] = sum(1 for c in checks if re.search(c, "\n".join(sol_texts)))
    res["fix_ok"] = bool(checks) and res["fix_hits"] == len(checks)
    res["n_changes"], res["n_verbatim"], res["whole_file"] = explicit_score(case, sol_texts)
    files_after, st = flow_apply.apply(case, sol_texts)
    ok, checks_ = flow_apply.validate(case, files_after, build=BUILD)
    res["works_first"] = ok
    res["feedback_rounds"] = 0
    for it in range(FEEDBACK):
        if ok:
            break
        bad = [c for c in checks_ if not c[1] and c[2]]
        if not bad:
            break
        name, _, msg = bad[0]
        code = "B1" if "編譯" in msg else "R1"
        sol_texts.append(send(wrap(f"資料 {code}（照你的修改改完後：{name}）", msg) + "\n繼續", f"fb{it + 1}"))
        res["feedback_rounds"] = it + 1
        files_after, st = flow_apply.apply(case, sol_texts)
        ok, checks_ = flow_apply.validate(case, files_after, build=BUILD)
    res.update(applied=st, works=ok, checks=[[c[0], c[1], c[2]] for c in checks_], _files_after=files_after,
               pick=case["expect_area"][0], pick_ok=True, ack_ok=3, seg_ok=len(case["segments"]), g02_fields=0,
               rounds=0, patch_round=None, reqs=[], over2=0, dups=0, notes=[], valid_req=0, relevant_req=0, n_req=0,
               patch_file_ok=False, truncated=any(t["truncated"] for t in turns), only_shou_dao=0, n_data_replies=0,
               last_prompt_tokens=max((t["prompt_tokens"] or 0) for t in turns), sec=round(sum(t["sec"] for t in turns), 1),
               out_cut=sum(1 for t in turns if t["done_reason"] == "length"))
    return res, turns


def run_fix_conversation(case, send, turns, res, log_path):
    """修 bug 專用的新對話（SOP 新版 §5）：G01-01 → 題目 → 題目提到的檔 → 該區陷阱卡 → 檢查卡 → 修改卡 → 錯誤貼回去。"""
    send(CARDS["G01-01"], "G01-01")
    segs = case["segments"]
    for i, sg in enumerate(segs, 1):
        send(wrap(f"題目第 {i}/{len(segs)} 段", sg).replace("來源：", "", 1), f"seg{i}")
    for p in case.get("main_files", list(case.get("files", {}))[:1]):
        if PLAIN:
            send(wrap(f"程式 {p}（cat {p}）", "\n".join(case["files"][p].split("\n")[:60])), f"file:{p}")
        else:
            send(wrap(f"程式 {p}（cat -n）", cat_n(case["files"][p], 1, 60)), f"file:{p}")
    trap = TRAP_BY_AREA.get(case["expect_area"][0])
    if trap:
        send(wrap(trap, CARDS[trap]), f"trap:{trap}")
    start = len(turns)
    if CHECK_CARD:
        send(CHECK_CARD, "CHECK")
    send(FIX_CARD, "FIX")
    return finish(case, turns, res, send, start)


def run_quiz(cli, log_path):
    msgs = []
    for c in ("G01-01", "G01-02", "G01-03"):
        msgs.append({"role": "user", "content": CARDS[c]})
        msgs.append({"role": "assistant", "content": cli.chat(msgs)["text"]})
    msgs.append({"role": "user", "content": "只回答：規格卡有哪幾個編號？資料代號 B1 是什麼？"})
    a = cli.chat(msgs)["text"]
    es = set(re.findall(r"E0[1-6]", a))
    rng = bool(re.search(r"E01[-\d]*\s*[～~至到\-–]\s*E06", a))
    b1 = "第一個錯誤" in a or "first error" in a.lower()
    return {"case": "quiz", "e_codes": len(es), "e_range": rng, "b1_ok": b1,
            "pass": (len(es) >= 5 or rng) and b1, "answer": a[:400]}


# ------------------------------------------------------------------ report
def report(root):
    rows = []
    for f in sorted(glob.glob(os.path.join(root, "**", "summary.json"), recursive=True)):
        rows += json.load(open(f, encoding="utf-8"))
    by = {}
    for r in rows:
        by.setdefault((r["model"], r["ctx"]), []).append(r)
    print("| 模型 | ctx | 測試2 | 了解 3/3 | 收到 | 選對範本 | 繼續卻只回收到 | 有效請求 | 相關請求 | 給出解法 | 說對解法 | **照著改完能用** | 改動處 | 原本找得到 | 改不了 | 丟整檔 | 截斷 | 平均回合 | 秒 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (m, c), rs in sorted(by.items()):
        q = [r for r in rs if r["case"] == "quiz"]
        cs = [r for r in rs if r["case"] != "quiz"]
        n = len(cs) or 1
        nreq = sum(r["n_req"] for r in cs) or 1
        print(f"| {m} | {c} | {sum(r['pass'] for r in q)}/{len(q)} | {sum(r['ack_ok']==3 for r in cs)}/{n} | "
              f"{sum(r['seg_ok']==len(flow_cases.CASE_BY_ID[r['case']]['segments']) for r in cs)}/{n} | "
              f"{sum(r['pick_ok'] for r in cs)}/{n} | {sum(r['only_shou_dao'] for r in cs)}/{sum(r['n_data_replies'] for r in cs)} | "
              f"{sum(r['valid_req'] for r in cs)}/{nreq} | "
              f"{sum(r['relevant_req'] for r in cs)}/{nreq} | {sum(r['patch_round'] is not None for r in cs)}/{n} | "
              f"{sum(r.get('fix_ok', False) for r in cs)}/{n} | **{sum(r.get('works', False) for r in cs)}/{n}** | "
              f"{sum(r.get('n_changes', 0) for r in cs)} | "
              f"{sum(r.get('n_verbatim', 0) for r in cs)}/{sum(r.get('n_changes', 0) for r in cs)} | "
              f"{sum(r.get('applied', {}).get('failed', 0) for r in cs)} | "
              f"{sum(r.get('whole_file', False) for r in cs)}/{n} | {sum(r['truncated'] for r in cs)}/{n} | "
              f"{sum(r['rounds'] for r in cs)/n:.1f} | {sum(r['sec'] for r in cs)/n:.0f} |")


def revalidate(root):
    """讀 *_r0.md 對話紀錄 → 取 G02-01 之後模型的回答 → 套用 → 驗證；更新同資料夾的 summary.json。"""
    for sp in glob.glob(os.path.join(root, "**", "summary.json"), recursive=True):
        d = os.path.dirname(sp)
        summ = json.load(open(sp, encoding="utf-8"))
        for r in summ:
            if r["case"] == "quiz":
                continue
            md = os.path.join(d, f"{r['case']}_r{r.get('rep', 0)}.md")
            s = open(md, encoding="utf-8").read()
            parts = re.split(r"\n######## ", s)
            texts, seen = [], False
            for prt in parts[1:]:
                head, _, body = prt.partition("\n")
                if head.startswith("操作者 [G02-01]"):
                    seen = True
                elif seen and head.startswith("模型"):
                    texts.append(body.strip())
            case = flow_cases.CASE_BY_ID[r["case"]]
            r["n_changes"], r["n_verbatim"], r["whole_file"] = explicit_score(case, texts)
            files_after, st = flow_apply.apply(case, texts)
            ok, checks = flow_apply.validate(case, files_after, build=BUILD)
            r.update(applied=st, works=ok, checks=[[c[0], c[1], c[2]] for c in checks])
        json.dump(summ, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("revalidated", sp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--model")
    ap.add_argument("--ctx", default="4096,8192")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--max-rounds", type=int, default=6)
    ap.add_argument("--only", default="")
    ap.add_argument("--server-log", default="")
    ap.add_argument("--out", default="out/flow")
    ap.add_argument("--cont", default="繼續", help="資料區塊後的最後一行（A/B 測試用）")
    ap.add_argument("--report")
    ap.add_argument("--proactive", action="store_true")
    ap.add_argument("--fix-card", help="修改卡檔案（G02-02 草稿）")
    ap.add_argument("--fix-after", type=int, default=1)
    ap.add_argument("--feedback", type=int, default=0)
    ap.add_argument("--check-card")
    ap.add_argument("--fix-only", action="store_true")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--build", action="store_true", help="改完用 pico-sdk 實際編譯（要 /workspace/pico-sdk）")
    ap.add_argument("--revalidate", help="重新解析某個輸出資料夾的對話紀錄，套用修改並驗證")
    ap.add_argument("--override", action="append", default=[], help="ID=檔案：用檔案內容取代那張卡（A/B 測試）")
    a = ap.parse_args()
    global PROACTIVE, BUILD, FIX_AFTER, FIX_CARD, FEEDBACK, CHECK_CARD, FIX_ONLY, PLAIN
    PROACTIVE = a.proactive
    if a.fix_card:
        FIX_CARD = open(a.fix_card, encoding="utf-8").read().strip()
        FIX_AFTER = a.fix_after
    BUILD = a.build
    FEEDBACK = a.feedback
    FIX_ONLY = a.fix_only
    PLAIN = a.plain
    if a.check_card:
        CHECK_CARD = open(a.check_card, encoding='utf-8').read().strip()
    if a.revalidate:
        return revalidate(a.revalidate)
    for ov in a.override:
        cid, _, path = ov.partition("=")
        CARDS[cid] = open(path, encoding="utf-8").read().strip()
        print(f"override {cid} ← {path} ({len(CARDS[cid])} 字)")
    if a.report:
        return report(a.report)
    cases = [c for c in flow_cases.CASES if not a.only or c["id"] in a.only.split(",")]
    for ctx in [int(x) for x in a.ctx.split(",")]:
        out = os.path.join(a.out, f"ctx{ctx}"); os.makedirs(out, exist_ok=True)
        cli = Client(a.base_url, a.model, ctx, a.temperature)
        summary = []
        for rep in range(a.repeat):
            if not FIX_ONLY:
                q = run_quiz(cli, a.server_log); q.update(model=a.model, ctx=ctx, rep=rep); summary.append(q)
                print(f"[{a.model} ctx{ctx}] quiz pass={q['pass']}", flush=True)
            else:
                print(f"[{a.model} ctx{ctx}] fix-only", flush=True)
            for case in cases:
                try:
                    res, turns = run_case(cli, case, a.max_rounds, a.server_log, a.cont)
                except Exception as e:  # noqa: BLE001
                    print(f"  {case['id']}: ERROR {e}", flush=True); continue
                res.update(model=a.model, ctx=ctx, rep=rep)
                files_after = res.pop("_files_after", {})
                summary.append(res)
                with open(os.path.join(out, f"{case['id']}_r{rep}_改完.txt"), "w", encoding="utf-8") as f:
                    f.write(f"套用：{res['applied']}\n驗證：{res['checks']}\n")
                    for fp, txt in files_after.items():
                        f.write(f"\n===== {fp}\n{txt}\n")
                with open(os.path.join(out, f"{case['id']}_r{rep}.md"), "w", encoding="utf-8") as f:
                    for t in turns:
                        f.write(f"\n\n######## 操作者 [{t['kind']}]\n{t['user']}\n\n######## 模型 "
                                f"(prompt={t['prompt_tokens']} out={t['out_tokens']} {t['sec']}s"
                                f"{' TRUNCATED' if t['truncated'] else ''} {t['done_reason']})\n{t['text']}\n")
                print(f"  {case['id']}: pick={res['pick']}({'ok' if res['pick_ok'] else 'NG'}) ack={res['ack_ok']}/3 "
                      f"seg={res['seg_ok']} reqs={res['n_req']} rel={res['relevant_req']} patch@{res['patch_round']} "
                      f"FIX={'OK' if res['fix_ok'] else 'NG'}({res['fix_hits']}/{len(case.get('solution_checks', []))}) "
                      f"改完能用={'OK' if res['works'] else 'NG'} 套用={res['applied']} "
                      f"trunc={res['truncated']} {res['sec']}s", flush=True)
        json.dump(summary, open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
