"""合并步骤独立测试：合成 2 片数据验证 _merge_slices"""
import json
import pathlib
import sys

sys.path.insert(0, ".")
import breakdown  # noqa: F401,E402
from breakdown.config import load_config  # noqa: E402
from breakdown.vision import _merge_slices  # noqa: E402

cfg = load_config()
llm = cfg["llm"]

slices = [
    {
        "start": 0, "end": 40,
        "result": {
            "scene_prompts": [
                {"time": "0-5s", "visual": "歌手在麦克风前", "prompt_zh": "P1", "prompt_en": "E1", "camera": "固定", "style": "复古"},
                {"time": "5-10s", "visual": "歌手在拱门下", "prompt_zh": "P2", "prompt_en": "E2", "camera": "推近", "style": "复古"},
            ]
        },
    },
    {
        "start": 40, "end": 80,
        "result": {
            "scene_prompts": [
                {"time": "40-45s", "visual": "酒吧调酒师", "prompt_zh": "P3", "prompt_en": "E3", "camera": "固定", "style": "暖光"},
                {"time": "45-50s", "visual": "歌手特写", "prompt_zh": "P4", "prompt_en": "E4", "camera": "特写", "style": "暖光"},
            ]
        },
    },
]

try:
    merged = _merge_slices(llm, slices)
    scenes = merged.get("scene_prompts") or []
    print("合并成功，分镜数:", len(scenes))
    for s in scenes:
        print(f"  [{s.get('time')}] {str(s.get('visual'))[:30]}")
    print("overall_prompt:", json.dumps(merged.get("overall_prompt", {}), ensure_ascii=False)[:120])
    print("style_keywords:", merged.get("style_keywords"))
    assert len(scenes) >= 4, "分镜数量不足"
    print("✅ 合并测试通过")
except Exception as e:  # noqa: BLE001
    print("❌ 合并失败:", e)
    sys.exit(1)
