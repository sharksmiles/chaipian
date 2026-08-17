"""分片分帧实测：212s B站视频 → 6 片反推 → 合并"""
import pathlib
import sys

sys.path.insert(0, ".")
import breakdown  # noqa: F401,E402
from breakdown.config import load_config  # noqa: E402
from breakdown.downloader import fetch_video  # noqa: E402
from breakdown.vision import analyze_vision, _video_duration  # noqa: E402

cfg = load_config()
meta, audio, video = fetch_video(
    "https://www.bilibili.com/video/BV1GJ411x7h7",
    pathlib.Path("work/slice_test"),
    prefer_combined=True,
)
print("视频:", video.name, "| 时长:", meta["duration"], "s")
dur = _video_duration(video)
print("PyAV 探测时长:", round(dur, 1), "s")

result = analyze_vision(meta, [], video, cfg)
scenes = result.get("scene_prompts") or []
print("=" * 60)
print("合并后分镜数:", len(scenes))
print("分片数:", result.get("_slice_count"))
for s in scenes[:20]:
    print(f"  [{s.get('time')}] {str(s.get('visual'))[:40]}")
print("风格关键词:", result.get("style_keywords"))
