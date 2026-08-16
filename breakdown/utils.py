"""小工具函数"""
import re


def ts(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def format_transcript(segments):
    return [f"[{ts(s['start'])}-{ts(s['end'])}] {s['text']}" for s in segments]


def sanitize(name, max_len=40):
    name = re.sub(r'[<>:"/\\|?*\r\n\t]+', "", name or "").strip().replace(" ", "-")
    return (name[:max_len] or "video")
