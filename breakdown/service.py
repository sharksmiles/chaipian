"""拆解流水线服务：CLI 与 Web 共用同一套逻辑

run_pipeline(url, cfg, opts, on_progress, stop_event) -> (report_path, meta, result)
"""
import json
import pathlib
import sys

from .config import llm_key_ready, load_config
from .downloader import fetch_video
from .transcriber import transcribe
from .analyzer import analyze
from .vision import analyze_vision
from .render import render_report
from . import library as lib
from . import utils

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_pipeline(url, cfg=None, opts=None, on_progress=None, stop_event=None):
    cfg = cfg or load_config()
    opts = opts or {}

    def report(line):
        if on_progress:
            on_progress(line)
        else:
            print(line, file=sys.stderr)

    def cancelled():
        return stop_event is not None and stop_event.is_set()

    vision_configured = bool((cfg.get("vision") or {}).get("model"))
    vision_on = vision_configured and bool(opts.get("vision", True))
    engine = opts.get("engine") or None
    whisper_model = opts.get("whisper_model") or "small"
    lang = opts.get("lang") or "zh"
    cookies = opts.get("cookies_from_browser")
    cookies_file = opts.get("cookies_file")

    work = _ROOT / cfg["paths"]["work"]
    reports = _ROOT / cfg["paths"]["reports"]
    libdir = _ROOT / cfg["paths"]["library"]
    work.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    libdir.mkdir(parents=True, exist_ok=True)

    report(f"① 下载解析：{url}")
    meta, audio_path, video_path = fetch_video(
        url, work, cookies, prefer_combined=vision_on, cookiefile=cookies_file
    )
    report(f"　标题：{meta['title']} ｜ 作者：{meta['uploader'] or '未知'} ｜ 时长：{meta['duration']}s")
    if cancelled():
        raise RuntimeError("已取消")

    report(f"② 语音转写（engine={engine or 'local'}）…")
    segments = transcribe(audio_path, cfg, engine=engine, model_size=whisper_model, language=lang)
    speech_secs = sum(max(0, s["end"] - s["start"]) for s in segments)
    report(f"　完成：{len(segments)} 段，约 {speech_secs:.0f}s 语音")
    lines = utils.format_transcript(segments)
    if cancelled():
        raise RuntimeError("已取消")

    report("③ AI 七维拆解…")
    result = analyze(meta, lines, cfg)
    if cancelled():
        raise RuntimeError("已取消")

    if vision_on:
        report("③.5 画面提示词反推（抽帧 + 视觉模型）…")
        try:
            v = analyze_vision(meta, lines, video_path or audio_path, cfg)
            result["visual_prompts"] = v
            report(f"　完成：{len(v.get('scene_prompts') or [])} 个分镜提示词")
        except Exception as e:  # noqa: BLE001
            report(f"　⚠️ 提示词反推失败（不影响主报告）：{e}")
        if cancelled():
            raise RuntimeError("已取消")

    report("④ 生成报告与入库…")
    report_path = render_report(result, meta, lines, reports)
    lib.append_index(result, meta, libdir)
    lib.append_hook(result, meta, libdir)
    if "visual_prompts" in result:
        lib.append_prompt(result, meta, libdir)
    report(f"✅ 完成：{report_path.name}")
    return report_path, meta, result


def config_snapshot():
    """给 Web UI 用的配置摘要"""
    cfg = load_config()
    vision = cfg.get("vision") or {}
    llm = cfg.get("llm") or {}
    return {
        "llm_configured": llm_key_ready(cfg),
        "llm_model": llm.get("model", ""),
        "vision_available": bool(vision.get("model")),
        "vision_model": vision.get("model", ""),
        "transcribe_engine": (cfg.get("transcribe") or {}).get("engine", "local"),
        "whisper_model": (cfg.get("transcribe") or {}).get("whisper_model", "small"),
    }
