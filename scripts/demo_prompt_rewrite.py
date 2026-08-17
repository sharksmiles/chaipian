"""演示：反推提示词 → 模型化改写（可灵/即梦格式），对比直接用 vs 改写后"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import breakdown  # noqa: F401,E402
from breakdown.config import load_config  # noqa: E402

ORIGINAL = {
    "zh": "展示一款专为宝宝设计的轻薄纸尿裤，强调其高吸收性和舒适性。",
    "en": "Showcase a baby diaper designed for comfort and high absorbency.",
}

SYSTEM = """你是短视频 AI 生成提示词改写专家。用户给你一段"反推出来的原始提示词"，请把它改写成可直接粘贴到视频生成工具里的成品提示词。
输出 JSON：
{
  "kling_zh": "可灵格式中文提示词（结构：主体+动作+环境+镜头语言+光影色调+风格+画质，可加入运镜描述）",
  "kling_en": "可灵格式英文版",
  "jimeng_zh": "即梦格式中文提示词（更重画面描述与镜头运动，简洁有画面感）",
  "negative": "负向提示词（不要出现的内容，如模糊/变形/多余手指）",
  "params": {"时长建议": "", "运动强度": "", "首帧建议": ""}
}
只输出 JSON。"""

USER = f"原始反推提示词（中文）：{ORIGINAL['zh']}\n原始反推提示词（英文）：{ORIGINAL['en']}\n请按上面要求改写。"

from openai import OpenAI  # noqa: E402

cfg = load_config()
client = OpenAI(base_url=cfg["llm"]["base_url"], api_key=cfg["llm"]["api_key"], timeout=300)
resp = client.chat.completions.create(
    model=cfg["llm"]["model"],
    messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
    temperature=0.4,
    response_format={"type": "json_object"},
)
text = resp.choices[0].message.content or ""
data = json.loads(text)

print("=" * 60)
print("【原始反推提示词】")
print("  ", ORIGINAL["zh"])
print("=" * 60)
print("【可灵格式（可直接粘贴）】")
print(data["kling_zh"])
print("=" * 60)
print("【即梦格式（可直接粘贴）】")
print(data["jimeng_zh"])
print("=" * 60)
print("【负向提示词】", data["negative"])
print("【参数建议】", json.dumps(data.get("params", {}), ensure_ascii=False))
