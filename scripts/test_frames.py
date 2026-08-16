"""抽帧测试：真实 B站视频（带画面格式）→ PyAV 抽帧 → base64 JPEG"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import breakdown  # noqa: F401,E402
from breakdown.downloader import fetch_video  # noqa: E402
from breakdown.vision import extract_frames  # noqa: E402

meta, audio, video = fetch_video(
    "https://www.bilibili.com/video/BV1GJ411x7h7",
    pathlib.Path("work/test_frames"),
    prefer_combined=True,
)
print("音频文件:", audio, audio.stat().st_size, "bytes")
assert video is not None, "视频轨下载失败"
print("视频文件:", video, video.stat().st_size, "bytes")
print("时长:", meta["duration"], "s")
frames = extract_frames(video, max_frames=6)
print("抽帧数:", len(frames))
assert frames, "抽帧失败"
for i, b64 in enumerate(frames, 1):
    assert b64[:10] == "/9j/4AAQSk", f"第{i}帧不是 JPEG"
print("✅ 抽帧成功：全部为 JPEG（base64），可直接发视觉模型")
