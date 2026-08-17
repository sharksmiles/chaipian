"""配置加载：config.json + 环境变量覆盖"""
import json
import os
import pathlib
import sys
import time

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
        "max_frames": 8,  # 每 3 秒抽 1 帧（上限 8）：实测 glm-4.6v 在 8 帧+2500 tokens 内输出最稳，10 帧会截断 JSON
        "max_tokens": 2500,  # 部分模型上限低（如智谱 glm-4v-flash 限 1024），按需调小
        "active": "",  # 多模型预设切换：presets 中生效的预设名（留空则用上面的平铺字段）
        "presets": {},  # {"预设名": {"model": ..., "base_url": ..., "api_key": ..., "max_tokens": ...}}
    },
    "paths": {
        "reports": "reports",
        "library": "library",
        "work": "work",
    },
    "download": {
        "cookiefile": "",  # 默认 cookies 文件路径（抖音/快手等需要），Web 页面可一键保存
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
        user = None
        for _ in range(3):  # 并发写入时可能读到半截文件，稍等重试
            try:
                user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.15)
        if user is None:
            print(f"⚠️ config.json 解析失败（可能正被写入），使用默认配置", file=sys.stderr)
        else:
            _merge(cfg, user)
    for var, keys in _ENV_MAP:
        v = os.environ.get(var)
        if v:
            _set(cfg, keys, v)
    _apply_vision_preset(cfg)
    return cfg


def _apply_vision_preset(cfg):
    """vision.active 指向 presets 里的预设时，把预设字段合入 vision 顶层。"""
    v = cfg.get("vision") or {}
    presets = v.get("presets") or {}
    active = v.get("active") or ""
    if presets and active in presets:
        _merge(v, presets[active])


def _write_config(data):
    """原子写 config.json：先写临时文件再 os.replace，避免并发读读到半截文件。

    读者持有文件句柄时 os.replace 可能短暂撞 Windows 共享锁，重试几次即可。
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    for _ in range(6):
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, CONFIG_PATH)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def save_cookiefile(path):
    """把 cookies 文件路径写入 config.json（保留其他字段）"""
    cfg = load_config()
    cfg["download"]["cookiefile"] = (path or "").strip()
    _write_config(cfg)
    return cfg["download"]["cookiefile"]


def save_vision_active(name):
    """切换生效的视觉模型预设（写入 config.json 的 vision.active）。"""
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    vision = raw.setdefault("vision", {})
    presets = vision.get("presets") or {}
    if name not in presets:
        raise ValueError(f"未知的视觉模型预设：{name}")
    vision["active"] = name
    _write_config(raw)
    return name
