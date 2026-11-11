#!/usr/bin/env python3
"""mock_server.py — tiny fake OpenAI-compatible server for testing run.py without a GPU (stdlib only).

Endpoints: GET /v1/models, POST /v1/chat/completions, POST /tokenize (vLLM-style {"count": n}).
Modes:
  echo   (default) deterministic pseudo-answers built from the pasted text: sometimes a real quote,
         sometimes an invented quote, a patch, a full-file dump, simplified chars, <think> blocks …
         → most correctness checks fail; proves the pipeline + checks work.
  golden returns the case's `golden` answer (needs run.py --send-case-header) → should pass ~100%.
Usage:
  python3 mock_server.py --port 8099 [--mode echo|golden] [--error-rate 0.05] [--delay 0.0] [--no-tokenize]
"""
import argparse, hashlib, json, random, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGS = None
GOLDEN = {}


def echo_answer(messages, temperature):
    last = messages[-1]["content"] if messages else ""
    seed = int(hashlib.sha1(last.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed if temperature == 0 else random.random())
    lines = [l.strip() for l in last.split("\n") if len(l.strip()) >= 8 and "{{" not in l]
    if len(last) < 700 and ("了解" in last[-80:]):
        return "了解"
    out = []
    if rng.random() < 0.3:
        out.append("<think>mock: 先想一想……</think>")
    out.append("（mock 回答）")
    if lines:
        ln = rng.choice(lines)
        out.append(f"1. 原因：可能和這行有關：{ln[:60]}")
        if rng.random() < 0.7:
            s = rng.randrange(0, max(1, len(ln) - 20))
            out.append(f"證據：「{ln[s:s + 24]}」")
        else:
            out.append("證據：「這段文字其實不在資料裡」")
    out.append("2. 驗證：加 printf 印出中間值。")
    if rng.random() < 0.3:
        out.append("3. 資料中沒有")
    if lines and rng.random() < 0.5:
        ln = rng.choice(lines)
        out.append(f"main.c:{rng.randint(1, 120)}\n修改前：\n```c\n{ln}\n```\n修改後：\n```c\n{ln} // fixed\n```")
    if rng.random() < 0.15:
        out.append("完整程式：\n```c\n" + last + "\n```")
    if rng.random() < 0.15:
        out.append("这个问题应该是数据错误。")
    return "\n".join(out)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        if ARGS.verbose:
            super().log_message(*a)

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            return self._send(200, {"object": "list", "data": [{"id": "mock", "object": "model"}]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if self.path.rstrip("/") == "/tokenize":
            if ARGS.no_tokenize:
                return self._send(404, {"error": "no tokenize"})
            txt = "\n".join(m.get("content", "") for m in body.get("messages", [])) or body.get("prompt", "")
            cjk = sum(1 for ch in txt if ord(ch) > 0x2E80)
            return self._send(200, {"count": int(cjk + (len(txt) - cjk) / 4) + 8, "max_model_len": 32768, "tokens": []})
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            return self._send(404, {"error": "not found"})
        if ARGS.delay:
            time.sleep(ARGS.delay)
        if random.random() < ARGS.error_rate:
            return self._send(500, {"error": "mock random failure"})
        msgs = body.get("messages", [])
        temp = float(body.get("temperature", 0) or 0)
        case_id, turn = self.headers.get("X-Stress-Case"), self.headers.get("X-Stress-Turn", "final")
        if ARGS.mode == "golden" and case_id:
            content = GOLDEN.get(case_id, "了解") if turn == "final" else "了解"
        else:
            content = echo_answer(msgs, temp)
        mt = body.get("max_tokens") or 1024
        finish = "stop"
        if len(content) > mt * 3:
            content, finish = content[: mt * 3], "length"
        self._send(200, {"id": "mock-" + hashlib.md5(content.encode()).hexdigest()[:8], "object": "chat.completion",
                         "created": int(time.time()), "model": body.get("model", "mock"),
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                         "usage": {"prompt_tokens": sum(len(m.get("content", "")) for m in msgs) // 2,
                                   "completion_tokens": len(content) // 2, "total_tokens": 0}})


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--mode", choices=["echo", "golden"], default="echo")
    ap.add_argument("--cases", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases", "*.yaml"))
    ap.add_argument("--error-rate", type=float, default=0.0)
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--no-tokenize", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ARGS = ap.parse_args()
    if ARGS.mode == "golden":
        import run  # reuse the case loader
        for c in run.load_cases(ARGS.cases):
            GOLDEN[c["id"]] = c.get("golden", "")
    print(f"mock server ({ARGS.mode}) on http://{ARGS.host}:{ARGS.port}/v1", file=sys.stderr, flush=True)
    ThreadingHTTPServer((ARGS.host, ARGS.port), H).serve_forever()


if __name__ == "__main__":
    main()
