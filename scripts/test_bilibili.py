"""B站下载测试：验证 bilibili 平台解析"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from breakdown.downloader import fetch_video

meta, audio = fetch_video("https://www.bilibili.com/video/BV1GJ411x7h7", pathlib.Path("work/test_bili"))
print("标题:", meta["title"])
print("作者:", meta["uploader"])
print("时长:", meta["duration"], "秒")
print("播放量:", meta["view_count"], "点赞:", meta["like_count"])
print("平台:", meta["platform"])
print("音频文件:", audio, audio.stat().st_size, "bytes")
