"""webui 任务表隔离测试：进程内调用 vs HTTP 请求"""
import json
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import webui  # noqa: E402

# 1. 进程内直接调用
jid = webui.start_job("https://example.com/inprocess-test", {"vision": False})
print("进程内 job_id:", jid)
snap = webui._job_snapshot(jid)
print("进程内快照:", snap["status"] if snap else "MISSING")

# 2. 通过 HTTP 请求
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 8977), webui.Handler)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
time.sleep(0.3)

import urllib.request  # noqa: E402

req = urllib.request.Request(
    "http://127.0.0.1:8977/api/analyze",
    data=json.dumps({"url": "https://example.com/http-test", "vision": False}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    body = json.loads(r.read().decode())
print("HTTP 提交:", body)
jid2 = body.get("job_id")
print("_q 解析测试:", repr(webui._q("/api/status?id=" + str(jid2), "id")))
try:
    with urllib.request.urlopen(f"http://127.0.0.1:8977/api/status?id={jid2}") as r:
        print("HTTP 状态:", r.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP 状态(404 body):", e.read().decode())
print("进程内 keys:", sorted(webui.JOBS.keys()))
for k in sorted(webui.JOBS.keys()):
    print(" ", k, "->", webui.JOBS[k]["status"])
srv.shutdown()
