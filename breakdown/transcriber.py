"""语音转写：本地 faster-whisper（免费）或 OpenAI 兼容 ASR 接口"""
import pathlib
import sys


def transcribe(audio_path, cfg, engine=None, model_size="small", language="zh"):
    engine = engine or cfg["transcribe"].get("engine", "local")
    if engine == "api":
        return _transcribe_api(audio_path, cfg["transcribe"])
    return _transcribe_local(audio_path, model_size, language)


def _transcribe_local(audio_path, model_size, language):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # noqa: BLE001
        raise SystemExit(
            "缺少 faster-whisper：请先安装依赖 `python -m pip install --target vendor faster-whisper`，"
            "或改用 --engine api 走云端 ASR"
        ) from e
    print(f"   （本地 Whisper 模型 {model_size}，首次运行会自动下载，请稍候…）", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]


def _transcribe_api(audio_path, tc):
    import os

    from openai import OpenAI

    key = tc.get("openai_api_key") or os.environ.get("ASR_API_KEY")
    if not key:
        raise SystemExit("api 转写需要配置 transcribe.openai_api_key（或环境变量 ASR_API_KEY）")
    client = OpenAI(base_url=tc.get("openai_base_url") or None, api_key=key, timeout=600)
    with open(audio_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model=tc.get("openai_audio_model", "whisper-1"),
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segs = getattr(res, "segments", None) or []
    return [
        {"start": float(s.get("start", 0)), "end": float(s.get("end", 0)), "text": str(s.get("text", "")).strip()}
        for s in segs
    ]
