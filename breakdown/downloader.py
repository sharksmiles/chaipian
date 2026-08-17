"""下载解析：yt-dlp 封装（音频轨转写 + 视频轨抽帧，无需 ffmpeg 合并）"""
import pathlib
import re
import sys
import urllib.parse

from yt_dlp import YoutubeDL

_AUDIO_SUFFIXES = {".m4a", ".webm", ".mp3", ".mp4", ".opus", ".ogg", ".flac", ".aac", ".wav"}
_IGNORE_SUFFIXES = {".json", ".jpg", ".jpeg", ".png", ".webp", ".info", ".part"}


def _normalize_url(url):
    """把平台网页/搜索页 URL 规范化为可解析的视频直链。

    例：抖音精选页 https://www.douyin.com/jingxuan/search/xxx?modal_id=123 → https://www.douyin.com/video/123
    """
    m = re.search(r"[?&]modal_id=(\d+)", url)
    if m and "douyin" in url:
        return f"https://www.douyin.com/video/{m.group(1)}"
    return url


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


def fetch_video(url, work_dir, cookies_from_browser=None, prefer_combined=False, cookiefile=None):
    """返回 (meta, audio_path, video_path)。

    prefer_combined=False：只下载音频轨（转写用），video_path=None。
    prefer_combined=True：音频轨 + 视频画面轨都下载（提示词反推抽帧用）。
    音视频分轨下载各自是单流文件，不需要 ffmpeg 合并；视频轨失败时降级纯音频。

    cookies_from_browser：浏览器名（chrome/edge/firefox），新版 Chrome/Edge 可能解密失败；
    cookiefile：Netscape 格式 cookies.txt 路径（推荐，浏览器扩展"Get cookies.txt LOCALLY"导出）。
    """
    url = _normalize_url(url)
    work_dir = pathlib.Path(work_dir)
    meta, audio = _download(url, work_dir / "audio", cookies_from_browser, "bestaudio/best", cookiefile)
    if not prefer_combined:
        return meta, audio, None
    try:
        _m, video = _download(url, work_dir / "video", cookies_from_browser, "bestvideo/best", cookiefile)
    except Exception as e:  # noqa: BLE001
        print(f"   提示：画面流下载失败（{type(e).__name__}），将跳过画面提示词反推", file=sys.stderr)
        return meta, audio, None
    return meta, audio, video


def _download(url, out_dir, cookies_from_browser, fmt, cookiefile=None):
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
    if cookiefile:
        cf = pathlib.Path(cookiefile)
        if not cf.exists():
            raise RuntimeError(f"Cookies 文件不存在：{cookiefile}\n提示：用浏览器扩展 Get cookies.txt LOCALLY 导出后填路径")
        opts["cookiefile"] = str(cf)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:  # noqa: BLE001
        hint = (
            "提示：抖音/快手/小红书等平台需要登录态 cookies。\n"
            "　1) 推荐：浏览器装扩展 Get cookies.txt LOCALLY → 打开目标站点页面 → 导出 cookies.txt，"
            "然后 Web 页面填路径或 CLI 加 --cookies-file <路径>\n"
            "　2) 或尝试 --cookies-from-browser chrome/edge（新版 Chrome/Edge 可能解密失败）；B站会员视频同样需要"
        )
        raise RuntimeError(f"下载失败：{e}\n{hint}") from e
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


def meta_for_local_file(path):
    """本地视频/音频文件：跳过 yt-dlp，直接用文件做转写与抽帧。

    返回与 fetch_video 相同结构的 meta；时长用 PyAV 探测（失败则为 0）。
    """
    path = pathlib.Path(path)
    return {
        "url": path.name,
        "platform": "本地文件",
        "title": path.stem or path.name,
        "uploader": "",
        "duration": _probe_duration(path),
        "upload_date": "",
        "view_count": None,
        "like_count": None,
        "comment_count": None,
        "description": "",
        "thumbnail": "",
    }


def _probe_duration(path):
    """用 PyAV 探测媒体时长（秒）；PyAV 不可用或失败时返回 0。"""
    try:
        import av

        container = av.open(str(path))
        try:
            dur = float(container.duration or 0) / 1_000_000.0  # AV_TIME_BASE
        except Exception:  # noqa: BLE001
            dur = 0.0
        if dur <= 0:
            stream = container.streams.video[0] if container.streams.video else None
            if stream is not None:
                try:
                    dur = float(stream.duration * stream.time_base)
                except Exception:  # noqa: BLE001
                    dur = 0.0
        container.close()
        return int(dur) if dur > 0 else 0
    except Exception:  # noqa: BLE001
        return 0
