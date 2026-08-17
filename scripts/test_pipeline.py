"""端到端流水线测试：mock LLM + 视觉模型，验证 拆解→提示词反推→报告→入库→检索 全链路"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import breakdown  # noqa: F401,E402  触发 vendor 注入
import openai  # noqa: E402

from breakdown import library as lib  # noqa: E402
from breakdown.analyzer import analyze  # noqa: E402
from breakdown.prompt import SCHEMA_DEMO, VISION_OUTPUT_DEMO  # noqa: E402
from breakdown.render import render_report  # noqa: E402
from breakdown.utils import format_transcript  # noqa: E402
import breakdown.vision as vision_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 关键：使用临时目录，绝不碰真实的 reports/ 与 library/（否则会清掉用户数据）
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="chaipian-test-"))
TEST_DIR = _TMP / "work"
REPORTS = _TMP / "reports"
LIB = _TMP / "library"
for d in (TEST_DIR, REPORTS, LIB):
    d.mkdir(parents=True, exist_ok=True)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResp:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def create(self, **kwargs):
        msgs = kwargs["messages"]
        system = msgs[0]["content"]
        user = msgs[1]["content"]
        if "扩写" in system:  # 分镜扩写调用（文本）
            return FakeResp(json.dumps(
                {"scene_prompts": [{"time": "0-3s", "prompt_zh": "完整版提示词。" * 15}]},
                ensure_ascii=False,
            ))
        if "合并" in system:  # 分片合并调用（文本）
            sample = json.loads(json.dumps(VISION_OUTPUT_DEMO))
            sample["video_type"] = "AI生成（测试判断）"
            sample["overall_prompt"]["zh"] = "测试整体提示词"
            sample["scene_prompts"] = [
                {"time": "0-3s", "visual": "特写", "prompt_zh": "P1", "prompt_en": "E1", "camera": "固定", "style": "自然"}
            ]
            return FakeResp(json.dumps(sample, ensure_ascii=False))
        if isinstance(user, list):  # 视觉反推调用（含图）
            assert any(p.get("type") == "image_url" for p in user)
            sample = json.loads(json.dumps(VISION_OUTPUT_DEMO))
            sample["video_type"] = "AI生成（测试判断）"
            sample["overall_prompt"]["zh"] = "测试整体提示词"
            return FakeResp(json.dumps(sample, ensure_ascii=False))
        # 文本七维拆解调用
        assert kwargs.get("response_format") == {"type": "json_object"}
        sample = json.loads(json.dumps(SCHEMA_DEMO))
        sample["basic"]["category"] = "测试赛道"
        sample["title_cover"]["title"] = ""  # 触发回退到真实标题
        sample["formula"]["hook_one_liner"] = "悬念提问 + 利益承诺"
        sample["formula"]["reusable"] = ["复用A", "复用B", "复用C"]
        sample["hook_3s"]["timeline"] = [
            {"second": "0-1s", "visual": "特写", "script": "大家好", "subtitle": "", "sound": ""}
        ]
        return FakeResp(json.dumps(sample, ensure_ascii=False))


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self, *a, **kw):
        self.chat = FakeChat()


def main():
    openai.OpenAI = FakeClient  # mock
    vision_mod.extract_frames = lambda path, max_frames=8, start=None, end=None: ["QUJD", "REVG"]  # mock 抽帧

    meta = {
        "url": "https://www.bilibili.com/video/BVtest",
        "platform": "B站", "title": "流水线测试视频", "uploader": "测试UP",
        "duration": 120, "upload_date": "20260101",
        "view_count": 1000, "like_count": 100, "comment_count": 5,
        "description": "",
    }
    cfg = {
        "llm": {"base_url": "http://fake", "api_key": "fake", "model": "fake-model"},
        "vision": {"model": "fake-vision", "base_url": "", "api_key": "", "max_frames": 8},
        "transcribe": {}, "paths": {},
    }
    segments = [{"start": 0, "end": 3, "text": "大家好"}, {"start": 3, "end": 8, "text": "今天讲钩子"}]
    lines = format_transcript(segments)

    # ① 文本七维拆解
    result = analyze(meta, lines, cfg)
    # ② 画面提示词反推
    vp = vision_mod.analyze_vision(meta, lines, "fake.mp4", cfg)
    assert vp["video_type"] == "AI生成（测试判断）"
    result["visual_prompts"] = vp

    # ③ 报告 + 入库
    report = render_report(result, meta, lines, REPORTS)
    lib.append_index(result, meta, LIB)
    lib.append_hook(result, meta, LIB)
    lib.append_prompt(result, meta, LIB)

    text = report.read_text(encoding="utf-8")
    assert "流水线测试视频" in text
    assert "一句话钩子公式" in text and "悬念提问 + 利益承诺" in text
    assert "画面提示词反推" in text and "测试整体提示词" in text
    assert "[00:00-00:03] 大家好" in text

    csv_text = (LIB / "index.csv").read_text(encoding="utf-8-sig")
    assert "流水线测试视频" in csv_text and "悬念提问 + 利益承诺" in csv_text

    hits = lib.search_hooks(LIB, "复用A")
    assert hits and hits[0]["transfer_topic"] == "可迁移到我方哪个选题"
    phits = lib.search_prompts(LIB, "测试整体提示词")
    assert phits and phits[0]["video_type"] == "AI生成（测试判断）"

    print("✅ 全链路通过（含提示词反推）：", report)
    print("✅ index.csv / hooks.jsonl / prompts.jsonl 均入库，检索 OK")

    # 清理测试产物（临时目录，不影响真实数据）
    shutil.rmtree(_TMP, ignore_errors=True)
    print("✅ 测试产物已清理")


if __name__ == "__main__":
    main()
