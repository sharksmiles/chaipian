"""报告渲染：把 LLM 拆解结果渲染成 Markdown（对齐《爆款视频拆解模板.md》结构）"""
import datetime

from .utils import sanitize


def _g(d, *keys, default=""):
    cur = d if isinstance(d, dict) else {}
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def _fmt(v):
    v = _g(v) if not isinstance(v, (str, int, float)) else (v if v is not None else "")
    return str(v).strip()


def render_report(result, meta, lines, reports_dir):
    r = result if isinstance(result, dict) else {}
    today = datetime.date.today().isoformat()
    path = reports_dir / f"{today}-{sanitize(meta['title'])}.md"
    n = 2
    while path.exists():
        path = reports_dir / f"{today}-{sanitize(meta['title'])}-{n}.md"
        n += 1

    p = []
    p.append(f"# {meta['title']} —— 拆解报告\n")
    p.append(f"> 拆解日期：{today} ｜ [视频链接]({meta['url']}) ｜ 平台：{meta['platform']} ｜ 由 AI 初拆 + 人工校准\n")

    # 0 基本信息
    b = _g(r, "basic")
    p.append("## 0. 基本信息\n")
    p.append("| 字段 | 内容 |")
    p.append("|---|---|")
    p.append(f"| 视频链接 | {meta['url']} |")
    p.append(f"| 平台 | {meta['platform']} |")
    p.append(f"| 账号名称 | {meta['uploader'] or '未知'} |")
    p.append(f"| 发布时间 | {meta['upload_date'] or '未知'} |")
    p.append(f"| 时长 | {meta['duration']} 秒 |")
    p.append(f"| 赛道 | {_fmt(_g(b, 'category'))} |")
    p.append(f"| 粉丝量级 | 待补充 |")
    p.append("")

    # 1 数据快照
    d = _g(r, "data_snapshot")
    p.append("## 1. 数据快照\n")
    p.append("| 指标 | 数值 | 判断 |")
    p.append("|---|---|---|")
    p.append(f"| 播放量 | {_fmt(_g(d, 'view_count'))} | 待补充 |")
    p.append(f"| 点赞数 | {_fmt(_g(d, 'likes'))} | 待补充 |")
    p.append(f"| 评论数 | {_fmt(_g(d, 'comments'))} | 待补充 |")
    p.append("| 转发/收藏/完播率 | 待人工在创作者后台补充 | 待补充 |")
    p.append(f"**数据结论**：{_fmt(_g(d, 'note'))}\n")

    # 2 选题卡
    t = _g(r, "topic_card")
    p.append("## 2. 选题卡\n")
    for label, key in [("目标人群", "audience"), ("切入角度", "angle"), ("蹭的热点/标签", "trend"),
                       ("差异化", "difference"), ("选题一句话", "one_liner")]:
        p.append(f"- **{label}**：{_fmt(_g(t, key))}")
    p.append("")

    # 3 标题/封面
    tc = _g(r, "title_cover")
    p.append("## 3. 标题 / 封面 / 话题\n")
    p.append(f"- **标题原文**：{_fmt(_g(tc, 'title') or meta['title'])}")
    p.append(f"- **标题公式**：{_fmt(_g(tc, 'title_formula'))}")
    p.append(f"- **封面视觉焦点**：{_fmt(_g(tc, 'cover_focus'))}（待人工核对）")
    p.append(f"- **话题标签**：{_fmt(_g(tc, 'tags'))}")
    p.append("")

    # 4 前3秒钩子
    hk = _g(r, "hook_3s")
    p.append("## 4. 前 3 秒钩子\n")
    p.append("| 秒数 | 画面 | 台词 | 字幕/特效 | 音效 |")
    p.append("|---|---|---|---|---|")
    for seg in _g(hk, "timeline") or []:
        p.append(f"| {_fmt(_g(seg, 'second'))} | {_fmt(_g(seg, 'visual'))} | {_fmt(_g(seg, 'script'))} "
                 f"| {_fmt(_g(seg, 'subtitle'))} | {_fmt(_g(seg, 'sound'))} |")
    p.append(f"\n- **钩子类型**：{_fmt(_g(hk, 'hook_type'))}")
    p.append(f"- **钩子公式**：{_fmt(_g(hk, 'hook_formula'))}\n")

    # 5 结构骨架
    st = _g(r, "structure")
    p.append("## 5. 结构骨架（时间轴）\n")
    p.append("| 起-止(秒) | 段落功能 | 内容要点 | 情绪(0-5) | 留人/掉人 |")
    p.append("|---|---|---|---|---|")
    for seg in _g(st, "segments") or []:
        p.append(f"| {_fmt(_g(seg, 'start'))}-{_fmt(_g(seg, 'end'))} | {_fmt(_g(seg, 'function'))} "
                 f"| {_fmt(_g(seg, 'points'))} | {_fmt(_g(seg, 'emotion'))} | {_fmt(_g(seg, 'retention'))} |")
    p.append(f"\n- **骨架类型**：{_fmt(_g(st, 'skeleton'))}")
    p.append(f"- **反转/爽点数量**：{_fmt(_g(st, 'twist_count'))}")
    p.append(f"- **结尾收尾方式**：{_fmt(_g(st, 'ending'))}\n")

    # 6 逐字稿精华
    p.append("## 6. 逐字稿精华摘录\n")
    for item in _g(r, "script_excerpts") or []:
        p.append(f"- 「{_fmt(_g(item, 'quote'))}」 —— *{_fmt(_g(item, 'function'))}*")
    p.append("")

    # 7 画面与剪辑
    v = _g(r, "visuals")
    p.append("## 7. 画面与剪辑\n")
    p.append(f"- **画面语言**：{_fmt(_g(v, 'notes'))}")
    p.append(f"- **平均镜头时长判断**：{_fmt(_g(v, 'avg_shot'))}")
    p.append(f"- **B-roll 密度**：{_fmt(_g(v, 'broll_density'))}")
    p.append("")

    # 8 声音设计
    so = _g(r, "sound")
    p.append("## 8. 声音设计\n")
    p.append(f"- **语速**：{_fmt(_g(so, 'speech_speed'))}")
    p.append(f"- **BGM**：{_fmt(_g(so, 'bgm'))}（待人工核对）")
    p.append(f"- **音效**：{_fmt(_g(so, 'sfx'))}")
    p.append("")

    # 9 评论区
    c = _g(r, "comments")
    p.append("## 9. 评论区洞察（待人工补充）\n")
    p.append(f"- **置顶/引导话术**：{_fmt(_g(c, 'pinned'))}")
    for item in _g(c, "top_comments") or []:
        p.append(f"- 高赞评论：{_fmt(item)}")
    p.append(f"- **洞察**：{_fmt(_g(c, 'insight'))}")
    p.append("")

    # 10 公式提炼
    f = _g(r, "formula")
    p.append("## 10. 公式提炼（本视频最核心产出）\n")
    p.append(f"> **一句话钩子公式**：{_fmt(_g(f, 'hook_one_liner'))}")
    p.append(f">\n> **结构链**：{_fmt(_g(f, 'structure_chain'))}")
    p.append(f">\n> **节奏规律**：{_fmt(_g(f, 'rhythm'))}")
    for i, item in enumerate(_g(f, "reusable") or [], 1):
        p.append(f">\n> **可复用 {i}**：{_fmt(item)}")
    p.append(f">\n> **可迁移选题**：{_fmt(_g(f, 'transfer_topic'))}\n")

    # 11 灵感备注
    p.append("## 11. 灵感备注\n")
    p.append(_fmt(_g(r, "notes")) or "（无）")
    p.append("")

    # 12 画面提示词反推（可选，vision 配置后才有）
    vp = _g(r, "visual_prompts")
    if isinstance(vp, dict) and vp:
        p.append("## 12. 画面提示词反推（AI 生成复刻用）\n")
        p.append(f"- **视频类型判断**：{_fmt(_g(vp, 'video_type'))}")
        op = _g(vp, "overall_prompt")
        if isinstance(op, dict):
            p.append(f"\n**整体文生视频提示词（中文）**：\n\n```text\n{_fmt(_g(op, 'zh'))}\n```")
            p.append(f"\n**Overall Prompt (EN)**：\n\n```text\n{_fmt(_g(op, 'en'))}\n```")
        p.append("\n**分镜提示词**：\n")
        p.append("| 时间 | 画面描述 | 中文提示词 | 运镜 | 风格 |")
        p.append("|---|---|---|---|---|")
        for seg in _g(vp, "scene_prompts") or []:
            p.append(f"| {_fmt(_g(seg, 'time'))} | {_fmt(_g(seg, 'visual'))} | {_fmt(_g(seg, 'prompt_zh'))} "
                     f"| {_fmt(_g(seg, 'camera'))} | {_fmt(_g(seg, 'style'))} |")
        kws = _g(vp, "style_keywords")
        if isinstance(kws, list) and kws:
            p.append(f"\n**风格关键词**：{', '.join(str(k) for k in kws)}")
        p.append(f"\n**图生视频提示词模板**：\n\n```text\n{_fmt(_g(vp, 'image_to_video_prompt'))}\n```")
        p.append(f"\n**复刻建议**：{_fmt(_g(vp, 'recreate_notes'))}")
        p.append("")

    # 附：完整逐字稿
    p.append("---")
    p.append("## 附：完整逐字稿\n")
    p.append("```text")
    p.extend(lines)
    p.append("```")
    p.append("")

    path.write_text("\n".join(p), encoding="utf-8")
    return path
