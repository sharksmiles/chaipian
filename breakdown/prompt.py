"""七维拆解 prompt 模板（核心资产：按《爆款视频拆解模板.md》固化的拆解指令）"""
import json

HOOK_TYPES = "痛点直击｜反常识/反直觉｜悬念提问｜结果前置｜利益承诺｜冲突开场｜情绪共鸣｜视觉冲击"
SKELETONS = "三段式（钩子→主体→收尾）｜AIDA（注意→兴趣→欲望→行动）｜PAS（问题→放大痛点→方案）｜黄金圈（Why→How→What）｜短剧节奏（每3-5秒一个刺激点）"

SYSTEM = """你是资深的爆款短视频拆解专家，服务于内容团队。给你一条视频的元信息和带时间戳的逐字稿，请按"七维拆解模型"输出结构化拆解结果。

七维：①选题与定位 ②标题/封面/话题 ③前3秒钩子 ④结构与脚本 ⑤画面与剪辑 ⑥声音设计 ⑦数据与评论区。

规则：
1. 只依据给定材料分析。逐字稿和元信息里没有的信息（如完播率、评论区、封面细节、BGM曲目）一律填空字符串或 null，严禁编造。
2. 前3秒钩子按逐秒拆（0-1s / 1-2s / 2-3s）；"画面""音效"只能依据台词与常识合理推断，不确定就写"待人工补充"。
3. 结构骨架按时间轴分段，每段标注起止秒、段落功能、要点、情绪值（0-5）、留人/掉人判断。
4. 钩子类型只从以下清单选择：%HOOKS%。结构骨架类型只从以下清单选择：%SKELETONS%。
5. 结尾必须给出可迁移的公式：一句话钩子公式、结构链、节奏规律、3条可复用点、可迁移到哪个选题。
6. 输出必须是合法 JSON（不要 markdown 代码块，不要注释），结构严格遵循用户消息中的示例。"""

SCHEMA_DEMO = {
    "basic": {"platform": "", "title": "", "account": "", "duration": "", "category": "赛道"},
    "data_snapshot": {
        "view_count": None, "likes": None, "comments": None,
        "note": "数据来自下载接口；完播率/转发/收藏等后台指标需人工补充",
    },
    "topic_card": {"audience": "目标人群", "angle": "切入角度", "trend": "蹭的热点/标签", "difference": "差异化", "one_liner": "选题一句话"},
    "title_cover": {"title": "标题原文", "title_formula": "标题公式类型", "cover_focus": "封面视觉焦点（不确定填空）", "tags": "话题标签"},
    "hook_3s": {
        "timeline": [
            {"second": "0-1s", "visual": "画面", "script": "台词", "subtitle": "字幕/特效", "sound": "音效"}
        ],
        "hook_type": "钩子类型（从清单选）",
        "hook_formula": "可迁移的钩子公式",
    },
    "structure": {
        "segments": [
            {"start": "0", "end": "3", "function": "段落功能", "points": "内容要点", "emotion": 3, "retention": "留人/掉人判断"}
        ],
        "skeleton": "骨架类型（从清单选）",
        "twist_count": 0,
        "ending": "结尾收尾方式",
    },
    "script_excerpts": [{"quote": "值得学习的原句", "function": "功能标注（开场句/转折句/收尾句/评论引导句）"}],
    "visuals": {"notes": "画面语言要点", "avg_shot": "平均镜头时长判断", "broll_density": "B-roll密度"},
    "sound": {"speech_speed": "语速判断（字/分钟区间）", "bgm": "BGM（不确定填null）", "sfx": "音效"},
    "comments": {"pinned": "置顶/引导话术（未知填null）", "top_comments": [], "insight": "待人工补充"},
    "formula": {
        "hook_one_liner": "一句话钩子公式",
        "structure_chain": "结构链（如：悬念提问→案例→反转→行动号召）",
        "rhythm": "节奏规律",
        "reusable": ["可复用点1", "可复用点2", "可复用点3"],
        "transfer_topic": "可迁移到我方哪个选题",
    },
    "notes": "其他洞察",
}


def build_messages(meta, lines):
    system = SYSTEM.replace("%HOOKS%", HOOK_TYPES).replace("%SKELETONS%", SKELETONS)
    info = (
        f"# 视频信息\n"
        f"- 标题：{meta['title']}\n"
        f"- 平台：{meta['platform']}\n"
        f"- 作者：{meta['uploader'] or '未知'}\n"
        f"- 时长：{meta['duration']} 秒\n"
        f"- 发布日期：{meta['upload_date'] or '未知'}\n"
        f"- 播放量：{meta['view_count'] if meta['view_count'] is not None else '未知'}\n"
        f"- 点赞数：{meta['like_count'] if meta['like_count'] is not None else '未知'}\n"
        f"- 评论数：{meta['comment_count'] if meta['comment_count'] is not None else '未知'}\n"
        f"- 简介（截取）：{(meta['description'] or '无')[:300]}\n\n"
    )
    transcript = "# 带时间戳逐字稿\n" + "\n".join(lines) + "\n\n"
    output_req = (
        "# 输出要求\n"
        "请输出严格符合以下结构的 JSON（未提及的字段填空字符串或 null，数值用数字）：\n"
        + json.dumps(SCHEMA_DEMO, ensure_ascii=False, indent=2)
    )
    user = info + transcript + output_req
    return system, user


VISION_OUTPUT_DEMO = {
    "video_type": "AI生成 / 实拍 / 混剪（附判断依据）",
    "quick_prompt": {
        "zh": "一行快速提示词（≤60字，可直接粘贴到文生视频工具）",
        "en": "One-line quick prompt (English)",
    },
    "negative_prompt": "负面提示词（逗号分隔，画面中应避免的元素/缺陷）",
    "overall_prompt": {
        "zh": "整体文生视频提示词（中文）",
        "en": "Overall text-to-video prompt (English)",
    },
    "scene_prompts": [
        {
            "time": "0-3s",
            "visual": "画面内容描述（含相对前一帧的变化）",
            "prompt_zh": "该镜头中文提示词",
            "prompt_en": "Shot prompt in English",
            "camera": "角度+景别+运镜+速度（如：45°仰拍，中景，缓推）",
            "style": "风格关键词（光影/色调/质感）",
        }
    ],
    "style_keywords": ["风格关键词列表"],
    "image_to_video_prompt": "图生视频提示词模板（以参考图为第一帧）",
    "recreate_notes": "复刻建议（模型选择、参数、注意事项）",
}


SINGLE_VISION_OUTPUT_DEMO = {
    "quick_prompt": {
        "zh": "一行快速提示词（≤60字，可直接粘贴到文生视频工具）",
        "en": "One-line quick prompt (English)",
    },
    "description_zh": "画面深度描述（150-200字，生动且精准）",
    "subject": {
        "characters": "人物特征（性别/年龄/外貌/表情/发型/妆容）",
        "action": "动作/姿态/手势/朝向",
        "clothing": "服装配饰（款式/颜色/材质/细节）",
        "other": "其他主体（动物/物体/图标等）",
    },
    "environment": {
        "scene_type": "场景类型（室内/室外/自然/城市/虚拟/抽象）",
        "scene_detail": "具体场景描述",
        "time_weather": "时段+天气（清晨/正午/黄昏/深夜 + 晴/雨/雪/雾）",
        "depth": "空间层次（前景/中景/背景）",
    },
    "camera": {
        "angle": "拍摄角度（数值化，如 45°仰拍）",
        "shot_size": "景别（ELS/LS/FS/MS/MCU/CU/ECU）",
        "movement": "运镜建议+速度（静态图推断，如 缓推/固定）",
        "focus": "焦点/景深（合焦位置/虚化程度）",
        "composition": "构图法则（三分法/引导线/框架/对称/留白）",
    },
    "lighting": {
        "source": "光源类型（自然光/人造光/屏幕光）",
        "direction": "光照方向（顺光/侧光/逆光/顶光/底光）",
        "contrast": "光比氛围（柔和/强烈/高反差/剪影）",
        "color_temp": "色温色调（暖调/冷调/中性/霓虹）",
    },
    "style": {
        "visual_style": "视觉风格（写实/电影感/动漫/3D渲染/油画/赛博朋克等）",
        "color": "色彩体系（主色调+配色方案）",
        "texture": "质感材质（光滑/粗糙/金属/织物/烟雾）",
        "post": "后期处理（胶片颗粒/晕影/LUT滤镜等）",
    },
    "mood": {
        "tone": "情感基调（宁静/紧张/温馨/孤独/浪漫/神秘/活力）",
        "narrative": "叙事暗示（故事背景/情节暗示）",
        "rhythm": "节奏动态（静止/缓慢/快速/动荡）",
    },
    "negative_prompt": "负面提示词（逗号分隔，画面中应避免的元素/缺陷）",
    "params": {
        "aspect_ratio": "宽高比建议（如 16:9 / 9:16 / 21:9）",
        "motion_intensity": "运动强度（静止/微动/中/剧烈）",
        "duration_suggestion": "时长建议（秒）",
    },
    "recreate_notes": "复刻建议（模型选择/图生视频用法/注意事项）",
}


def build_single_vision_messages(meta, frame_count):
    """单图/单帧深度反推的 system + user 文本（图像以 data URI 追加在 user content 中）。"""
    system = (
        "你是 AI 视频画面提示词反推专家。给你一张视频截图/封面/参考图，"
        "请按专业级六维分析（主体/环境/镜头语言/光影/美术风格/氛围情绪）反推：这张画面用 AI 怎么生成。\n"
        "规则：\n"
        "1. 画面细节只依据给定图片，看不到的信息写'待人工确认'，不要编造；\n"
        "2. 镜头语言按标准术语描述：景别用 ELS(极端远景)/LS(远景)/FS(全景)/MS(中景)/MCU(近景)/CU(特写)/ECU(大特写)；"
        "运镜用 推/拉/摇/移/跟/环绕/手持/滑动变焦 并加速度（缓/匀速/快，静态图给建议值）；"
        "角度尽量数值化（如'45°仰拍'而非'斜角'）；构图参考 三分法/引导线/框架/对称/留白；\n"
        "3. 主体按 人物特征/动作/服装配饰/其他主体 逐项写；环境按 场景类型/具体场景/时段天气/空间层次 逐项写；\n"
        "4. 光影按 光源类型/光照方向/光比氛围/色温色调 逐项写；风格按 视觉风格/色彩体系/质感材质/后期处理 逐项写；"
        "氛围按 情感基调/叙事暗示/节奏动态 逐项写；\n"
        "5. 除六维分析外，必须再给一行 ≤60 字可直接粘贴的快速提示词（中英各一行），覆盖最关键的主体+环境+风格+镜头；\n"
        "6. 给出负面提示词（逗号分隔）：画面中应避免的元素与 AI 常见缺陷（如 肢体形变/面部扭曲/闪烁/文字乱码/多余手指/比例失调）；\n"
        "7. 输出严格 JSON，不要 markdown 代码块，结构遵循用户消息中的示例；JSON 外不允许任何字符，禁止'好的''我将为您'等开场白。"
    )
    info = (
        f"# 图片信息\n- 来源：{meta.get('title') or '未命名'}\n\n"
        f"# 图片\n共 {frame_count} 张（随后续消息给出）。\n\n"
        f"# 输出要求\n请输出严格符合以下结构的 JSON：\n"
        + json.dumps(SINGLE_VISION_OUTPUT_DEMO, ensure_ascii=False, indent=2)
    )
    return system, info


def build_vision_messages(meta, lines, frame_count):
    """视觉反推的 system + user 文本部分（图像以 data URI 追加在 user content 中）。"""
    system = (
        "你是 AI 视频提示词反推专家。给你一段视频的关键帧画面（按时间顺序）和带时间戳逐字稿，"
        "请反推：如果要用文生视频/图生视频模型复刻这条视频，提示词应该怎么写。\n"
        "规则：\n"
        "1. 画面细节只依据关键帧，台词与节奏参考逐字稿；看不到的信息写'待人工确认'，不要编造；\n"
        "2. 必须完整覆盖所有关键帧：按时间顺序逐帧描述（第 1 帧到最后一帧），只描述开头几帧、遗漏后半段画面属于严重错误；\n"
        "3. 分镜按画面变化切分：每个关键帧一般对应一个分镜，画面变化频繁时按帧细分、不要合并；分镜数量应与关键帧数量大致一致；每镜标注时间、画面描述、中英文提示词、运镜、风格；\n"
        "4. 每镜必须写出相对前一帧的变化（主体位移/动作变化/光线变化/景别切换），不要只罗列静态画面；\n"
        "5. 镜头语言按标准术语描述：景别用 ELS(极端远景)/LS(远景)/FS(全景)/MS(中景)/MCU(近景)/CU(特写)/ECU(大特写)；"
        "运镜用 推/拉/摇/移/跟/环绕/手持/滑动变焦 并加速度（缓/匀速/快）；角度尽量数值化（如'45°仰拍'而非'斜角'）；"
        "构图可参考 三分法/引导线/框架/对称/留白；\n"
        "6. 提示词要可直接粘贴使用：含主体、动作、环境、光影、色调、镜头语言；\n"
        "7. 除整体提示词外，必须再给一行 ≤60 字可直接粘贴的快速提示词（中英各一行），覆盖最关键的主体+动作+环境+镜头；\n"
        "8. 给出负面提示词（逗号分隔）：画面中应避免的元素与 AI 视频常见缺陷（如 肢体形变/面部扭曲/闪烁/文字乱码/多余手指/比例失调）；\n"
        "9. 输出严格 JSON，不要 markdown 代码块，结构遵循用户消息中的示例；JSON 外不允许任何字符，禁止'好的''我将为您'等开场白；\n"
        "10. 保持简洁：画面描述不超过40字，中英文提示词各不超过80字，不要冗余铺垫。"
    )
    info = (
        f"# 视频信息\n"
        f"- 标题：{meta['title']}\n- 时长：{meta['duration']} 秒\n"
        f"- 逐字稿片段数：{len(lines)}\n\n"
        f"# 带时间戳逐字稿\n" + "\n".join(lines) + "\n\n"
        f"# 关键帧\n共 {frame_count} 帧（按时间顺序，随后续消息逐张给出）。\n\n"
        f"# 输出要求\n请输出严格符合以下结构的 JSON：\n"
        + json.dumps(VISION_OUTPUT_DEMO, ensure_ascii=False, indent=2)
    )
    return system, info
