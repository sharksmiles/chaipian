"""爆款视频拆解工具包"""
import pathlib
import sys

# 依赖装在项目根目录 vendor/，先注入 sys.path（在任何 yt_dlp/openai 导入之前）
_VENDOR = pathlib.Path(__file__).resolve().parent.parent / "vendor"
if _VENDOR.exists() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# Windows 控制台默认 GBK，统一输出 UTF-8，避免中文乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
