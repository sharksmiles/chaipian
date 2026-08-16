"""冒烟测试：不依赖网络的部分"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from breakdown.analyzer import _parse_json
from breakdown.prompt import build_messages, SCHEMA_DEMO

ok = True


def check(name, cond):
    global ok
    print(("✅" if cond else "❌"), name)
    ok = ok and bool(cond)


# 1. JSON 解析（含代码块包裹、纯 JSON、垃圾输入）
check("解析纯 JSON", _parse_json('{"a": 1}') == {"a": 1})
check("解析代码块 JSON", _parse_json('```json\n{"b": 2}\n```') == {"b": 2})
check("垃圾输入返回 None", _parse_json("没有 json") is None)

# 2. prompt 构建
meta = {
    "url": "https://example.com/v",
    "platform": "B站", "title": "测试标题", "uploader": "up主",
    "duration": 120, "upload_date": "20260101",
    "view_count": 100, "like_count": 10, "comment_count": 2,
    "description": "简介",
}
system, user = build_messages(meta, ["[00:00-00:03] 大家好"])
check("system 包含钩子清单", "悬念提问" in system)
check("system 包含骨架清单", "AIDA" in system)
check("user 包含逐字稿", "大家好" in user)
check("schema 可序列化", isinstance(json.loads(json.dumps(SCHEMA_DEMO)), dict))

# 3. library 行生成
from breakdown.library import CSV_HEADERS, _row

sample = json.loads(json.dumps(SCHEMA_DEMO))
row = _row(sample, meta)
check("CSV 行长度 = 表头长度", len(row) == len(CSV_HEADERS))
check("CSV 行是字符串", all(isinstance(x, str) for x in row))

# 4. utils
from breakdown.utils import sanitize, ts

check("时间格式", ts(65) == "01:05")
check("文件名清理", sanitize('a/b:c*"d') == "abcd")

# 5. 视觉反推 prompt 构建
from breakdown.prompt import VISION_OUTPUT_DEMO, build_vision_messages

vsys, vuser = build_vision_messages(meta, ["[00:00-00:03] 大家好"], 4)
check("vision system 包含反推要求", "提示词" in vsys and "JSON" in vsys)
check("vision user 包含帧数说明", "4 帧" in vuser)
check("vision schema 可序列化", isinstance(json.loads(json.dumps(VISION_OUTPUT_DEMO)), dict))

# 6. library 提示词记录
from breakdown.library import append_prompt, search_prompts

sample_vp = {
    "video_type": "AI生成",
    "overall_prompt": {"zh": "整体提示词", "en": "Overall"},
    "scene_prompts": [{"time": "0-3s", "visual": "画面", "prompt_zh": "P1", "prompt_en": "E1", "camera": "推", "style": "赛博朋克"}],
    "style_keywords": ["赛博朋克", "霓虹"],
    "image_to_video_prompt": "图生视频模板",
    "recreate_notes": "用可灵",
}
import tempfile

with tempfile.TemporaryDirectory() as td:
    libdir = pathlib.Path(td)
    append_prompt({"visual_prompts": sample_vp}, meta, libdir)
    hits = search_prompts(libdir, "赛博朋克")
    check("prompts.jsonl 写入与检索", len(hits) == 1 and hits[0]["overall_zh"] == "整体提示词")
    check("提示词空查询列出全部", len(search_prompts(libdir)) == 1)

# 7. markdown → HTML 转换
from breakdown.mdhtml import md_to_html

SAMPLE_MD = """# 标题
## 0. 基本信息
| 字段 | 内容 |
|---|---|
| 链接 | http://x |
| 时长 | 60 秒 |

> **一句话钩子**：悬念提问
- 可复用 1
- 可复用 2

```text
逐字稿行
```

正文 **加粗** 和 `代码` 和 [链接](http://a.b)。
"""
h = md_to_html(SAMPLE_MD)
check("md 标题", "<h1>标题</h1>" in h and "<h2>0. 基本信息</h2>" in h)
check("md 表格", "<table>" in h and "<th>字段</th>" in h and "<td>60 秒</td>" in h)
check("md 引用", "<blockquote>" in h and "<strong>一句话钩子</strong>" in h)
check("md 列表", "<ul>" in h and "<li>可复用 1</li>" in h)
check("md 代码块", "<pre><code>" in h and "逐字稿行" in h)
check("md 行内元素", "<strong>加粗</strong>" in h and "<code>代码</code>" in h and '<a href="http://a.b">链接</a>' in h)
check("md 无未转义标签", "<script" not in h)

sys.exit(0 if ok else 1)
