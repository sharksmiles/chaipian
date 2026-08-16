"""下载解析：yt-dlp 封装（音频轨转写 + 视频轨抽帧，无需 ffmpeg 合并）"""
import pathlib
import sys
import urllib.parse

from yt_dlp import YoutubeDL

_AUDIO_SUFFIXES = {".m4a", ".webm", ".mp3", ".mp4", ".opus", ".ogg", ".flac", ".aac", ".wav"}
_IGNORE_SUFFIXES = {".json", ".jpg", ".jpeg", ".png", ".webp", ".info", ".part"}


def _platform(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    if "bilibili" in host:
        return "B站"
    if "youtube" in host or "youtu.be" in host:
        return "YouTube"
    if "douyin" in host or "iesdouyin" in host:
        return "抖音"
    if "kuaishou" in host:
        return "快手"
    if "xiaohongshu" in host or "xhslink" in host:
        return "小红书"
    if "weixin" in host or "channels" in host:
        return "视频号"
    return "其他"


def fetch_video(url, work_dir, cookies_from_browser=None, prefer_combined=False):
    """返回 (meta, audio_path, video_path)。

    prefer_combined=False：只下载音频轨（转写用），video_path=None。
    prefer_combined=True：音频轨 + 视频画面轨都下载（提示词反推抽帧用）。
    音视频分轨下载各自是单流文件，不需要 ffmpeg 合并；视频轨失败时降级纯音频。
    """
    work_dir = pathlib.Path(work_dir)
    meta, audio = _download(url, work_dir / "audio", cookies_from_browser, "bestaudio/best")
    if not prefer_combined:
        return meta, audio, None
    try:
        _m, video = _download(url, work_dir / "video", cookies_from_browser, "bestvideo/best")
    except Exception as e:  # noqa: BLE001
        print(f"   提示：画面流下载失败（{type(e).__name__}），将跳过画面提示词反推", file=sys.stderr)
        return meta, audio, None
    return meta, audio, video


def _download(url, out_dir, cookies_from_browser, fmt):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": fmt,
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": False,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"下载失败：{e}\n提示：部分平台/B站会员视频需要加 --cookies-from-browser chrome") from e
    if not info:
        raise RuntimeError("yt-dlp 未能解析该链接")

    vid = str(info.get("id") or "video")
    candidates = [p for p in out_dir.glob(f"{vid}.*")]
    candidates = [p for p in candidates if p.suffix.lower() not in _IGNORE_SUFFIXES]
    if not candidates:
        raise RuntimeError(f"未找到下载文件（id={vid}）")
    media = max(candidates, key=lambda p: p.stat().st_size)

    meta = {
        "url": url,
        "platform": _platform(url),
        "title": str(info.get("title") or "未命名"),
        "uploader": str(info.get("uploader") or info.get("channel") or ""),
        "duration": int(info.get("duration") or 0),
        "upload_date": str(info.get("upload_date") or ""),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "description": str((info.get("description") or "")[:500]),
        "thumbnail": str(info.get("thumbnail") or ""),
    }
    return meta, media
