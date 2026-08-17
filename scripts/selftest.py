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
check("vision system 含镜头语言术语表", "景别" in vsys and "ELS" in vsys and "运镜" in vsys)
check("vision system 含逐帧差异规则", "相对前一帧的变化" in vsys)
check("vision system 含快速提示词规则", "快速提示词" in vsys)
check("vision system 含负面提示词规则", "负面提示词" in vsys and "肢体形变" in vsys)
check("vision system 含输出纪律", "不允许任何字符" in vsys and "开场白" in vsys)
check("vision user 包含帧数说明", "4 帧" in vuser)
check("vision schema 可序列化", isinstance(json.loads(json.dumps(VISION_OUTPUT_DEMO)), dict))
check("vision schema 含 quick_prompt", "quick_prompt" in VISION_OUTPUT_DEMO and "zh" in VISION_OUTPUT_DEMO["quick_prompt"])
check("vision schema 含 negative_prompt", "negative_prompt" in VISION_OUTPUT_DEMO)
check("vision schema camera 结构化要求", "景别" in VISION_OUTPUT_DEMO["scene_prompts"][0]["camera"])

# 5.5 单图六维反推 prompt 构建
from breakdown.prompt import SINGLE_VISION_OUTPUT_DEMO, build_single_vision_messages

ssys, suser = build_single_vision_messages(meta, 1)
check("single system 含六维分析", all(k in ssys for k in ("主体", "环境", "镜头语言", "光影", "美术风格", "氛围情绪")))
check("single system 含镜头术语", "景别" in ssys and "ELS" in ssys and "构图" in ssys)
check("single system 含快速提示词规则", "快速提示词" in ssys)
check("single system 含负面提示词规则", "负面提示词" in ssys and "肢体形变" in ssys)
check("single system 含输出纪律", "不允许任何字符" in ssys)
check("single user 含图片说明", "1 张" in suser and "输出要求" in suser)
check("single schema 可序列化", isinstance(json.loads(json.dumps(SINGLE_VISION_OUTPUT_DEMO)), dict))
check("single schema 含六维字段", all(k in SINGLE_VISION_OUTPUT_DEMO for k in ("subject", "environment", "camera", "lighting", "style", "mood")))
check("single schema 含 quick_prompt/negative/params", "quick_prompt" in SINGLE_VISION_OUTPUT_DEMO and "negative_prompt" in SINGLE_VISION_OUTPUT_DEMO and "params" in SINGLE_VISION_OUTPUT_DEMO)

# 6. library 提示词记录
from breakdown.library import append_prompt, search_prompts

sample_vp = {
    "video_type": "AI生成",
    "quick_prompt": {"zh": "快速提示词", "en": "Quick prompt"},
    "negative_prompt": "肢体形变, 闪烁",
    "overall_prompt": {"zh": "整体提示词", "en": "Overall"},
    "scene_prompts": [{"time": "0-3s", "visual": "画面", "prompt_zh": "P1", "prompt_en": "E1", "camera": "45°仰拍，中景，缓推", "style": "赛博朋克"}],
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
    check("prompts.jsonl 含快速提示词字段", hits[0]["quick_zh"] == "快速提示词" and hits[0]["quick_en"] == "Quick prompt")
    check("prompts.jsonl 含负面提示词字段", hits[0]["negative_prompt"] == "肢体形变, 闪烁")
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
