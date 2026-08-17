"""探测智谱可用的视觉模型：用小图调 chat/completions，返回 200 即可用

API Key 来源（按优先级）：环境变量 ZHIPU_API_KEY → config.json 的 vision.api_key（本地文件，已 gitignore）。
禁止在脚本里硬编码 Key。
"""
import base64
import json
import os
import pathlib
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def _load_key():
    key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if key:
        return key
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        key = ((cfg.get("vision") or {}).get("api_key") or "").strip()
    except Exception:  # noqa: BLE001
        key = ""
    return key


KEY = _load_key()
if not KEY:
    print("未找到智谱 API Key：请设置环境变量 ZHIPU_API_KEY，或在 config.json 的 vision.api_key 中填写。")
    sys.exit(1)

URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 1x1 红色 PNG
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

CANDIDATES = [
    "glm-4v-plus", "glm-4v-plus-0111",
    "glm-4.5v", "glm-4.6v", "glm-4.7v", "glm-5v",
]

for model in CANDIDATES:
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG_B64}"}},
                {"type": "text", "text": "这张图是什么颜色？只回答颜色名。"},
            ],
        }],
        "max_tokens": 10,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
            answer = d["choices"][0]["message"]["content"]
            print(f"[OK] {model}: {answer}")
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:120]
        print(f"[X] {model}: HTTP {e.code} {err}")
    except Exception as e:  # noqa: BLE001
        print(f"[X] {model}: {e}")
