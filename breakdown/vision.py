"""画面提示词反推：抽关键帧 + 多模态视觉模型 → 反推 AI 生成提示词

原理：把视频按"分片分帧"策略拆解——
- 短片（≤ slice_seconds，默认 40s）：一次调用，片内均匀抽 ≤8 帧；
- 长片：按时间切成多片，每片单独抽帧 + 单独调用视觉模型（保证单次 ≤8 帧、
  输出不被截断），最后用文本 LLM 合并各片结果 → 完整分镜表（时间偏移、排序、去重）。
全程 PyAV 解码，不依赖 ffmpeg 二进制。
"""
import base64
import io
import json
import math
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

MERGE_SYSTEM = """你是视频分镜合并专家。同一视频按时间段分批反推了分镜结果（每片的时间已是全局绝对秒），
请合并成一份完整结果：把所有分镜按时间排序、合并内容重复或相邻的镜头、重新编号（时间保持绝对秒，格式如 "12-15s"），
并汇总：整体文生视频提示词（中文 zh / 英文 en，各 60-120 字）、风格关键词列表（去重）。
只输出 JSON，结构：{"video_type": "", "overall_prompt": {"zh": "", "en": ""}, "scene_prompts": [{"time": "12-15s", "visual": "", "prompt_zh": "", "prompt_en": "", "camera": "", "style": ""}], "style_keywords": [], "image_to_video_prompt": "", "recreate_notes": ""}
分镜数量多时也要全部保留，不要省略。"""


def _video_duration(path):
    """用 PyAV 探测时长（秒）"""
    import av

    try:
        container = av.open(str(path))
        stream = container.streams.video[0]
        try:
            dur = float(stream.duration * stream.time_base)
        except Exception:  # noqa: BLE001
            dur = 0.0
        if dur <= 0 and stream.frames:
            dur = float(stream.frames) / float(stream.average_rate)
        container.close()
        return dur if dur > 0 else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def extract_frames(video_path, max_frames=8, start=None, end=None):
    """用 PyAV 在 [start, end) 区间内均匀抽取关键帧，返回 base64 JPEG 列表。"""
    import av

    container = av.open(str(video_path))
    stream = container.streams.video[0]
    try:
        duration = float(stream.duration * stream.time_base)
    except Exception:  # noqa: BLE001
        duration = None
    if not duration or duration <= 0:
        duration = float(stream.frames) / float(stream.average_rate) if stream.frames else 30.0

    seg_start = start if start is not None else 0.0
    seg_end = end if end is not None else duration
    seg_len = max(0.0, seg_end - seg_start)

    # 片内每 3 秒 1 帧，最少 4 帧，不超过上限
    n = min(max_frames, max(4, int(seg_len / 3) + 1))
    if n <= 0 or seg_len <= 0:
        container.close()
        return []
    targets = [seg_start + seg_len * i / (n + 1) for i in range(1, n + 1)][::-1]

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


def _filter_lines(lines, start, end):
    """按时间范围过滤逐字稿行（格式 [MM:SS-MM:SS] 文本）"""
    out = []
    for line in lines:
        m = re.match(r"\[(\d{2}):(\d{2})-", line)
        if m:
            t = int(m.group(1)) * 60 + int(m.group(2))
            if start <= t < end:
                out.append(line)
    return out


def _offset_scene_times(result, offset, slice_len):
    """把片内相对时间 +offset 秒，变成全局绝对时间。

    部分模型会无视"片内相对时间"指令直接输出绝对时间——若分镜时间已超出片长，
    视为绝对时间，不再偏移（避免时间翻倍）。
    """
    segs = result.get("scene_prompts") or []
    max_end = 0.0
    for seg in segs:
        m = re.match(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)", str(seg.get("time") or ""))
        if m:
            max_end = max(max_end, float(m.group(2)))
    if segs and max_end > slice_len + 5:
        return result  # 已是绝对时间
    for seg in segs:
        t = str(seg.get("time") or "")
        m = re.match(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)", t)
        if m:
            a = round(float(m.group(1)) + offset)
            b = round(float(m.group(2)) + offset)
            seg["time"] = f"{a}-{b}s"
    return result


def _call_vision(client, model, max_tokens, system, user_parts, frames, label):
    """单次视觉调用（失败重试一次），返回解析后的 dict 或 None"""
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
            print(f"   {label}：视觉模型调用失败（{e}），重试一次…", file=sys.stderr)
            continue
        data = _parse_json(text)
        if data is not None:
            return data
        print(f"   {label}：JSON 解析失败，重试…", file=sys.stderr)
        user_parts += "\n\n注意：你上一次输出不是合法 JSON，请只输出完整合法 JSON，不要截断。"
    raise RuntimeError(f"{label}：视觉模型输出无法解析（最后错误：{last_err}）")


def _merge_slices(llm, slices, max_tokens=8000):
    """用文本 LLM（llm 配置，如 DeepSeek）合并各片结果"""
    from openai import OpenAI

    client = OpenAI(base_url=llm.get("base_url") or None, api_key=llm["api_key"], timeout=600)
    payload = {
        "slices": [
            {
                "range": f"{s['start']}-{s['end']}s",
                "scenes": s["result"].get("scene_prompts", []),
            }
            for s in slices
        ]
    }
    last_err = None
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=llm["model"],
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"   合并调用失败（{e}），重试一次…", file=sys.stderr)
            continue
        data = _parse_json(text)
        if data is not None:
            return data
        print("   合并输出解析失败，重试…", file=sys.stderr)
    raise RuntimeError(f"合并分镜结果解析失败（最后错误：{last_err}）")


def _coverage_end(result):
    """分镜覆盖到的最晚时间（秒）"""
    max_end = 0.0
    for seg in result.get("scene_prompts") or []:
        m = re.match(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)", str(seg.get("time") or ""))
        if m:
            max_end = max(max_end, float(m.group(2)))
    return max_end


def _merge_or_fallback(llm, slices):
    try:
        return _merge_slices(llm, slices)
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ 合并失败（{e}），退回拼接模式", file=sys.stderr)
        return _fallback_merge(slices)


def analyze_vision(meta, lines, video_path, cfg, max_frames=None):
    """分片分帧反推提示词，返回与单次调用同结构的 dict。"""
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

    frames_per_slice = int(vision.get("frames_per_slice") or max_frames or 8)
    slice_seconds = float(vision.get("slice_seconds") or 40)
    max_slices = int(vision.get("max_slices") or 8)
    max_tokens = int(vision.get("max_tokens") or 2500)

    duration = float(meta.get("duration") or 0)
    if duration <= 0:
        duration = _video_duration(video_path)
    if duration <= 0:
        duration = slice_seconds

    n_slices = min(max_slices, max(1, math.ceil(duration / slice_seconds)))
    print(
        f"   （分片分帧：时长 {duration:.0f}s → {n_slices} 片 × ≤{frames_per_slice} 帧）",
        file=sys.stderr,
    )

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=600)
    system, _ = build_vision_messages(meta, [], 1)  # 复用 system 文本

    slices = []
    for i in range(n_slices):
        s = i * slice_seconds
        e = min((i + 1) * slice_seconds, duration)
        label = f"第 {i + 1}/{n_slices} 片（{s:.0f}-{e:.0f}s）"
        print(f"   反推 {label}…", file=sys.stderr)
        seg_lines = _filter_lines(lines, s, e)
        sys_prompt, user_parts = build_vision_messages(meta, seg_lines, frames_per_slice)
        user_parts += f"\n本片段时间范围：{s:.0f}-{e:.0f} 秒（第 {i + 1}/{n_slices} 片），时间字段按片内相对秒填写。"
        frames = extract_frames(video_path, frames_per_slice, start=s, end=e)
        if not frames:
            print(f"   {label}：无帧，跳过", file=sys.stderr)
            continue
        try:
            result = _call_vision(client, model, max_tokens, sys_prompt, user_parts, frames, label)
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ {label}反推失败，跳过该片：{e}", file=sys.stderr)
            continue
        result = _offset_scene_times(result, s, e - s)
        slices.append({"start": s, "end": e, "result": result})

    if not slices:
        raise RuntimeError("所有分片反推均失败")

    if len(slices) == 1:
        merged = slices[0]["result"]
        # 覆盖度自检：模型只描述了开头几帧时，自动补帧反推后半段再合并
        covered = _coverage_end(merged)
        if 0 < covered < duration * 0.6 and duration - covered > 3:
            print(
                f"   ⚠️ 模型仅覆盖到 {covered:.0f}s（总长 {duration:.0f}s），补帧反推后半段…",
                file=sys.stderr,
            )
            seg_lines = _filter_lines(lines, covered, duration)
            sys_prompt2, user2 = build_vision_messages(meta, seg_lines, frames_per_slice)
            user2 += f"\n本批画面为视频后半段（{covered:.0f}-{duration:.0f}s），时间字段按片内相对秒填写。"
            frames2 = extract_frames(video_path, frames_per_slice, start=covered, end=duration)
            if frames2:
                try:
                    r2 = _call_vision(client, model, max_tokens, sys_prompt2, user2, frames2, "补帧")
                    r2 = _offset_scene_times(r2, covered, duration - covered)
                    merged = _merge_or_fallback(
                        llm,
                        [
                            {"start": 0, "end": covered, "result": merged},
                            {"start": covered, "end": duration, "result": r2},
                        ],
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"   ⚠️ 补帧反推失败（保留前半段结果）：{e}", file=sys.stderr)
    else:
        print("   合并各分片结果…", file=sys.stderr)
        merged = _merge_or_fallback(llm, slices)

    merged.setdefault("style_keywords", [])
    merged.setdefault("image_to_video_prompt", "")
    merged.setdefault("recreate_notes", "")
    merged["_frame_count"] = len(slices) * frames_per_slice
    merged["_slice_count"] = len(slices)
    return merged


def _fallback_merge(slices):
    """合并失败时的兜底：直接拼接分镜并按时间排序"""
    scenes = []
    for s in slices:
        scenes.extend(s["result"].get("scene_prompts") or [])
    scenes.sort(key=lambda x: float(re.match(r"(\d+)", str(x.get("time") or "0")).group(1)))
    first = slices[0]["result"]
    return {
        "video_type": first.get("video_type", ""),
        "overall_prompt": first.get("overall_prompt", {"zh": "", "en": ""}),
        "scene_prompts": scenes,
        "style_keywords": first.get("style_keywords", []),
        "image_to_video_prompt": first.get("image_to_video_prompt", ""),
        "recreate_notes": first.get("recreate_notes", ""),
    }


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
