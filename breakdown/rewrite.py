"""提示词改写层：把反推的提示词改写成按模型分段、可直接粘贴的复刻提示词包

输入：prompts.jsonl 中的一条反推记录（overall_zh / overall_en / scene_prompts）
输出：{segments: [{time, summary, seedance_zh, kling_zh, jimeng_zh}], negative, params}
分段把 3 秒级分析分镜合并成 5-8 秒生成段，每段分别按 Seedance / 可灵 / 即梦 格式改写；
不输出整条视频的简略提示词（复刻目的是逐段生成）。
连贯性保证：① 改写指令强制全片一致性锚点（主体/场景/光线/风格描述逐字复用 + 段间衔接句）；
② 输出后做时间轴校验（连续性/段长/覆盖度），未通过带错误反馈重试一次。
"""
import json
import re
import sys

from .config import llm_key_ready

TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)s?")

SYSTEM = """你是短视频 AI 生成提示词改写专家。用户给你一段"反推出来的原始提示词"（含按 3 秒左右切分的分析级分镜提示词），请改写成可直接粘贴到视频生成工具里的成品提示词包。用户目的是复刻这条视频，需要按模型、按生成段给出可直接生成的完整提示词。
输出 JSON，字段如下：
{
  "segments": [
    {
      "time": "0-8s",
      "summary": "该段画面要点（20字内）",
      "seedance_zh": "该段的 Seedance 2.0/2.5 格式中文提示词（五维架构：①主体 ②动作 ③环境 ④镜头语言[景别/运镜/视角] ⑤光影色调与氛围，可加风格画质，120-250字）",
      "kling_zh": "该段的可灵格式中文提示词（主体+动作+环境+镜头语言+光影色调+风格+画质，可加入运镜描述，120-220字）",
      "jimeng_zh": "该段的即梦格式中文提示词（重画面描述与镜头运动，简洁有画面感，80-150字）"
    }
  ],
  "negative": "负向提示词（不要出现的内容，逗号分隔）",
  "params": {"时长建议": "5-8秒", "运动强度": "低/中/高", "首帧建议": "首帧构图要点"}
}
合并规则：把用户给的 3 秒级分镜合并成可独立生成的段落——按画面内容/场景切换/语义完整性划分，每段 5-8 秒（不得少于 4 秒、不得多于 12 秒）；整条视频通常拆成 3-5 段；时间字段写合并后的区间，格式如 "0-8s"，必须首尾相连覆盖全片：段与段之间无缝隙、无重叠（上一段结束秒 = 下一段开始秒），首段从 0 开始，末段覆盖到视频最后；输入分镜的每一个画面要点都必须归入某一段，不得遗漏。
全片一致性（复刻连贯性的关键）：所有段的 主体（人物外貌/服装/产品外观）、场景、光线、色调、风格 必须完全一致，描述词逐字复用（例如婴儿固定写"胖乎乎的婴儿穿着粉色花纹纸尿裤"，场景固定写"紫色床单上的明亮室内"），严禁每段换一种说法；每段提示词开头写"延续上一段：同一【主体】、同一【场景】，从上一段结尾画面继续"，结尾点出该段画面停驻状态（如"画面停在双手展示纸尿裤"），使相邻段的动作/机位/光线能自然接上；【重要】只有非首段才写衔接句，首段（时间最早的那段）严禁出现"延续上一段/承接上一段/从上一段"等任何衔接字样，首段直接描述起始画面（主体+场景+初始动作+镜头+光线）。
规则：画面细节以原始提示词为准，不要自行添加不存在的元素；Seedance 部分镜头语言要具体（如：特写→中景推进、俯视 10°、镜头跟随主体左移），但不要编造原始画面没有的内容；若用户提供了"原始负面提示词"，negative 字段以它为主并补充完善，不要丢弃；若用户没有提供分镜提示词，segments 输出一个覆盖整条视频时间区间（如 "0-26s"）的分段；只输出 JSON，不要输出 segments 以外的提示词字段。"""


def _parse_time(t):
    m = TIME_RE.match(str(t or "").strip())
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _ranges(segments):
    out = []
    for s in segments or []:
        if not isinstance(s, dict):
            continue
        r = _parse_time(s.get("time"))
        if r:
            out.append(r)
    return out


def _union_length(ranges):
    rs = sorted(ranges)
    total = 0.0
    if not rs:
        return 0.0
    cur_s, cur_e = rs[0]
    for s, e in rs[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    return total + (cur_e - cur_s)


FIRST_SEG_RE = re.compile(r"延续上一段|承接上一段|从上一段|上一段|前一段")


def _check_first_segment(segments):
    """首段（时间最早）的提示词不得出现衔接句（前面没有上一段）。

    返回错误描述或 None。只检查时间最早的那段，其余段的衔接句是预期行为。
    """
    rs = []
    for i, s in enumerate(segments or []):
        if not isinstance(s, dict):
            continue
        r = _parse_time(s.get("time"))
        if r:
            rs.append((i, r))
    if not rs:
        return None
    i0 = min(rs, key=lambda x: x[1][0])[0]
    seg = segments[i0]
    for k in ("seedance_zh", "kling_zh", "jimeng_zh"):
        text = str(seg.get(k) or "")
        if FIRST_SEG_RE.search(text):
            return (
                f"首段（{seg.get('time') or '?'}）的 {k} 提示词开头不应写衔接句"
                "（不能出现『延续上一段/承接上一段/上一段』），首段应从起始画面直接描述"
            )
    return None


def _validate_segments(segments, scene_ranges, duration):
    """校验分段时间轴：连续无缝隙/重叠、段长合理、覆盖全片。

    返回 (ok, issues)；issues 为空即通过。
    """
    issues = []
    rs = _ranges(segments)
    if not rs:
        return False, ["分段中没有可解析的时间字段"]
    rs_sorted = sorted(rs)
    for (ps, pe), (s, e) in zip(rs_sorted, rs_sorted[1:]):
        if s < pe - 0.5:
            issues.append(f"时间轴重叠：{ps:.0f}-{pe:.0f}s 与 {s:.0f}-{e:.0f}s 有重叠")
        elif s > pe + 1.0:
            issues.append(f"时间轴不连续：{ps:.0f}-{pe:.0f}s 与 {s:.0f}-{e:.0f}s 之间有缝隙")
    for (s, e) in rs_sorted:
        if e - s < 3:
            issues.append(f"段 {s:.0f}-{e:.0f}s 过短（<3秒），请与相邻段合并")
        if e - s > 12:
            issues.append(f"段 {s:.0f}-{e:.0f}s 过长（>12秒），请拆分")
    if scene_ranges:
        cov = min(1.0, _union_length(rs) / _union_length(scene_ranges))
        if cov < 0.95:
            issues.append(f"分段只覆盖原分镜时间轴的 {cov * 100:.0f}%（要求≥95%），请补全遗漏的时间段")
    if duration:
        if rs_sorted[0][0] > 1.0:
            issues.append(f"首段应从 0 秒开始（当前从 {rs_sorted[0][0]:.0f}s 开始）")
        if abs(rs_sorted[-1][1] - duration) > 2.0:
            issues.append(f"末段应覆盖到 {duration:.0f}s（当前到 {rs_sorted[-1][1]:.0f}s）")
    return (not issues), issues


def _call_pack(client, model, user, retry_hint):
    messages = [{"role": "system", "content": SYSTEM}]
    content = user + (f"\n\n注意：你上一次输出的时间轴校验未通过，请修正后重新输出完整 JSON：\n{retry_hint}" if retry_hint else "")
    messages.append({"role": "user", "content": content})
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    text = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError("改写结果无法解析为 JSON")
        data = json.loads(m.group(0))
    return _normalize_pack(data)


def rewrite_prompts(record, cfg=None):
    """改写一条反推记录，返回提示词包 dict。"""
    from openai import OpenAI

    from .config import load_config

    cfg = cfg or load_config()
    if not llm_key_ready(cfg):
        raise SystemExit("未配置 LLM API Key（config.json 或环境变量 LLM_API_KEY）")
    llm = cfg["llm"]

    zh = (record.get("overall_zh") or "").strip()
    en = (record.get("overall_en") or "").strip()
    img2vid = (record.get("image_to_video_prompt") or "").strip()
    if not zh and not en:
        raise RuntimeError("该记录没有可改写的中英文整体提示词，先重新跑一次带视觉反推的拆解")

    quick = (record.get("quick_zh") or record.get("quick_en") or "").strip()
    neg = (record.get("negative_prompt") or "").strip()
    scenes = record.get("scene_prompts") or []
    scene_txt = "\n".join(
        f"[{s.get('time', '')}] {s.get('prompt_zh', '')}"
        for s in scenes
        if isinstance(s, dict) and (s.get("prompt_zh") or "").strip()
    )
    user = (
        "原始反推提示词（中文）：" + (zh or "（无）") + "\n"
        "原始反推提示词（英文）：" + (en or "（无）") + "\n"
        "快速提示词：" + (quick or "（无）") + "\n"
        "原始负面提示词：" + (neg or "（无）") + "\n"
        "图生视频模板：" + (img2vid or "（无）") + "\n"
        "分镜提示词：" + (scene_txt or "（无）") + "\n\n"
        "请按规则改写成可直接粘贴的提示词包。"
    )
    client = OpenAI(base_url=llm.get("base_url") or None, api_key=llm["api_key"], timeout=300)

    # 时间轴校验基线：分镜时间范围 + 视频末秒（以分镜覆盖到的最晚时间为准）
    scene_ranges = _ranges(scenes)
    duration = max((e for _, e in scene_ranges), default=None)

    data = None
    last_issues = []
    for attempt in range(2):
        retry_hint = "\n".join(last_issues) if attempt > 0 else None
        data = _call_pack(client, llm["model"], user, retry_hint)
        ok, issues = _validate_segments(data.get("segments") or [], scene_ranges, duration)
        first_issue = _check_first_segment(data.get("segments") or [])
        if first_issue:
            issues.append(first_issue)
            ok = False
        if ok:
            return data
        last_issues = issues
        print(f"   改写校验未通过（第 {attempt + 1} 次）：{'；'.join(issues)}", file=sys.stderr)
    # 两次都未通过：保留结果但附上校验警告，前端展示提示用户
    data["warnings"] = last_issues
    return data


def _normalize_pack(data):
    """规范化 segments：只保留 {time, summary, kling_zh, jimeng_zh, seedance_zh} 中有效字段"""
    if not isinstance(data, dict):
        return data
    if isinstance(data.get("segments"), list):
        cleaned = []
        for s in data["segments"]:
            if not isinstance(s, dict):
                continue
            seg = {
                "time": str(s.get("time") or "").strip(),
                "summary": str(s.get("summary") or "").strip(),
            }
            for k in ("kling_zh", "jimeng_zh", "seedance_zh"):
                if (s.get(k) or "").strip():
                    seg[k] = str(s[k]).strip()
            if seg.get("time") and any(seg.get(k) for k in ("kling_zh", "jimeng_zh", "seedance_zh")):
                cleaned.append(seg)
        if cleaned:
            data["segments"] = cleaned
        else:
            data.pop("segments", None)
    return data
