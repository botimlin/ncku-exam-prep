#!/usr/bin/env python3
"""run.py — prompt-card stress-test harness (stdlib only; PyYAML optional).

Talks to any OpenAI-compatible /v1/chat/completions endpoint (vLLM, llama.cpp server, Ollama /v1).
Cards are parsed at runtime from ../cards/*.md by their 【…｜…】 title line; cases reference cards by
file glob + title substring and fill the {{…}} blanks. See README.md for the case format.

Typical:
  python3 run.py --base-url http://localhost:8000/v1 --model Qwen/Qwen2.5-7B-Instruct \
      --temperature 0,0.7 --repeat 3 --max-context 8192 --paste-limit 4000 --out out/qwen7b
  python3 run.py --list-cards                 # card parse report
  python3 run.py --validate-cases             # golden answers must pass, a dummy answer must fail
  python3 run.py --dry-run --out out/prompts  # render every prompt to text files, no model calls
  python3 run.py --merge out/a out/b --out out/all   # one report over several runs
"""
import argparse, collections, datetime, fnmatch, glob, json, os, re, sys, threading, time, unicodedata
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import yaml  # optional
except ImportError:
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR = os.path.normpath(os.path.join(HERE, "..", "cards"))
MATERIAL_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))  # 成大上機考/
CARD_BUDGET = 1200  # chars per card (prompt工具包/README.md)

# ============================================================ cards
TITLE_RE = re.compile(r"^\s*【([^｜】\n]+)｜([^】\n]*)】")
BLANK_RE = re.compile(r"\{\{(.*?)\}\}", re.S)
TASK_EN_RE = re.compile(r"^\s*Task\s*\((?:EN|English)\)\s*[:：]", re.I)
TASK_ZH_RE = re.compile(r"^\s*任務\s*[:：]")
EN_MARK_RE = re.compile(r"^\s*[#>*\-\s]*[【\[(（]?\s*(?:English(?: version| instructions?| variant)?|EN(?: version)?)\s*[】\])）]?\s*[:：]?\s*$", re.I)


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s)).lower()


class Card:
    def __init__(self, file, title_line, text, line):
        self.file, self.title_line, self.text, self.line = file, title_line, text, line
        m = TITLE_RE.match(title_line)
        self.title = title_line[:m.end()].strip() if m else title_line.strip()
        self.kind = m.group(1).strip() if m else "?"
        parts = [p.strip() for p in (m.group(2) if m else "").split("｜")]
        self.topic = parts[0] if parts else ""
        self.name = parts[1] if len(parts) > 1 else ""
        nm = re.search(r"(\d+)\s*/\s*(\d+)", self.topic)
        self.n, self.N = (int(nm.group(1)), int(nm.group(2))) if nm else (None, None)
        self.blanks = BLANK_RE.findall(text)
        self.en_block = None
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            if i > 0 and EN_MARK_RE.match(ln):
                self.en_block = (i, lines[0] + "\n" + "\n".join(lines[i + 1:]).strip())
                break
        self.has_task_en = any(TASK_EN_RE.match(ln) for ln in lines)

    @property
    def key(self):
        return f"{self.file} › {self.title}"

    def variant(self, v):
        """card = exactly as written; zh = drop the 'Task (EN)' line / English block; en = English
        instruction instead of the Chinese 任務 line (None if the card has no English part)."""
        lines = self.text.split("\n")
        if v in ("card", None, ""):
            return self.text
        if v == "zh":
            if self.en_block:
                return "\n".join(lines[:self.en_block[0]]).rstrip()
            return "\n".join(l for l in lines if not TASK_EN_RE.match(l))
        if v == "en":
            if self.en_block:
                return self.en_block[1]
            if self.has_task_en:
                return "\n".join(l for l in lines if not TASK_ZH_RE.match(l))
            return None
        raise ValueError(f"unknown variant {v}")


def parse_cards(cards_dir=CARDS_DIR):
    cards, problems = [], []
    for path in sorted(glob.glob(os.path.join(cards_dir, "*.md"))):
        fn = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
        chunks, cur, start, fence = [], [], 1, False
        for i, ln in enumerate(lines, 1):
            if ln.strip().startswith("```"):
                fence = not fence
            if not fence and ln.strip() == "---":
                chunks.append((start, cur)); cur, start = [], i + 1
                continue
            cur.append(ln)
        chunks.append((start, cur))
        if fence:
            problems.append(f"{fn}: unbalanced ``` fence")
        found = 0
        for ci, (st, ch) in enumerate(chunks):
            text = "\n".join(ch).strip()
            if not text:
                continue
            titles = [j for j, ln in enumerate(ch) if TITLE_RE.match(ln)]
            first = next(j for j, ln in enumerate(ch) if ln.strip())
            if not titles:
                if ci > 0:
                    problems.append(f"{fn}:{st}: block between --- has no 【…｜…】 title (starts: {ch[first].strip()[:40]!r})")
                continue
            if titles[0] != first:
                problems.append(f"{fn}:{st + titles[0]}: title is not the first line of its block")
            if len(titles) > 1:
                problems.append(f"{fn}:{st + titles[1]}: two titles in one block (missing --- ?)")
            body = "\n".join(ch[titles[0]:]).strip()
            c = Card(fn, ch[titles[0]].strip(), body, st + titles[0])
            cards.append(c); found += 1
        if not found:
            problems.append(f"{fn}: no cards found")
        # N/N consistency per topic prefix
        by_topic = collections.defaultdict(list)
        for c in cards:
            if c.file == fn and c.N:
                by_topic[re.sub(r"\s*\d+\s*/\s*\d+.*", "", c.topic)].append(c)
        for t, cs in by_topic.items():
            Ns = {c.N for c in cs}
            if len(Ns) > 1 or (Ns and max(Ns) != len(cs)):
                problems.append(f"{fn}: topic '{t}' numbering n/N inconsistent ({len(cs)} cards, N={sorted(Ns)})")
    seen = collections.Counter(norm(c.title) for c in cards)
    for t, k in seen.items():
        if k > 1:
            problems.append(f"duplicate title ×{k}: {t}")
    return cards, problems


def resolve_card(spec, cards):
    """spec: {file, title, kind} | "file::title" | list of those (first that resolves wins)."""
    cands = spec if isinstance(spec, list) else [spec]
    for c in cands:
        if isinstance(c, str):
            f, _, t = c.partition("::")
            c = {"file": f or "*", "title": t}
        fpat, title, kind = c.get("file", "*"), c.get("title", ""), c.get("kind")
        hits = [k for k in cards if fnmatch.fnmatch(k.file, fpat) and norm(title) in norm(k.title)
                and (not kind or kind in k.kind)]
        if hits:
            return hits[0], (len(hits) > 1)
    return None, False


# ============================================================ cases
class CaseError(Exception):
    pass


def load_cases(pattern):
    files = sorted(glob.glob(pattern))
    if not files and pattern.endswith(".yaml"):
        files = sorted(glob.glob(pattern[:-5] + ".json"))
    if any(f.endswith((".yaml", ".yml")) for f in files) and yaml is None:
        alt = sorted(glob.glob(os.path.join(HERE, "cases_json", "*.json")))
        print("[info] PyYAML not installed → using cases_json/*.json", file=sys.stderr)
        files = alt
    cases = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) if f.endswith((".yaml", ".yml")) else json.load(fh)
        for c in (data.get("cases", data) if isinstance(data, dict) else data):
            c["_file"] = os.path.basename(f)
            cases.append(c)
    ids = collections.Counter(c["id"] for c in cases)
    dup = [i for i, n in ids.items() if n > 1]
    if dup:
        raise SystemExit(f"duplicate case ids: {dup}")
    return cases


def read_excerpt(v):
    path = v["file"]
    full = path if os.path.isabs(path) else os.path.join(MATERIAL_ROOT, path)
    if not os.path.exists(full):
        raise CaseError(f"file not found: {path}")
    with open(full, encoding="utf-8") as f:
        lines = f.read().split("\n")
    a, b = 0, len(lines)
    if "lines" in v:
        a, b = v["lines"][0] - 1, v["lines"][1]
    if "start_at" in v:
        idx = [i for i, ln in enumerate(lines) if v["start_at"] in ln]
        if not idx:
            raise CaseError(f"start_at anchor not found in {path}: {v['start_at']!r}")
        a = idx[0]
    if "end_at" in v:
        idx = [i for i, ln in enumerate(lines) if i >= a and v["end_at"] in ln]
        if not idx:
            raise CaseError(f"end_at anchor not found in {path}: {v['end_at']!r}")
        b = idx[0] + 1
    return "\n".join(lines[a:b]), a + 1


def resolve_value(v, data):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v
    if "ref" in v:
        if v["ref"] not in data:
            raise CaseError(f"unknown data ref {v['ref']!r}")
        s = data[v["ref"]]
    elif "file" in v:
        s, first = read_excerpt(v)
    else:
        s = v.get("text", "")
    for d in v.get("drop_lines", []):  # remove every line containing the substring
        if not any(d in ln for ln in s.split("\n")):
            raise CaseError(f"drop_lines anchor not found: {d!r}")
        s = "\n".join(ln for ln in s.split("\n") if d not in ln)
    for inj in v.get("inject", []):
        if inj["find"] not in s:
            raise CaseError(f"inject anchor not found: {inj['find']!r}")
        s = s.replace(inj["find"], inj["replace"], inj.get("count", 1))
    if v.get("strip_comments"):
        s = re.sub(r"[ \t]*//[^\n]*", "", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
    if v.get("number_lines"):  # like `cat -n`, numbered from the excerpt's real first line (or the given int)
        n0 = v["number_lines"] if isinstance(v["number_lines"], int) and v["number_lines"] is not True else \
            (first if "file" in v else 1)
        s = "\n".join(f"{n0 + i:6d}\t{ln}" for i, ln in enumerate(s.split("\n")))
    if v.get("fence"):
        s = f"```{v['fence'] if isinstance(v['fence'], str) else ''}\n{s}\n```"
    return v.get("prefix", "") + s + v.get("suffix", "")


def fill_entries(fills, data):
    out = []
    if isinstance(fills, dict):
        fills = [{"match": re.escape(k), "value": v} for k, v in fills.items()]
    for i, e in enumerate(fills or []):
        if not isinstance(e, dict) or not ({"value", "match", "name"} & set(e)):
            e = {"value": e}
        val = resolve_value(e.get("value"), data)
        out.append({"match": e.get("match"), "value": val, "name": e.get("name", f"fill{i}"),
                    "label": e.get("label", ""), "data": e.get("data", True)})
    return out


def blank_default(inner, default):
    """Value for a blank no fill matched — what a student would type without thinking:
    paste slots ({{貼…}}, {{…}}) → `default`; {{例如 X}} → X; {{a / b}} → a; {{2.2.0}} → 2.2.0."""
    t = inner.strip()
    if not t or t.startswith("貼") or t in ("…", "...") or t.startswith("…"):
        return default
    if t.startswith("例如"):
        return t[2:].strip()
    if " / " in t:
        return t.split(" / ")[0].strip()
    return t


def fill_card(text, entries, default, warnings):
    used = [False] * len(entries)

    def repl(m):
        inner = m.group(1)
        ls = text.rfind("\n", 0, m.start()) + 1
        prefix = text[ls:m.start()]
        if not prefix.strip():  # label is the previous non-empty line, e.g. "[第一個 error 前後 10 行]"
            prev = text[:ls].rstrip("\n").split("\n")
            prefix = next((l for l in reversed(prev) if l.strip()), "")
        label = prefix.strip() + " | " + inner
        for i, e in enumerate(entries):
            if not used[i] and e["match"] and re.search(e["match"], label, re.I):
                used[i] = True; return e["value"]
        for i, e in enumerate(entries):
            if not used[i] and not e["match"]:
                used[i] = True; return e["value"]
        val = blank_default(inner, default)
        if val == default:
            warnings.append(f"unfilled blank {label[-40:]!r} → {default!r}")
        return val
    out = BLANK_RE.sub(repl, text)
    for i, e in enumerate(entries):
        if not used[i]:
            warnings.append(f"fill '{e['name']}' (match={e['match']!r}) matched no blank → appended at end")
            out += f"\n\n{e['label']}\n{e['value']}".rstrip() if e["label"] else f"\n\n{e['value']}"
    return out


class Built:
    """A case rendered into concrete messages for one card variant."""
    def __init__(self):
        self.steps = []        # [{"user": str, "assistant": str|None, "card": Card|None}]
        self.card = None       # final card
        self.corpus = []       # pasted data (grounding source)
        self.data = {}
        self.warnings = []
        self.ambiguous = False


def build_case(case, cards, variant="card", paste_limit=None):
    b = Built()
    for k, v in (case.get("data") or {}).items():
        b.data[k] = resolve_value(v, b.data)
    default = case.get("default_fill", "（無）")
    steps = list(case.get("turns") or []) + [dict(case, _final=True)]
    pad = case.get("pad")
    for si, st in enumerate(steps):
        final = st.get("_final", False)
        entries = fill_entries(st.get("fills"), b.data)
        card = None
        if st.get("card"):
            card, amb = resolve_card(st["card"], cards)
            if card is None:
                raise CaseError(f"CARD_MISSING: {st['card']}")
            b.ambiguous |= amb and final
            text = card.variant(variant)
            if text is None:
                raise CaseError("NO_VARIANT")
            body = fill_card(text, entries, default, b.warnings)
        else:
            body = "\n\n".join(e["value"] for e in entries)
        user = (st.get("before", "") + body + st.get("after", "")) if card or entries else st.get("user", "")
        if st.get("user") and (card or entries):
            user = user + "\n\n" + st["user"]
        if final and pad:
            target = pad.get("to_chars", 3800)
            if isinstance(target, str) and target.startswith("paste_limit"):
                off = int(target[len("paste_limit"):] or 0)
                target = (paste_limit + off) if paste_limit else pad.get("default_chars", 3800)
            deficit = int(target) - len(user)
            if deficit > 0:
                filler_src = resolve_value(pad["filler"], b.data)
                fl, n = [], 0
                while n < deficit:
                    for ln in filler_src.split("\n"):
                        if n + len(ln) + 1 > deficit:
                            break
                        fl.append(ln); n += len(ln) + 1
                    else:
                        continue
                    break
                filler = "\n".join(fl)
                tgt = next((e for e in entries if e["name"] == pad["fill"]), None)
                if tgt is None:
                    raise CaseError(f"pad.fill {pad['fill']!r} not a fill name")
                tgt["value"] = (filler + "\n" + tgt["value"]) if pad.get("position", "before") == "before" \
                    else (tgt["value"] + "\n" + filler)
                body =fill_card(card.variant(variant), entries, default, []) if card else "\n\n".join(e["value"] for e in entries)
                user = st.get("before", "") + body + st.get("after", "")
                if st.get("user"):
                    user += "\n\n" + st["user"]
        for e in entries:
            if e["data"] and e["value"].strip():
                b.corpus.append(e["value"])
        if st.get("user") and not card:
            b.corpus.append(st["user"])
        if card and card.kind.startswith("參考"):
            b.corpus.append(card.variant(variant) or card.text)
        b.steps.append({"user": user, "assistant": None if final else st.get("assistant"), "card": card})
        if final:
            b.card = card
    return b


# ============================================================ checks
EVID_RE = re.compile(r"(?:證據|依據|出處|原文|[Ee]vidence|[Qq]uote)\s*[:：]\s*((?:[「『“\"`][^」』”\"`\n]{1,400}[」』”\"`]\s*[、,，;；及和]?\s*)+)")
QUOTE_RE = re.compile(r"[「『“\"`]([^」』”\"`\n]{1,400})[」』”\"`]")  # 反引號 `…` 也算逐字引用
FENCE_RE = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.S)
SIMPLIFIED = set("这们个为说时码数据题错误应该将对设计还过实现问务样处与关键线输读写执锁断满载变环检测验调试优连传递级缓区节点")
ABSENT_DEFAULT = ["資料中沒有"]
CATEGORY = {"regex": "format", "not_regex": "format", "max_chars": "format", "min_chars": "format",
            "max_lines": "format", "max_code_block_lines": "format", "no_full_dump": "format",
            "patch_format": "format", "card_slots": "format", "numbered_items": "format",
            "not_empty": "format", "no_simplified": "format", "answer_field": "format",
            "evidence_grounded": "grounding", "absent": "grounding", "not_absent": "grounding",
            "identifiers_subset": "grounding",
            "contains_any": "correctness", "contains_all": "correctness", "not_contains": "correctness",
            "k_of": "correctness", "rank_first": "correctness", "field_matches": "correctness",
            "choice": "correctness", "table_cell": "correctness", "table_rows": "format"}
FIELD_PAREN = r"(?:\s*[（(][^）)\n]*[）)])?"  # 欄位名後面照抄卡片的（說明）也算
GLOBAL_CHECKS = [{"type": "not_empty"}, {"type": "no_simplified", "max": 4}]


def nq(s):
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s`*]+", "", s)


def _hit(resp, item, icase=True):
    if isinstance(item, str) and item.startswith("re:"):
        return re.search(item[3:], resp, re.I | re.M if icase else re.M) is not None
    return (item.lower() in resp.lower()) if icase else (item in resp)


def collect_quotes(resp, extra_fields=()):
    """Evidence quotes: 「…」 after 證據/Evidence/… (or extra field names), plus quotes in a markdown
    table column whose header contains 證據 / evidence."""
    quotes = []
    for m in EVID_RE.finditer(resp):
        quotes += QUOTE_RE.findall(m.group(1))
    for f in extra_fields:
        for m in re.finditer(re.escape(f) + r"\s*[:：]\s*(.+)", resp):
            quotes += QUOTE_RE.findall(m.group(1))
    rows = md_table(resp)
    if rows:
        hdr = rows[0]
        cols = [i for i, h in enumerate(hdr) if re.search(r"證據|[Ee]vidence", h)]
        for rw in rows[1:]:
            for i in cols:
                if i < len(rw):
                    cell = re.sub(r"^證據\s*[:：]\s*", "", rw[i])
                    found = QUOTE_RE.findall(cell)
                    if not found and len(nq(cell)) >= 4 and not re.search(r"資料中沒有|看不到|無相關|^無$", cell):
                        found = [cell.strip()]  # 證據欄沒加「」：整格當引用
                    quotes += found
    if not quotes:  # 沒寫「證據：」標籤但有用「…」引用原文（≥ 8 字）也算
        quotes = [q for q in re.findall(r"「([^」\n]{8,400})」", resp)]
    seen, out = set(), []
    for q in quotes:
        if q not in seen:
            seen.add(q); out.append(q)
    return out


def card_slot_labels(card_text):
    """Labels of the card's fixed output format: lines after '…格式…：' / '只輸出這 4 段：' / 'Output:'
    up to a blank line, '範例…', the data delimiter, or a long instruction sentence."""
    out, inblock = [], False
    for ln in card_text.split("\n")[1:]:
        s = ln.strip()
        if not inblock:
            if (re.search(r"(格式|[Ff]ormat)[^。]*[:：]\s*$", s) or
                    (re.search(r"(輸出|[Oo]utput)[^。：:]{0,16}[:：]\s*$", s) and len(s) <= 30)):
                inblock = True
            continue
        if re.match(r"^(範例|例|[Ee]xample)", s) or s.startswith("<<<"):
            break
        if not s or "{{" in s:
            if out:
                break
            continue
        if s.startswith("|"):
            continue
        numbered = re.match(r"^\d+[.、)]\s*", s) is not None
        s = re.sub(r"^([-*•]|\d+[.、)])\s*", "", s)
        brackets = re.findall(r"【([^】]+)】", s)
        s2 = re.sub(r"【[^】]+】", "", s)
        has_colon = re.search(r"[:：]", s2) is not None
        rest = re.split(r"[:：]", s2, 1)[1].strip() if has_colon else ""
        if not numbered and not has_colon:
            continue
        if not numbered and len(rest) > 24 and not rest.startswith(("|", "[")):
            break  # an instruction sentence, not a slot
        lab = re.split(r"[（(，,：:]", s2)[0].strip()
        out += [x for x in brackets if len(x) <= 12]
        if 1 <= len(lab) <= 16:
            out.append(lab)
    return out


def card_options(card_text):
    """Closed-choice option lists in a card: '類別：A 找不到 SDK　B cache 殘留 …' (full-width-space
    separated) or a label line followed by lines 'A …', 'B …'. Returns [(label, {letter: desc})]."""
    groups, lines = [], card_text.split("\n")
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*([^\s:：|（(]{1,10})(?:\s*[（(][^）)\n]*[）)])?\s*[:：]\s*(.*)$", ln)  # 標籤後可帶（說明）
        if not m:
            continue
        opts = {}
        for part in re.split(r"[　]+", m.group(2)):
            mm = re.match(r"^\s*([A-Z])\s+(.+?)\s*$", part)
            if mm:
                opts[mm.group(1)] = mm.group(2)
        if len(opts) < 3 and not m.group(2).strip():
            j = i + 1
            while j < len(lines) and re.match(r"^\s*([A-Z])\s+\S", lines[j]):
                mm = re.match(r"^\s*([A-Z])\s+(.+?)\s*$", lines[j]); opts[mm.group(1)] = mm.group(2); j += 1
        if len(opts) >= 3:
            groups.append((m.group(1), opts))
    return groups


def md_table(resp):
    rows = []
    for ln in resp.split("\n"):
        s = ln.strip()
        if s.startswith("|") and s.count("|") >= 3 and not re.match(r"^\|[\s:|-]+\|?$", s):
            rows.append([c.strip() for c in s.strip("|").split("|")])
    return rows


def run_check(chk, resp, ctx):
    t = chk["type"]
    r = {"type": t, "category": chk.get("category", CATEGORY.get(t, "correctness")),
         "name": chk.get("name", t), "passed": False, "skipped": False, "detail": ""}
    if chk.get("if_card") and not (ctx["card"] and re.search(chk["if_card"], ctx["card"].text)):
        r["skipped"], r["detail"] = True, f"card does not ask for it (if_card /{chk['if_card']}/)"
        return r
    icase = chk.get("ignore_case", True)
    if t in ("regex", "not_regex", "answer_field", "field_matches", "choice", "rank_first"):
        # 模型常把答案寫在「標籤：」的下一行（或用 - 條列）→ 接回同一行再比對
        resp = re.sub(r"([:：])[ \t]*\n[ \t]*(?:[-*•][ \t]*)?(?=\S)", r"\1 ", resp)
        if t in ("regex", "not_regex"):
            # 模型照抄卡片欄位名後面的（說明）→ 比對前拿掉，例如「符合預期（只寫是或否）：否」
            resp = re.sub(r"[（(][^）)\n]{0,80}[）)]\s*(?=[:：])", "", resp)
    code_free = FENCE_RE.sub("", resp)
    if t == "not_empty":
        r["passed"] = bool(resp.strip())
    elif t == "regex":
        pats = chk["pattern"] if isinstance(chk["pattern"], list) else [chk["pattern"]]
        miss = [p for p in pats if not re.search(p, resp, re.M | (re.I if icase else 0))]
        r["passed"], r["detail"] = not miss, (f"missing /{miss[0]}/" if miss else "")
    elif t == "not_regex":
        pats = chk["pattern"] if isinstance(chk["pattern"], list) else [chk["pattern"]]
        hit = [m.group(0) for p in pats for m in [re.search(p, resp, re.M | (re.I if icase else 0))] if m]
        r["passed"], r["detail"] = not hit, (f"found {hit[0]!r}" if hit else "")
    elif t == "max_chars":
        r["passed"], r["detail"] = len(resp) <= chk["max"], f"{len(resp)} chars (max {chk['max']})"
    elif t == "min_chars":
        r["passed"], r["detail"] = len(resp) >= chk["min"], f"{len(resp)} chars (min {chk['min']})"
    elif t == "max_lines":
        n = len([l for l in resp.split("\n") if l.strip()])
        r["passed"], r["detail"] = n <= chk["max"], f"{n} non-empty lines (max {chk['max']})"
    elif t == "max_code_block_lines":
        blocks = [len(b.strip("\n").split("\n")) for b in FENCE_RE.findall(resp)]
        mx = max(blocks) if blocks else 0
        r["passed"], r["detail"] = mx <= chk["max"], f"longest code block {mx} lines (max {chk['max']})"
    elif t == "no_full_dump":
        minlen, mx = chk.get("min_line_len", 12), chk.get("max_copied_lines", 10)
        src = set()
        for c in ctx["corpus"]:
            for ln in c.split("\n"):
                s = nq(ln)
                if len(s) >= minlen:
                    src.add(s)
        got = {nq(l) for l in resp.split("\n")} & src
        r["passed"], r["detail"] = len(got) <= mx, f"{len(got)} data lines copied verbatim (max {mx})"
    elif t == "patch_format":
        before = len(re.findall(r"修改前|改前|[Bb]efore\s*[:：]", resp))
        after = len(re.findall(r"修改後|改後|[Aa]fter\s*[:：]", resp))
        need_loc = chk.get("require_location", "auto")
        if need_loc == "auto":
            need_loc = bool(ctx["card"] and "行號" in ctx["card"].text)
        loc_ok = bool(re.search(r"[\w./-]+\.(?:c|h|cpp|hpp|py|txt|cmake|pio|S|s|xml|ya?ml|sh)`?\s*[:：]\s*\d+|第\s*\d+\s*行|[Ll]ine\s*\d+|行號\s*[:：]\s*\d+|^\s*\d{1,5}(\t| {2,})\S", resp, re.M))  # 程式碼區塊裡 cat -n 的行號也算
        mxp = chk.get("max_patches", 3)
        ok = before >= 1 and after >= 1 and (loc_ok or not need_loc) and before <= mxp
        r["passed"] = ok
        r["detail"] = f"修改前×{before} 修改後×{after} location={'ok' if loc_ok else 'missing'}{'(required)' if need_loc else ''} max_patches={mxp}"
    elif t == "card_slots":
        labels = chk.get("labels") or (card_slot_labels(ctx["card"].text) if ctx["card"] else [])
        if not labels:
            r["skipped"], r["detail"] = True, "card has no recognisable output-format block"
        else:
            nr = nq(resp)
            miss = [l for l in labels if nq(l) not in nr and nq(l)[:4] not in nr]
            frac = 1 - len(miss) / len(labels)
            need = chk.get("min_fraction", 0.8)
            r["passed"] = frac >= need
            r["detail"] = f"{len(labels) - len(miss)}/{len(labels)} slots present (need {need:.0%})" + (f"; missing: {', '.join(miss[:6])}" if miss else "")
    elif t == "numbered_items":
        nums = {int(m) for m in re.findall(r"^\s*(?:#+\s*)?\**\s*(\d{1,2})\s*[.、)）]", code_free, re.M)}
        r["passed"], r["detail"] = len(nums) >= chk["min"], f"{len(nums)} numbered items (min {chk['min']})"
    elif t == "no_simplified":
        bad = [ch for ch in code_free if ch in SIMPLIFIED]
        r["passed"], r["detail"] = len(bad) <= chk.get("max", 4), f"{len(bad)} simplified-only chars {''.join(bad[:10])}"
    elif t == "evidence_grounded":
        quotes = collect_quotes(resp, chk.get("fields", []))
        # 卡片自己的佔位字（例如表頭「證據：「原文」」）被模型照抄時不算引用
        card_nq = nq(ctx["card"].text) if ctx["card"] else ""
        quotes = [q for q in quotes if not (card_nq and nq(q) and nq(q) in card_nq and len(nq(q)) <= 12)]
        minq = chk.get("min_quotes", "auto")
        if minq == "auto":
            minq = 1 if (ctx["card"] and "證據" in ctx["card"].text) else 0
        corpus = nq("\n".join(ctx["corpus"]))
        bad = []
        for q in quotes:
            q = q.strip().rstrip("。.，,；;、 ")  # 結尾標點差異不算錯
            parts = [p for p in re.split(r"…+|\.{3,}|⋯", q) if len(nq(p)) >= 2]
            if any(nq(p) not in corpus for p in parts):
                # 省略中間一段（沒用 …）也算：依標點切段，每段都在原文裡就接受
                sub = [x for x in re.split(r"[，,；;：:、。（）()\s]+", q) if len(nq(x)) >= 3]
                if not sub or any(nq(x) not in corpus for x in sub):
                    bad.append(q)
        if not quotes and not minq:
            r["passed"], r["detail"] = True, "no evidence quotes (none required)"
        else:
            r["passed"] = len(bad) <= chk.get("max_bad", 0) and len(quotes) >= minq
            r["detail"] = f"{len(quotes)} quotes, {len(bad)} not in data (min {minq})" + (f"; e.g. 「{bad[0][:60]}」" if bad else "")
    elif t in ("absent", "not_absent"):
        phrases = chk.get("phrases", ABSENT_DEFAULT)
        found = [p for p in phrases if p in resp]
        r["passed"] = bool(found) if t == "absent" else not found
        r["detail"] = f"found {found}" if found else f"none of {phrases}"
    elif t == "identifiers_subset":
        corpus = "\n".join(ctx["corpus"])
        ids = sorted(set(re.findall(chk["pattern"], resp)))
        bad = [i for i in ids if i not in corpus]
        r["passed"], r["detail"] = not bad, f"{len(ids)} identifiers, invented: {bad[:5]}"
    elif t == "contains_any":
        hit = [i for i in chk["items"] if _hit(resp, i, icase)]
        r["passed"], r["detail"] = bool(hit), (f"hit {hit[0]!r}" if hit else f"none of {chk['items'][:6]}")
    elif t == "contains_all":
        miss = [i for i in chk["items"] if not _hit(resp, i, icase)]
        r["passed"], r["detail"] = not miss, (f"missing {miss}" if miss else "all present")
    elif t == "not_contains":
        hit = [i for i in chk["items"] if _hit(resp, i, icase)]
        r["passed"], r["detail"] = not hit, (f"found {hit[0]!r}" if hit else "")
    elif t == "k_of":
        hit = [i for i in chk["items"] if _hit(resp, i, icase)]
        r["passed"], r["detail"] = len(hit) >= chk["k"], f"{len(hit)}/{len(chk['items'])} (need {chk['k']})"
    elif t == "rank_first":  # first numbered item (optionally after a section regex) must mention one of items
        body = code_free
        if chk.get("section"):
            m = re.search(chk["section"], body, re.M)
            body = body[m.end():] if m else body
        rows = md_table(body)
        if len(rows) >= 2:
            first = " ".join(rows[1])
        else:
            m = re.search(r"^\s*(?:#+\s*)?\**\s*(?:1\s*[.、)）]|①|-\s)(.*?)(?=^\s*(?:#+\s*)?\**\s*(?:2\s*[.、)）]|②)|\Z)", body, re.M | re.S)
            first = m.group(1) if m else body[:300]
        hit = [i for i in chk["items"] if _hit(first, i, icase)]
        r["passed"], r["detail"] = bool(hit), f"first item: {first.strip()[:80]!r}"
    elif t in ("answer_field", "field_matches"):
        m = re.search(r"(?:" + chk["field"] + r")" + FIELD_PAREN + r"\s*[:：]\s*(.+)", resp)
        if not m:
            r["detail"] = f"field '{chk['field']}' not found"
        else:
            val = m.group(1).strip()
            r["passed"] = (re.search(chk["regex"], val, re.I) is not None) if "regex" in chk else True
            r["detail"] = f"{chk['field']}: {val[:80]!r}"
    elif t == "choice":  # closed-choice answer; letter resolved from the card text at runtime
        want = chk["option"] if isinstance(chk["option"], list) else [chk["option"]]
        groups = card_options(ctx["card"].text) if ctx["card"] else []
        found = None
        for lab, opts in groups:
            if chk.get("field", "auto") not in ("auto", lab):
                continue
            for letter, desc in opts.items():
                if any(nq(w).lower() in nq(desc).lower() for w in want):
                    found = (lab, letter, desc); break
            if found:
                break
        if not found:
            fb = chk.get("fallback", want)
            hit = [i for i in fb if _hit(resp, i, icase)]
            r["passed"] = bool(hit)
            r["detail"] = "card has no matching option list → fallback keywords: " + (f"hit {hit[0]!r}" if hit else f"none of {fb[:5]}")
        else:
            lab, letter, desc = found
            field = chk.get("field_in_answer", lab)
            m = re.search(r"(?:" + re.escape(field) + r")" + FIELD_PAREN + r"\s*[:：]\s*\**\s*([A-Z])(?![A-Za-z])", resp)
            if m:
                r["passed"] = m.group(1) == letter
                r["detail"] = f"{field}: answered {m.group(1)}, expected {letter} ({desc[:30]})"
            else:
                mv = re.search(r"(?:" + re.escape(field) + r")" + FIELD_PAREN + r"\s*[:：]\s*(.+)", resp)
                ok = bool(mv) and nq(desc)[:6].lower() in nq(mv.group(1)).lower()
                r["passed"] = ok
                r["detail"] = f"{field}: no letter; expected {letter} ({desc[:30]})" + (" — matched by description" if ok else "")
    elif t == "table_cell":  # markdown table: row whose key column matches `key` must have `regex` in column `col`
        rows = md_table(resp)
        kc, col = chk.get("key_col", 0), chk.get("col", 1)
        row = next((rw for rw in rows if len(rw) > kc and re.search(chk["key"], rw[kc], re.I)), None)
        if row is None:
            r["detail"] = f"no table row matching /{chk['key']}/ ({len(rows)} rows)"
        else:
            cell = row[col] if len(row) > col else ""
            r["passed"] = re.search(chk["regex"], cell, re.I) is not None
            r["detail"] = f"row {row[kc][:20]!r} col{col} = {cell[:40]!r} (want /{chk['regex']}/)"
    elif t == "table_rows":
        n = len(md_table(resp))
        mn, mx = chk.get("min", 1), chk.get("max", 10 ** 6)
        r["passed"], r["detail"] = mn <= n <= mx, f"{n} table rows (want {mn}..{mx})"
    else:
        r["skipped"], r["detail"] = True, f"unknown check type {t}"
    return r


def evaluate(case, resp, built, extra=()):
    ctx = {"corpus": built.corpus, "card": built.card}
    checks = list(case.get("checks", []))
    if case.get("global_checks", True):
        checks = GLOBAL_CHECKS + checks
    res = [run_check(c, resp, ctx) for c in checks] + list(extra)
    passed = all(r["passed"] or r["skipped"] for r in res)
    return res, passed


# ============================================================ tokens / context
def is_cjk(ch):
    o = ord(ch)
    return 0x2E80 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF or 0x3000 <= o <= 0x303F


def est_tokens(s, cjk_tpc=1.0, ascii_cpt=3.5):
    cjk = sum(1 for ch in s if is_cjk(ch))
    return int(cjk * cjk_tpc + (len(s) - cjk) / ascii_cpt) + 4


class Tokenizer:
    def __init__(self, args):
        self.args, self.mode, self.lock = args, args.tokenize, threading.Lock()
        self.root = re.sub(r"/v1/?$", "", args.base_url.rstrip("/"))

    def count(self, model, messages):
        a = self.args
        if self.mode in ("auto", "vllm"):
            try:
                j = http_json(self.root + "/tokenize", {"model": model, "messages": messages, "add_generation_prompt": True}, a.timeout)
                if "count" in j:
                    self.mode = "vllm"; return j["count"], "server"
            except Exception:
                if self.mode == "vllm":
                    self.mode = "off"
                elif self.mode == "auto":
                    self.mode = "llamacpp"
        if self.mode == "llamacpp":
            try:
                txt = "\n".join(m["content"] for m in messages)
                j = http_json(self.root + "/tokenize", {"content": txt}, a.timeout)
                return len(j["tokens"]) + 6 * len(messages), "server"
            except Exception:
                self.mode = "off"
        return sum(est_tokens(m["content"], a.cjk_tokens_per_char, a.ascii_chars_per_token) for m in messages) + 3, "estimate"


def fit_context(messages, model, args, tok):
    """Simulate a small web-chat context: drop oldest turns, then cut the head of the last message."""
    info = {"tokens": None, "src": None, "dropped_turns": 0, "head_cut_chars": 0}
    if not args.max_context:
        return messages, info
    budget = args.max_context - args.max_tokens
    msgs = list(messages)
    n, src = tok.count(model, msgs)
    info.update(tokens=n, src=src)
    sys_off = 1 if msgs and msgs[0]["role"] == "system" else 0
    while n > budget and len(msgs) - sys_off > 1 and args.context_policy == "truncate":
        del msgs[sys_off:sys_off + 2]; info["dropped_turns"] += 1
        n, _ = tok.count(model, msgs)
    if n > budget and args.context_policy == "truncate":
        last = msgs[-1]["content"]
        ratio = budget / max(n, 1)
        keep = int(len(last) * ratio * 0.95)
        info["head_cut_chars"] = len(last) - keep
        msgs[-1] = {"role": "user", "content": last[-keep:] if keep > 0 else ""}
        n, _ = tok.count(model, msgs)
    info["tokens_after"] = n
    info["overflow"] = n > budget
    return msgs, info


# ============================================================ HTTP
def http_json(url, body, timeout, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


def chat(args, model, messages, temperature, extra_headers):
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": args.max_tokens, "stream": False}
    if args.top_p is not None:
        body["top_p"] = args.top_p
    if args.seed is not None:
        body["seed"] = args.seed
    body.update(args.extra_body)
    headers = dict(extra_headers)
    if args.api_key:
        headers["Authorization"] = "Bearer " + args.api_key
    last = None
    for attempt in range(args.retries + 1):
        t0 = time.time()
        try:
            j = http_json(args.base_url.rstrip("/") + "/chat/completions", body, args.timeout, headers)
            ch = j["choices"][0]
            msg = ch.get("message") or {}
            raw = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            content = raw
            if args.strip_think:
                content = THINK_RE.sub("", content)
                if "</think>" in content:
                    content = content.split("</think>")[-1]
            return {"raw": raw, "content": content.strip(), "reasoning_chars": len(reasoning) + (len(raw) - len(content)),
                    "finish_reason": ch.get("finish_reason"), "usage": j.get("usage"), "latency": round(time.time() - t0, 2)}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}"
            if e.code < 500 and e.code != 429:
                break
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(last)


# ============================================================ runner
def run_job(job, args, cards, tok):
    case, model, temp, rep, variant = job
    row = {"model": model + (f" [{args.label}]" if args.label else ""), "model_id": model, "label": args.label,
           "cards_dir": args.cards_dir, "case": case["id"], "tags": case.get("tags", []), "temperature": temp, "rep": rep,
           "variant": variant, "status": "ok", "passed": False, "checks": [], "card": None, "warnings": [],
           "time": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        b = build_case(case, cards, variant, args.paste_limit)
    except CaseError as e:
        row["status"] = "no_variant" if str(e) == "NO_VARIANT" else "card_missing" if str(e).startswith("CARD_MISSING") else "case_error"
        row["error"] = str(e)
        return row
    row["card"] = b.card.key if b.card else "(no card)"
    if args.variants and variant != "card":
        row["card"] += f" [{variant}]"
    row["warnings"] = b.warnings + (["card title ambiguous: first match used"] if b.ambiguous else [])
    extra = []
    if args.paste_limit:
        sizes = [len(s["user"]) for s in b.steps]
        over = [i for i, n in enumerate(sizes) if n > args.paste_limit]
        extra.append({"type": "paste_limit", "category": "format", "name": "paste_limit", "skipped": False,
                      "passed": not over, "detail": f"user message sizes {sizes} (limit {args.paste_limit})"})
        if over and args.paste_limit_mode == "skip":
            row.update(status="paste_limit", checks=extra, passed=False)
            return row
    msgs = [{"role": "system", "content": args.system_prompt}] if args.system_prompt else []
    hdr = {"X-Stress-Case": case["id"]} if args.send_case_header else {}
    row["turns"] = []
    try:
        outs = {}  # 整題連續對話：<<TURNk>> 換成第 k 步模型自己的回答
        for i, st in enumerate(b.steps):
            u = st["user"]
            for k, v in outs.items():
                u = u.replace(f"<<TURN{k}>>", v)
            if args.user_suffix:  # 例如 "/no_think"、"Reasoning: low"：模擬學生在訊息最後加一行
                u = u + "\n" + args.user_suffix
            msgs.append({"role": "user", "content": u})
            final = i == len(b.steps) - 1
            if st["assistant"] is not None:
                msgs.append({"role": "assistant", "content": st["assistant"]}); continue
            send, cinfo = fit_context(msgs, model, args, tok)
            hdr2 = dict(hdr, **({"X-Stress-Turn": "final" if final else str(i)} if hdr else {}))
            out = chat(args, model, send, temp, hdr2)
            if final:
                row.update(response=out["content"], raw=out["raw"] if out["raw"] != out["content"] else None,
                           latency=out["latency"], usage=out["usage"], finish_reason=out["finish_reason"],
                           reasoning_chars=out["reasoning_chars"], context=cinfo,
                           messages=send if args.save_prompts else None)
            else:
                row["turns"].append({"assistant": out["content"][:2000], "context": cinfo})
                outs[i] = out["content"]
                b.corpus.append(out["content"])  # 後面的引用可能來自前一步的回答
            msgs.append({"role": "assistant", "content": out["content"]})
    except RuntimeError as e:
        row.update(status="error", error=str(e))
        return row
    ci = row.get("context") or {}
    if args.max_context:
        cut = ci.get("head_cut_chars", 0) or ci.get("overflow")
        extra.append({"type": "context_fit", "category": "context", "name": "context_fit", "skipped": False,
                      "passed": not cut, "detail": f"est {ci.get('tokens')} tok ({ci.get('src')}), dropped {ci.get('dropped_turns')} turns, head cut {ci.get('head_cut_chars')} chars"})
        if ci.get("dropped_turns"):
            row["warnings"].append(f"context: dropped {ci['dropped_turns']} earlier turn(s)")
    if row.get("finish_reason") == "length":
        row["warnings"].append("finish_reason=length (output truncated by max_tokens)")
    row["checks"], row["passed"] = evaluate(case, row["response"], b, extra)
    return row


def parse_list(s, typ=str):
    out = []
    for part in (s or []):
        out += [typ(x.strip()) for x in str(part).split(",") if x.strip()]
    return out


def job_key(model, cid, temp, rep, variant):
    return f"{model}|{cid}|{temp}|{rep}|{variant}"


def cmd_run(args, cards, problems, cases):
    models = parse_list(args.model)
    temps = parse_list(args.temperature, float) or [0.0]
    variants = parse_list(args.variants) or ["card"]
    if not models:
        raise SystemExit("--model is required")
    os.makedirs(args.out, exist_ok=True)
    raw_path = os.path.join(args.out, "raw.jsonl")
    done = set()
    if args.resume and os.path.exists(raw_path):
        for ln in open(raw_path, encoding="utf-8"):
            r = json.loads(ln)
            if r["status"] != "error":
                done.add(job_key(r.get("model_id", r["model"]), r["case"], r["temperature"], r["rep"], r.get("variant", "zh")))
    jobs = [(c, m, t, k, v) for m in models for v in variants for t in temps for k in range(args.repeat)
            for c in cases if job_key(m, c["id"], t, k, v) not in done]
    print(f"{len(cards)} cards parsed ({len(problems)} problems); {len(cases)} cases; {len(jobs)} jobs → {args.out}", file=sys.stderr)
    tok = Tokenizer(args)
    lock = threading.Lock()
    with open(raw_path, "a", encoding="utf-8") as fout, ThreadPoolExecutor(args.concurrency) as ex:
        futs = [ex.submit(run_job, j, args, cards, tok) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            row = f.result()
            with lock:
                fout.write(json.dumps(row, ensure_ascii=False) + "\n"); fout.flush()
            mark = "PASS" if row["passed"] else row["status"].upper() if row["status"] != "ok" else "fail"
            print(f"[{i}/{len(jobs)}] {mark:10s} {row['model'][:28]:28s} t={row['temperature']} {row['case']}", file=sys.stderr)
    write_report([args.out], args.out, cards, problems, cases, args)


# ============================================================ report
ADVICE = {
    "evidence_grounded": "證據引文不是逐字來自資料 → 規則寫「證據必須從 <<<資料>>> 逐字複製，最多 30 字」，few-shot 示範一行正確的「證據：「…」」，並在資料後重述這條規則。",
    "absent": "資料沒有的資訊卻沒回答「資料中沒有」→ 把這條規則放在資料之後重述；給一個「資料中沒有」的範例；把問題改成封閉式（有/沒有）。",
    "not_absent": "資料裡有答案卻回答「資料中沒有」→ 規則太強或資料太長被忽略：縮短資料、把問題放在資料後、要求先引用再回答。",
    "identifiers_subset": "模型編造了資料中沒有的 API/識別字 → 加「只能使用資料中出現的名稱」並要求每個名稱附證據。",
    "card_slots": "輸出缺少卡片規定的欄位 → 固定格式放在資料之後重述、欄位數減少（≤5）、給一個填好的小範例。",
    "numbered_items": "沒有照編號條列 → 在資料後重述「照 1. 2. 3. 編號回答」，減少項目數。",
    "patch_format": "修改沒有用「檔名:行號 / 修改前 / 修改後」格式或一次改太多 → 給 patch 範例、明寫「只改一處」。",
    "max_code_block_lines": "輸出過長的程式碼區塊 → 明寫「不要輸出整份檔案，只輸出要改的行（≤N 行）」。",
    "no_full_dump": "把貼上的程式整份抄回來 → 同上；並把『修改後』限制為單行或幾行。",
    "max_chars": "回答太長 → 限字數（例如 ≤300 字）並放在資料後重述；封閉式任務（選一個/填表）。",
    "max_lines": "回答太長 → 限行數，封閉式任務。",
    "regex": "缺少必要格式字樣 → 固定輸出模板，在資料後重述。",
    "not_regex": "出現禁止的寫法 → 在規則裡明確禁止並說明替代做法。",
    "no_simplified": "輸出簡體字 → 在資料後重述「用繁體中文（台灣用語）回答」；英文版卡片可改善。",
    "not_empty": "空回應 → 檢查 max_tokens / thinking 模式（Qwen3 enable_thinking=false）。",
    "paste_limit": "卡片+資料超過貼上上限 → 拆卡、資料分段貼、刪除卡片中的說明文字。",
    "context_fit": "超過 context，前面被截掉 → 卡片要能單獨成立；指令在資料後重述；開新對話+狀態卡。",
    "contains_any": "答錯/沒抓到關鍵點 → 模型知識不足時在卡片附上對應參考事實（參考卡），或改成分類/勾選題；把可疑處縮小範圍。",
    "contains_all": "答案不完整 → 拆成更小的單一任務；用勾選清單。",
    "not_contains": "出現已知錯誤答案（常見誤解）→ 在參考卡中直接寫出反例（例如「volatile 不能取代鎖」）。",
    "k_of": "關鍵點覆蓋不足 → 用固定欄位逼模型逐項回答。",
    "rank_first": "最可能原因排序錯誤 → 提供症狀→原因對照（參考卡）或要求先引用症狀再排序。",
    "field_matches": "欄位值錯誤 → 封閉式選項（A/B/C）＋證據。",
    "answer_field": "缺少答案欄位 → 固定「答案：」欄位並在資料後重述。",
}


def load_rows(dirs):
    rows = []
    for d in dirs:
        p = os.path.join(d, "raw.jsonl")
        if os.path.exists(p):
            rows += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    return rows


def pct(a, b):
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "–"


def excerpt(s, n=500):
    s = (s or "").strip()
    s = s if len(s) <= n else s[:n] + " …"
    return "\n".join("> " + l for l in s.split("\n"))


def write_report(dirs, out, cards, problems, cases, args=None):
    rows = load_rows(dirs)
    os.makedirs(out, exist_ok=True)
    scored = [r for r in rows if r["status"] in ("ok", "paste_limit")]
    models = sorted({r["model"] for r in rows})
    L = [f"# Prompt-card stress test report", "",
         f"- generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
         f"- runs: {', '.join(dirs)}", f"- rows: {len(rows)} (scored {len(scored)}, errors {sum(r['status'] == 'error' for r in rows)}, "
         f"case errors {sum(r['status'] == 'case_error' for r in rows)}, no variant {sum(r['status'] == 'no_variant' for r in rows)})",
         f"- models: {', '.join(models)}", f"- cases: {len(cases)}; cards parsed: {len(cards)}", ""]
    if args is not None and hasattr(args, "max_context"):
        L += [f"- settings: temperature={args.temperature} repeat={args.repeat} max_context={args.max_context} "
              f"paste_limit={args.paste_limit} max_tokens={args.max_tokens} variants={args.variants} system_prompt={'yes' if args.system_prompt else 'no'}", ""]
    # overall
    L += ["## 1. Overall per model", "", "| model | case pass | format checks | grounding checks | correctness checks | context | mean latency s | mean resp chars |", "|---|---|---|---|---|---|---|---|"]
    for m in models:
        rs = [r for r in scored if r["model"] == m]
        cat = collections.defaultdict(lambda: [0, 0])
        for r in rs:
            for c in r["checks"]:
                if c.get("skipped"):
                    continue
                cat[c["category"]][1] += 1; cat[c["category"]][0] += c["passed"]
        lat = [r["latency"] for r in rs if r.get("latency")]
        rc = [len(r.get("response") or "") for r in rs if r["status"] == "ok"]
        lat_s = f"{sum(lat) / len(lat):.1f}" if lat else "–"
        rc_s = str(sum(rc) // len(rc)) if rc else "–"
        L.append(f"| {m} | {pct(sum(r['passed'] for r in rs), len(rs))} | "
                 + " | ".join(pct(*cat[k]) for k in ("format", "grounding", "correctness", "context"))
                 + f" | {lat_s} | {rc_s} |")
    temps = sorted({r["temperature"] for r in scored})
    if len(temps) > 1:
        L += ["", "### by temperature", "", "| model | " + " | ".join(f"t={t}" for t in temps) + " |", "|---|" + "---|" * len(temps)]
        for m in models:
            L.append(f"| {m} | " + " | ".join(pct(sum(r['passed'] for r in scored if r['model'] == m and r['temperature'] == t),
                                                  sum(1 for r in scored if r['model'] == m and r['temperature'] == t)) for t in temps) + " |")
    # model × card
    L += ["", "## 2. Pass rate per card × model", "", "| card | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    cardkeys = sorted({r["card"] for r in scored if r["card"]})
    for ck in cardkeys:
        L.append(f"| {ck} | " + " | ".join(pct(sum(r['passed'] for r in scored if r['card'] == ck and r['model'] == m),
                                               sum(1 for r in scored if r['card'] == ck and r['model'] == m)) for m in models) + " |")
    # tags
    tags = sorted({t for r in scored for t in r.get("tags", [])})
    L += ["", "## 3. Pass rate per scenario tag × model", "", "| tag | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for tg in tags:
        L.append(f"| {tg} | " + " | ".join(pct(sum(r['passed'] for r in scored if tg in r.get('tags', []) and r['model'] == m),
                                               sum(1 for r in scored if tg in r.get('tags', []) and r['model'] == m)) for m in models) + " |")
    # check types
    L += ["", "## 4. Failures per check type × model (failed / evaluated)", "", "| check type | category | " + " | ".join(models) + " |", "|---|---|" + "---|" * len(models)]
    ctypes = sorted({(c["type"], c["category"]) for r in scored for c in r["checks"]})
    for ct, cg in ctypes:
        cells = []
        for m in models:
            ev = [c for r in scored if r["model"] == m for c in r["checks"] if c["type"] == ct and not c.get("skipped")]
            cells.append(f"{sum(not c['passed'] for c in ev)}/{len(ev)}" if ev else "–")
        L.append(f"| {ct} | {cg} | " + " | ".join(cells) + " |")
    # worst cases
    L += ["", "## 5. Worst cases", ""]
    bycase = collections.defaultdict(list)
    for r in scored:
        bycase[r["case"]].append(r)
    worst = sorted(bycase.items(), key=lambda kv: (sum(r["passed"] for r in kv[1]) / len(kv[1]), kv[0]))[:args.worst if args and hasattr(args, "worst") else 12]
    for cid, rs in worst:
        fails = collections.Counter(c["name"] for r in rs for c in r["checks"] if not c["passed"] and not c.get("skipped"))
        L += [f"### {cid} — pass {pct(sum(r['passed'] for r in rs), len(rs))}", "",
              f"- card: {rs[0]['card']}", f"- tags: {', '.join(rs[0].get('tags', []))}",
              "- per model: " + "; ".join(f"{m}: {pct(sum(r['passed'] for r in rs if r['model'] == m), sum(1 for r in rs if r['model'] == m))}" for m in models if any(r['model'] == m for r in rs)),
              "- failed checks: " + ", ".join(f"{k}×{v}" for k, v in fails.most_common(8))]
        bad = next((r for r in rs if not r["passed"]), None)
        if bad:
            det = [f"`{c['name']}`: {c['detail']}" for c in bad["checks"] if not c["passed"] and not c.get("skipped")]
            L += [f"- example ({bad['model']}, t={bad['temperature']}, rep {bad['rep']}): " + "; ".join(det[:5]), "", excerpt(bad.get("response") or bad.get("error") or "", 600)]
        L.append("")
    # fix suggestions
    L += ["## 6. Card fix suggestions (failures grouped by card)", ""]
    bycard = collections.defaultdict(list)
    for r in scored:
        bycard[r["card"]].append(r)
    for ck, rs in sorted(bycard.items(), key=lambda kv: sum(r["passed"] for r in kv[1]) / len(kv[1])):
        rate = sum(r["passed"] for r in rs) / len(rs)
        fails = collections.Counter(c["type"] for r in rs for c in r["checks"] if not c["passed"] and not c.get("skipped"))
        if not fails:
            continue
        L += [f"### {ck} — pass {pct(sum(r['passed'] for r in rs), len(rs))}", "", "| failure | count | cases | suggestion |", "|---|---|---|---|"]
        for t, n in fails.most_common():
            cs = sorted({r["case"] for r in rs for c in r["checks"] if c["type"] == t and not c["passed"] and not c.get("skipped")})
            L.append(f"| {t} | {n} | {', '.join(cs[:5])}{' …' if len(cs) > 5 else ''} | {ADVICE.get(t, '')} |")
        bym = {m: sum(r['passed'] for r in rs if r['model'] == m) / max(1, sum(1 for r in rs if r['model'] == m)) for m in models if any(r['model'] == m for r in rs)}
        if bym and max(bym.values()) - min(bym.values()) >= 0.5:
            L.append(f"\n- 模型間差異大（{', '.join(f'{m}={v:.0%}' for m, v in bym.items())}）：可能是知識問題而非格式問題 → 補參考事實或改封閉式。")
        if rate < 0.5:
            L.append("- 通過率 < 50%：優先修這張卡。")
        L.append("")
    # maintenance
    L += ["## 7. Harness / case maintenance", ""]
    errs = [r for r in rows if r["status"] in ("case_error", "error")]
    for r in errs[:30]:
        L.append(f"- {r['status']}: {r['case']} ({r['model']}): {r.get('error', '')[:200]}")
    warns = collections.Counter(w for r in rows for w in r.get("warnings", []) if "context" not in w)
    for w, n in warns.most_common(30):
        cs = sorted({r["case"] for r in rows if w in r.get("warnings", [])})
        L.append(f"- warning ×{n}: {w} — {', '.join(cs[:4])}")
    skipped = collections.Counter((r["card"], c["detail"]) for r in scored for c in r["checks"] if c.get("skipped"))
    for (ck, d), n in skipped.most_common(10):
        L.append(f"- skipped check ×{n} on {ck}: {d}")
    used = {r["card"] for r in rows}
    untested = [c.key for c in cards if c.kind.startswith(("提示", "開場")) and c.key not in used]
    if untested:
        L += ["", "Prompt cards not exercised by any case:", ""] + [f"- {k}" for k in untested]
    if problems:
        L += ["", "Card parse problems:", ""] + [f"- {p}" for p in problems]
    over = [c for c in cards if len(c.text) > CARD_BUDGET]
    if over:
        L += ["", f"Cards over the {CARD_BUDGET}-char budget:", ""] + [f"- {c.key}: {len(c.text)} chars" for c in over]
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    summ = {m: {"cases": sum(1 for r in scored if r["model"] == m), "passed": sum(r["passed"] for r in scored if r["model"] == m)} for m in models}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summ, f, ensure_ascii=False, indent=1)
    print(f"report → {os.path.join(out, 'report.md')}", file=sys.stderr)


# ============================================================ utilities
def cmd_list_cards(cards, problems, cases):
    refs = collections.Counter()
    for c in cases:
        for st in (c.get("turns") or []) + [c]:
            if st.get("card"):
                k, _ = resolve_card(st["card"], cards)
                if k:
                    refs[k.key] += 1
    print(f"{'file':24s} {'kind':5s} {'chars':>5s} {'blanks':>6s} {'en':2s} {'cases':>5s}  title")
    for c in cards:
        flag = "!" if len(c.text) > CARD_BUDGET else " "
        print(f"{c.file:24s} {c.kind[:3]:5s} {len(c.text):5d}{flag} {len(c.blanks):6d} {'y' if (c.en_block or c.has_task_en) else '-':2s} {refs[c.key]:5d}  {c.title}")
    files = sorted({c.file for c in cards})
    print(f"\n{len(cards)} cards in {len(files)} files; {sum(len(c.text) > CARD_BUDGET for c in cards)} over {CARD_BUDGET} chars")
    for p in problems:
        print("PROBLEM:", p)


def cmd_validate(cards, cases, args):
    bad = 0
    for c in cases:
        try:
            b = build_case(c, cards, "card", args.paste_limit)
        except CaseError as e:
            print(f"CASE-ERROR {c['id']}: {e}"); bad += 1; continue
        msg = []
        if not c.get("golden"):
            msg.append("no golden answer")
        else:
            res, ok = evaluate(c, c["golden"], b)
            if not ok:
                bad += 1
                msg.append("golden FAILS: " + "; ".join(f"{r['name']}: {r['detail']}" for r in res if not r["passed"] and not r["skipped"]))
        res, ok = evaluate(c, "了解。", b)
        if ok and not c.get("dummy_ok"):
            bad += 1; msg.append("dummy answer '了解。' PASSES (checks too weak)")
        sizes = [len(s["user"]) for s in b.steps]
        w = "; ".join(b.warnings)
        print(f"{'OK ' if not msg else 'BAD'} {c['id']:28s} card={b.card.key if b.card else '-'} sizes={sizes}"
              + (f"\n      {' | '.join(msg)}" if msg else "") + (f"\n      warn: {w}" if w else ""))
    print(f"\n{len(cases)} cases, {bad} problems")
    return bad


def cmd_dry_run(cards, cases, args):
    os.makedirs(args.out, exist_ok=True)
    for c in cases:
        for v in parse_list(args.variants) or ["card"]:
            try:
                b = build_case(c, cards, v, args.paste_limit)
            except CaseError as e:
                print(f"{c['id']} [{v}]: {e}"); continue
            p = os.path.join(args.out, f"{c['id']}.{v}.txt")
            with open(p, "w", encoding="utf-8") as f:
                for i, st in enumerate(b.steps):
                    f.write(f"===== user turn {i + 1} ({len(st['user'])} chars, ~{est_tokens(st['user'])} tok) card={st['card'].key if st['card'] else '-'}\n{st['user']}\n")
                    if st["assistant"] is not None:
                        f.write(f"===== assistant (canned)\n{st['assistant']}\n")
            print(f"{c['id']} [{v}] sizes={[len(s['user']) for s in b.steps]} → {p}")


def cmd_export_json(pattern):
    if yaml is None:
        raise SystemExit("PyYAML needed for --export-json")
    od = os.path.join(HERE, "cases_json"); os.makedirs(od, exist_ok=True)
    for f in sorted(glob.glob(pattern)):
        with open(f, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        o = os.path.join(od, os.path.splitext(os.path.basename(f))[0] + ".json")
        with open(o, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print("wrote", o)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", action="append", help="repeatable or comma list")
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    ap.add_argument("--cases", default=os.path.join(HERE, "cases", "*.yaml"))
    ap.add_argument("--only", help="regex on case id / tag")
    ap.add_argument("--cards-dir", default=CARDS_DIR, help="non-recursive *.md; cards/_舊版 for the old set")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--temperature", action="append", help="e.g. 0,0.7")
    ap.add_argument("--variants", action="append", help="card,zh,en — card = as written; zh = without the 'Task (EN)' line; en = English task line instead of 任務")
    ap.add_argument("--label", default="", help="tag rows, e.g. new / old (A/B of two card sets via --cards-dir)")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--top-p", type=float)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--extra-body", default="{}", help='JSON merged into the request, e.g. \'{"chat_template_kwargs":{"enable_thinking":false}}\'')
    ap.add_argument("--user-suffix", default="", help="append this line to every user message (e.g. /no_think)")
    ap.add_argument("--system-prompt", default="", help="simulate the exam web-chat's hidden system prompt")
    ap.add_argument("--max-context", type=int, default=0, help="simulated context window (tokens); 0 = off")
    ap.add_argument("--context-policy", choices=["truncate", "flag"], default="truncate")
    ap.add_argument("--tokenize", choices=["auto", "vllm", "llamacpp", "off"], default="auto", help="use server /tokenize when available")
    ap.add_argument("--cjk-tokens-per-char", type=float, default=1.0)
    ap.add_argument("--ascii-chars-per-token", type=float, default=3.5)
    ap.add_argument("--paste-limit", type=int, default=0, help="max chars of one user message; 0 = off")
    ap.add_argument("--paste-limit-mode", choices=["skip", "run"], default="skip")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--no-strip-think", dest="strip_think", action="store_false")
    ap.add_argument("--save-prompts", action="store_true", help="store the exact messages in raw.jsonl")
    ap.add_argument("--send-case-header", action="store_true", help="send X-Stress-Case (mock_server golden mode)")
    ap.add_argument("--worst", type=int, default=12)
    ap.add_argument("--out", default=os.path.join(HERE, "out", datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    ap.add_argument("--resume", action="store_true", help="skip jobs already in OUT/raw.jsonl")
    ap.add_argument("--list-cards", action="store_true")
    ap.add_argument("--validate-cases", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--merge", nargs="+", metavar="RUN_DIR")
    ap.add_argument("--export-json", action="store_true", help="write cases_json/*.json mirrors (for hosts without PyYAML)")
    args = ap.parse_args()
    args.extra_body = json.loads(args.extra_body)
    if args.export_json:
        return cmd_export_json(args.cases)
    cards, problems = parse_cards(args.cards_dir)
    cases = load_cases(args.cases)
    if args.only:
        cases = [c for c in cases if re.search(args.only, c["id"]) or any(re.search(args.only, t) for t in c.get("tags", []))]
    if args.list_cards:
        return cmd_list_cards(cards, problems, cases)
    if args.validate_cases:
        sys.exit(1 if cmd_validate(cards, cases, args) else 0)
    if args.dry_run:
        return cmd_dry_run(cards, cases, args)
    if args.merge:
        return write_report(args.merge, args.out, cards, problems, cases, args)
    cmd_run(args, cards, problems, cases)


if __name__ == "__main__":
    main()
