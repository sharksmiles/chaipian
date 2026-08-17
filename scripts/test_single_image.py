"""单图六维反推测试：mock OpenAI 视觉调用 + PIL 生成假图，验证 analyze_single_image 全链路"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import breakdown  # noqa: F401,E402  触发 vendor 注入
import openai  # noqa: E402

from breakdown.prompt import SINGLE_VISION_OUTPUT_DEMO  # noqa: E402
import breakdown.vision as vision_mod  # noqa: E402


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
        # 视觉调用：user 是 list（含图）
        assert isinstance(user, list), "单图反推的 user 消息应是包含图片的 list"
        assert any(p.get("type") == "image_url" for p in user)
        assert "六维" in system or "画面提示词反推" in system
        sample = json.loads(json.dumps(SINGLE_VISION_OUTPUT_DEMO))
        sample["quick_prompt"] = {"zh": "测试单图快速提示词", "en": "Test single quick prompt"}
        sample["description_zh"] = "一张测试图片的深度描述。"
        sample["subject"]["characters"] = "年轻女性"
        sample["negative_prompt"] = "肢体形变, 闪烁"
        return FakeResp(json.dumps(sample, ensure_ascii=False))


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self, *a, **kw):
        self.chat = FakeChat()


def main():
    openai.OpenAI = FakeClient  # mock

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="chaipian-single-"))
    try:
        # 生成一张假图片（PIL）
        from PIL import Image

        img = Image.new("RGB", (64, 48), (200, 30, 30))
        img_path = tmp / "cover.jpg"
        img.save(img_path, "JPEG")

        cfg = {
            "llm": {"base_url": "http://fake", "api_key": "fake", "model": "fake-model"},
            "vision": {"model": "fake-vision", "base_url": "", "api_key": "", "max_tokens": 8192},
            "transcribe": {}, "paths": {},
        }
        meta = {"url": str(img_path), "title": "cover.jpg", "platform": "本地图片", "duration": 0}

        result = vision_mod.analyze_single_image(img_path, meta, cfg)

        assert result["quick_prompt"]["zh"] == "测试单图快速提示词"
        assert result["negative_prompt"] == "肢体形变, 闪烁"
        assert result["subject"]["characters"] == "年轻女性"
        assert result["description_zh"]
        assert result["_frame_count"] == 1
        # setdefault 兜底字段
        assert result.get("params") is not None
        assert result.get("recreate_notes") is not None

        # 未配置 vision.model 时报可读错误
        try:
            vision_mod.analyze_single_image(img_path, meta, {"llm": {}, "vision": {"model": ""}})
            raise AssertionError("应当抛出未配置 vision.model 的错误")
        except RuntimeError as e:
            assert "vision.model" in str(e)

        print("✅ 单图六维反推全链路通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
