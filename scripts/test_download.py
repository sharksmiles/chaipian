"""下载测试：拉取 YouTube 首个视频（19秒）验证 yt-dlp 链路"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from breakdown.downloader import fetch_video

meta, audio = fetch_video("https://www.youtube.com/watch?v=jNQXAC9IVRw", pathlib.Path("work/test"))
print("标题:", meta["title"])
print("作者:", meta["uploader"])
print("时长:", meta["duration"], "秒")
print("播放量:", meta["view_count"])
print("平台:", meta["platform"])
print("音频文件:", audio, audio.stat().st_size, "bytes")
