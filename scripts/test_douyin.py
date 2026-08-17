"""抖音 URL 规范化测试：modal_id → 视频直链 → yt-dlp 解析"""
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

RAW = "https://www.douyin.com/jingxuan/search/%E5%B8%83%E6%9C%97%E5%B0%BC%E6%8B%89%E6%8B%89%E8%A3%A4?aid=68164c66-19a3-4cc8-8db2-792368f149e9&modal_id=7500428266353872185&type=general"

m = re.search(r"[?&]modal_id=(\d+)", RAW)
normalized = f"https://www.douyin.com/video/{m.group(1)}" if m else RAW
print("规范化后:", normalized)

import breakdown  # noqa: E402
from breakdown.downloader import fetch_video  # noqa: E402

try:
    meta, audio, video = fetch_video(normalized, pathlib.Path("work/douyin_test"))
    print("标题:", meta["title"])
    print("作者:", meta["uploader"], "| 时长:", meta["duration"], "s")
    print("音频:", audio, audio.stat().st_size, "bytes")
except Exception as e:  # noqa: BLE001
    print("下载失败:", type(e).__name__, str(e)[:300])
