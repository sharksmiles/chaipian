"""画面提示词反推：抽关键帧 + 多模态视觉模型 → 反推 AI 生成提示词

原理：把视频均匀抽 N 帧（PyAV 解码，不依赖 ffmpeg 二进制），连同逐字稿一起
喂给支持图像的 OpenAI 兼容模型（GPT-4o / 豆包视觉 / GLM-4V / Qwen-VL / Gemini 兼容端点），
输出"整体文生视频提示词 + 分镜提示词 + 风格关键词 + 图生视频模板"。
"""
import base64
import io
import json
import re
import sys

from .prompt import build_vision_messages

VISION_SYSTEM = (
    "你是 AI 视频提示词反推专家。给你一段视频的关键帧画面和逐字稿，"
    "请反推出：如果要用文生视频/图生视频模型复刻这条视频，提示词应该怎么写。"
    "输出必须包含：视频类型判断（AI生成/实拍/混剪）、整体文生视频提示词（中英双语）、"
    "按镜头划分的分镜提示词（每镜：时间、画面描述、中文提示词、英文提示词、运镜、风格）、"
    "风格关键词列表、图生视频提示词模板、复刻建议。"
    "输出严格 JSON，不要 markdown 代码块。画面细节以关键帧为准，逐字稿用于对齐台词与口型。"
)


def extract_frames(video_path, max_frames=8):
    """用 PyAV 均匀抽取关键帧，返回 base64 JPEG 列表。"""
    import av

    container = av.open(str(video_path))
    stream = container.streams.video[0]
    try:
        duration = float(stream.duration * stream.time_base)
    except Exception:  # noqa: BLE001
        duration = None
    if not duration or duration <= 0:
        duration = float(stream.frames) / float(stream.average_rate) if stream.frames else 30.0

    n = min(max_frames, max(3, int(duration // 15) + 1))
    targets = [duration * i / (n + 1) for i in range(1, n + 1)][::-1]
    frames = []
    for frame in container.decode(stream):
        if not targets:
            break
        t = frame.time
        if t is None:
            t = frame.pts * float(frame.time_base) if frame.pts is not None else None
        if t is None or t < targets[-1]:
            continue
        while targets and t >= targets[-1]:
            targets.pop()
        img = frame.to_image().convert("RGB")
        img.thumbnail((640, 640))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        frames.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        if not targets:
            break
    container.close()
    return frames


def analyze_vision(meta, lines, video_path, cfg, max_frames=None):
    """抽帧 + 调用视觉模型反推提示词，返回 dict。"""
    from openai import OpenAI

    vision = cfg.get("vision") or {}
    llm = cfg.get("llm") or {}
    model = vision.get("model") or ""
    if not model:
        raise RuntimeError("未启用画面提示词反推：config.json 中 vision.model 为空（需要支持图像的模型，如 gpt-4o / doubao-vision / glm-4v）")
    api_key = vision.get("api_key") or llm.get("api_key")
    base_url = vision.get("base_url") or llm.get("base_url") or None
    if not api_key:
        raise RuntimeError("vision.api_key 未配置（可复用 llm.api_key）")

    max_frames = max_frames or vision.get("max_frames") or 8
    max_tokens = int(vision.get("max_tokens") or 2500)
    print(f"   （抽取关键帧：≤{max_frames} 张）", file=sys.stderr)
    frames = extract_frames(video_path, max_frames)
    if not frames:
        raise RuntimeError("未能从视频中抽取到画面帧")
    print(f"   已抽 {len(frames)} 帧，调用视觉模型 {model}…", file=sys.stderr)

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=600)
    system, user_parts = build_vision_messages(meta, lines, len(frames))
    content = [{"type": "text", "text": user_parts}]
    for b64 in frames:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    last_err = None
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"   视觉模型调用失败（{e}），重试一次…", file=sys.stderr)
            continue
        data = _parse_json(text)
        if data is not None:
            data["_frame_count"] = len(frames)
            data["_prompt_raw"] = text[:2000]
            return data
        print("   JSON 解析失败，重试…", file=sys.stderr)
    raise RuntimeError(f"视觉模型输出无法解析（最后错误：{last_err}）")


def _parse_json(text):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                return None
        return None
