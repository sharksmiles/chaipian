#!/usr/bin/env python3
"""拆片 · 本地 Web 界面

用法：python webui.py [--port 8765] [--no-open]
浏览器访问 http://127.0.0.1:8765
"""
import argparse
import json
import pathlib
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
import breakdown  # noqa: F401,E402  vendor 注入 + UTF-8 输出

from breakdown import library as lib  # noqa: E402
from breakdown.config import save_cookiefile  # noqa: E402
from breakdown.mdhtml import md_to_html  # noqa: E402
from breakdown.service import config_snapshot, run_pipeline  # noqa: E402

JOBS = {}
JOBS_LOCK = threading.Lock()
_JOB_SEQ = [0]


def start_job(url, opts):
    with JOBS_LOCK:
        _JOB_SEQ[0] += 1
        jid = str(_JOB_SEQ[0])
        JOBS[jid] = {"status": "running", "progress": [], "error": "", "report": None, "stop": threading.Event()}
    if len(JOBS) > 50:  # 只保留最近 50 个任务
        for k in list(JOBS)[: len(JOBS) - 50]:
            JOBS.pop(k, None)

    def progress(line):
        with JOBS_LOCK:
            if jid in JOBS:
                JOBS[jid]["progress"].append(line)

    def worker():
        try:
            report_path, meta, _result = run_pipeline(
                url, opts=opts, on_progress=progress, stop_event=JOBS[jid]["stop"]
            )
            md = report_path.read_text(encoding="utf-8")
            with JOBS_LOCK:
                if jid not in JOBS:
                    return
                JOBS[jid]["status"] = "done"
                JOBS[jid]["report"] = {
                    "name": report_path.name,
                    "title": meta["title"],
                    "md": md,
                    "html": md_to_html(md),
                }
        except Exception as e:  # noqa: BLE001
            with JOBS_LOCK:
                if jid in JOBS:
                    JOBS[jid]["status"] = "error"
                    JOBS[jid]["error"] = str(e)

    threading.Thread(target=worker, daemon=True).start()
    return jid


def _job_snapshot(jid):
    with JOBS_LOCK:
        j = JOBS.get(jid)
        if not j:
            return None
        return {
            "status": j["status"],
            "progress": list(j["progress"]),
            "error": j["error"],
            "report": j["report"],
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "Chaipian/1.0"

    # ---- 工具方法 ----
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def log_message(self, fmt, *args):  # 安静一点
        return

    # ---- 路由 ----
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send(200, (_WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/app.css", "/app.js"):
            p = _WEB_DIR / path.lstrip("/")
            ctype = "text/css; charset=utf-8" if path.endswith(".css") else "text/javascript; charset=utf-8"
            return self._send(200, p.read_bytes(), ctype)
        if path == "/api/config":
            return self._json(200, config_snapshot())
        if path == "/api/status":
            jid = _q(self.path, "id")
            snap = _job_snapshot(jid)
            if snap is None:
                return self._json(404, {"error": "任务不存在"})
            return self._json(200, snap)
        if path == "/api/reports":
            return self._json(200, _list_reports())
        if path == "/api/report":
            name = _q(self.path, "name")
            p = _reports_dir() / name
            if not name or not p.exists():
                return self._json(404, {"error": "报告不存在"})
            md = p.read_text(encoding="utf-8")
            return self._json(200, {"name": name, "md": md, "html": md_to_html(md)})
        if path == "/api/hooks":
            return self._json(200, {"results": lib.search_hooks(_lib_dir(), _q(self.path, "q"))})
        if path == "/api/prompts":
            return self._json(200, {"results": lib.search_prompts(_lib_dir(), _q(self.path, "q"))})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/analyze":
            body = self._read_body()
            url = (body.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return self._json(400, {"error": "请粘贴 http(s) 开头的视频链接"})
            opts = {
                "engine": body.get("engine") or None,
                "whisper_model": body.get("whisper_model") or "small",
                "lang": body.get("lang") or "zh",
                "cookies_from_browser": body.get("cookies") or None,
                "cookies_file": (body.get("cookies_file") or "").strip() or None,
                "vision": bool(body.get("vision", True)),
            }
            jid = start_job(url, opts)
            return self._json(200, {"job_id": jid})
        if path == "/api/cookiefile":
            body = self._read_body()
            saved = save_cookiefile((body or {}).get("path") or "")
            return self._json(200, {"ok": True, "path": saved})
        if path == "/api/cancel":
            jid = (self._read_body() or {}).get("job_id") or ""
            with JOBS_LOCK:
                j = JOBS.get(jid)
                if j:
                    j["stop"].set()
            return self._json(200, {"ok": True})
        self._json(404, {"error": "not found"})


def _q(query_string, key):
    from urllib.parse import parse_qs

    qs = query_string.split("?", 1)[1] if "?" in query_string else query_string
    vals = parse_qs(qs).get(key)
    return vals[0] if vals else ""


def _reports_dir():
    from breakdown.config import load_config

    return _ROOT / load_config()["paths"]["reports"]


def _lib_dir():
    from breakdown.config import load_config

    return _ROOT / load_config()["paths"]["library"]


def _list_reports():
    d = _reports_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(d.glob("*.md"), reverse=True):
        out.append({"name": p.name, "date": p.name[:10] if len(p.name) >= 10 else ""})
    return out


_WEB_DIR = _ROOT / "web"


def main():
    ap = argparse.ArgumentParser(description="拆片 · 本地 Web 界面")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"拆片已启动：{url}（Ctrl+C 停止）")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
