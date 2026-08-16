"""转写测试：验证 faster-whisper 本地转写链路（首次运行自动下载模型）"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from breakdown.transcriber import _transcribe_local

audio = pathlib.Path("work/test/jNQXAC9IVRw.webm")
t0 = time.time()
segs = _transcribe_local(audio, model_size="tiny", language="en")
print(f"耗时 {time.time() - t0:.0f}s，{len(segs)} 段")
for s in segs[:10]:
    print(f"  [{s['start']:.1f}-{s['end']:.1f}] {s['text']}")
