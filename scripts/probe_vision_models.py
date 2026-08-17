"""探测智谱可用的视觉模型：用小图调 chat/completions，返回 200 即可用"""
import base64
import json
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

KEY = "3bde125150dc4c22854b50bda5684554.xpvEXen1fOGTxbvP"
URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 1x1 红色 PNG
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

CANDIDATES = [
    "glm-4v-flash", "glm-4v-plus", "glm-4v-plus-0111",
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
