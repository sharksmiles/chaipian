"""配置加载：config.json + 环境变量覆盖"""
import json
import os
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = _ROOT / "config.json"

DEFAULTS = {
    "llm": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
    },
    "transcribe": {
        "engine": "local",  # local = faster-whisper 本地免费；api = OpenAI 兼容 ASR
        "whisper_model": "small",
        "openai_base_url": "",
        "openai_api_key": "",
        "openai_audio_model": "whisper-1",
    },
    "vision": {
        "model": "",  # 填了即启用画面提示词反推（需支持图像的模型，如 gpt-4o / doubao-vision / glm-4v）
        "base_url": "",
        "api_key": "",
        "max_frames": 8,
    },
    "paths": {
        "reports": "reports",
        "library": "library",
        "work": "work",
    },
}

_ENV_MAP = [
    ("LLM_API_KEY", ("llm", "api_key")),
    ("LLM_BASE_URL", ("llm", "base_url")),
    ("LLM_MODEL", ("llm", "model")),
]

_PLACEHOLDER_KEY = "sk-你的key"


def llm_key_ready(cfg):
    """LLM Key 是否可用（排除模板占位符）"""
    k = (cfg.get("llm") or {}).get("api_key") or ""
    return bool(k) and k != _PLACEHOLDER_KEY


def _merge(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def _set(cfg, keys, value):
    cur = cfg
    for k in keys[:-1]:
        cur = cur[k]
    cur[keys[-1]] = value


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            _merge(cfg, user)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ config.json 解析失败（{e}），使用默认配置", file=sys.stderr)
    for var, keys in _ENV_MAP:
        v = os.environ.get(var)
        if v:
            _set(cfg, keys, v)
    return cfg
