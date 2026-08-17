"""AI 七维拆解：调用 OpenAI 兼容 LLM，强约束 JSON 输出"""
import json
import re
import sys

from .config import llm_key_ready
from .prompt import build_messages


def analyze(meta, lines, cfg):
    from openai import OpenAI

    llm = cfg["llm"]
    if not llm_key_ready(cfg):
        raise SystemExit("未配置 LLM API Key（config.json 或环境变量 LLM_API_KEY）")
    client = OpenAI(base_url=llm.get("base_url") or None, api_key=llm["api_key"], timeout=600)
    system, user = build_messages(meta, lines)

    for attempt in range(2):
        try:
            kwargs = dict(
                model=llm["model"],
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            if attempt == 0:
                print(f"   LLM 调用失败（{e}），重试一次…", file=sys.stderr)
                continue
            raise RuntimeError(f"LLM 调用失败：{e}") from e
        data = _parse_json(text)
        if data is not None:
            return data
        print("   JSON 解析失败，要求模型重试…", file=sys.stderr)
        user += "\n\n注意：你上一次输出不是合法 JSON，请只输出合法 JSON。"
    raise RuntimeError("LLM 输出无法解析为 JSON")


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
