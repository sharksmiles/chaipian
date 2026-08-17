"""提示词改写层：把反推的提示词改写成可灵/即梦可直接粘贴的提示词包

输入：prompts.jsonl 中的一条反推记录（overall_zh / overall_en / image_to_video_prompt）
输出：{kling_zh, kling_en, jimeng_zh, negative, params}
"""
import json

from .config import llm_key_ready

SYSTEM = """你是短视频 AI 生成提示词改写专家。用户给你一段"反推出来的原始提示词"，请把它改写成可直接粘贴到视频生成工具里的成品提示词。
输出 JSON，字段如下：
{
  "kling_zh": "可灵格式中文提示词（结构：主体+动作+环境+镜头语言+光影色调+风格+画质，可加入运镜描述，80-150字）",
  "kling_en": "可灵格式英文版",
  "jimeng_zh": "即梦格式中文提示词（重画面描述与镜头运动，简洁有画面感，60-100字）",
  "seedance_zh": "Seedance 2.0/2.5 格式中文提示词（遵循五维架构：①主体 ②动作 ③环境 ④镜头语言[景别/运镜/视角] ⑤光影色调与氛围，可加风格画质；中文为主，100-180字，可直接粘贴到即梦/火山方舟的 Seedance 模型）",
  "seedance_en": "Seedance 格式英文版",
  "negative": "负向提示词（不要出现的内容，逗号分隔）",
  "params": {"时长建议": "5-8秒", "运动强度": "低/中/高", "首帧建议": "首帧构图要点"}
}
规则：画面细节以原始提示词为准，不要自行添加不存在的元素；Seedance 部分镜头语言要具体（如：特写→中景推进、俯视 10°、镜头跟随主体左移），但不要编造原始画面没有的内容；只输出 JSON。"""


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

    user = (
        "原始反推提示词（中文）：" + (zh or "（无）") + "\n"
        "原始反推提示词（英文）：" + (en or "（无）") + "\n"
        "图生视频模板：" + (img2vid or "（无）") + "\n\n"
        "请按规则改写成可直接粘贴的提示词包。"
    )
    client = OpenAI(base_url=llm.get("base_url") or None, api_key=llm["api_key"], timeout=300)
    resp = client.chat.completions.create(
        model=llm["model"],
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    text = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        import re

        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError("改写结果无法解析为 JSON")
        data = json.loads(m.group(0))
    return data
