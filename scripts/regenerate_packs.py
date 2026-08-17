"""给提示词库现有记录重新改写（含 Seedance 2.0/2.5 格式）并保存"""
import pathlib
import sys

sys.path.insert(0, ".")
import breakdown  # noqa: F401,E402
from breakdown import library as lib  # noqa: E402
from breakdown.rewrite import rewrite_prompts  # noqa: E402

libdir = pathlib.Path("library")
records = lib.search_prompts(libdir)
print(f"共 {len(records)} 条反推记录")
for rec in records:
    pack = rewrite_prompts(rec)
    lib.save_prompt_pack(libdir, rec["url"], pack)
    print("=" * 60)
    print("已改写:", rec["title"][:25], "|", rec["url"])
    print("Seedance 2.0/2.5:", (pack.get("seedance_zh") or "")[:100])
    print("可灵:", (pack.get("kling_zh") or "")[:60])
