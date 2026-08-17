#!/usr/bin/env python3
"""一次性回填：把旧版本 prompts.jsonl 记录缺失的分镜提示词（scene_prompts）从对应报告第 12 节解析恢复。

旧版本 append_prompt 只存了 scene_count 数字、没有存 scene_prompts 内容，
导致提示词库与报告「画面提示词反推」第 12 节对不上。此脚本：
1. 遍历 prompts.jsonl 中缺 scene_prompts 的记录；
2. 按日期+标题在 reports/ 里找对应报告；
3. 解析第 12 节的「分镜提示词」表（时间/画面/中文提示词/运镜/风格）与
   「分镜完整提示词」代码块（可直接粘贴的完整版，优先采用）；
4. 回填后重写 prompts.jsonl（先备份到 prompts.jsonl.bak-<时间戳>）。

用法：python scripts/backfill_scene_prompts.py [--dry-run]
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from breakdown.config import load_config  # noqa: E402

RE_TIME = re.compile(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)s?")


def _parse_scenes(md):
    """从报告第 12 节解析分镜，返回 {time: {time, visual, prompt_zh, camera, style}}"""
    scenes = {}
    # 只取「## 12. 画面提示词反推」小节，避免误解析其他表格（如结构骨架表）
    sec = md
    m = re.search(r"^## 12\.[^\n]*\n", md, re.M)
    if m:
        sec = md[m.end():]
        cut = re.search(r"^(?:## |---)", sec, re.M)
        if cut:
            sec = sec[:cut.start()]
    lines = sec.splitlines()
    n = len(lines)
    i = 0
    # 1) 分镜完整提示词代码块：**【0-3s】** 后跟 ```text ... ```（可直接粘贴的完整版，优先）
    while i < n:
        m = re.match(r"^\*\*【([^】]+)】\*\*\s*$", lines[i])
        if m:
            time = m.group(1).strip()
            j = i + 1
            while j < n and not lines[j].startswith("```"):
                j += 1
            if j < n:
                buf = []
                j += 1
                while j < n and not lines[j].startswith("```"):
                    buf.append(lines[j])
                    j += 1
                prompt = "\n".join(buf).strip()
                if prompt:
                    scenes.setdefault(time, {"time": time})["prompt_zh"] = prompt
                    i = j + 1
                    continue
        i += 1
    # 2) 分镜提示词表：| 时间 | 画面描述 | 中文提示词 | 运镜 | 风格 |（表头含「画面描述」才认）
    in_table = False
    for line in lines:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not in_table:
                if len(cells) == 5 and cells[0] == "时间" and "画面描述" in cells[1] and "中文提示词" in cells[2]:
                    in_table = True
                continue
            if len(cells) == 5 and cells[0] != "时间":
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    continue  # 表格分隔行 |---|---|...
                time = cells[0]
                scene = scenes.setdefault(time, {"time": time})
                if cells[1]:
                    scene["visual"] = cells[1]
                if cells[2]:
                    scene["prompt_zh"] = cells[2]  # 表里已是扩写后的完整版；若代码块已有则保持代码块版本
                if cells[3]:
                    scene["camera"] = cells[3]
                if cells[4]:
                    scene["style"] = cells[4]
            elif len(cells) != 5:
                in_table = False
        elif line.strip():
            in_table = False
        else:
            in_table = False
    # 3) 按时间排序（数值比较）
    def _sort_key(scene):
        m = RE_TIME.match(str(scene.get("time") or ""))
        return (float(m.group(1)) if m else 1e9, float(m.group(2)) if m else 0)

    return [scenes[k] for k in sorted(scenes, key=lambda k: _sort_key(scenes[k]))]


def find_report(libdir, reports_dir, rec):
    """按记录日期+标题找对应报告；找不到返回 None"""
    date = str(rec.get("date") or "")
    title = str(rec.get("title") or "")
    if not reports_dir.exists():
        return None
    for p in sorted(reports_dir.glob("*.md")):
        if date and not p.name.startswith(date):
            continue
        stem = p.stem
        # 文件名形如 {date}-{title}[-N]，标题可能被 sanitize 截断
        if title and (title in stem or stem.split("-", 1)[-1].startswith(title[:20])):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只打印将回填的内容，不写文件")
    args = ap.parse_args()

    cfg = load_config()
    libdir = ROOT / cfg["paths"]["library"]
    reports_dir = ROOT / cfg["paths"]["reports"]
    path = libdir / "prompts.jsonl"
    if not path.exists():
        print("没有 prompts.jsonl，无需回填")
        return

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    updated = []
    skipped = []
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            skipped.append("坏行，跳过")
            continue
        if not isinstance(rec, dict):
            skipped.append("非对象行，跳过")
            continue
        scenes = rec.get("scene_prompts")
        if isinstance(scenes, list) and scenes:
            updated.append((rec, None, "已有 scene_prompts，无需回填"))
            continue
        if not rec.get("scene_count"):
            updated.append((rec, None, "无分镜（scene_count 为空），跳过"))
            continue
        rp = find_report(libdir, reports_dir, rec)
        if rp is None:
            updated.append((rec, None, f"找不到对应报告（date={rec.get('date')}, title={rec.get('title')}）"))
            continue
        parsed = _parse_scenes(rp.read_text(encoding="utf-8"))
        if not parsed:
            updated.append((rec, None, f"报告 {rp.name} 第 12 节无可解析分镜"))
            continue
        rec["scene_prompts"] = parsed
        rec["scene_count"] = len(parsed)
        updated.append((rec, rp.name, f"回填 {len(parsed)} 个分镜 ← {rp.name}"))

    if args.dry_run:
        for rec, src, note in updated:
            print(f"[DRY-RUN] {rec.get('title')}：{note}")
        return

    if not any(src for _, src, _ in updated):
        print("没有可回填的记录")
        return

    backup = path.with_name(f"prompts.jsonl.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"备份 → {backup.name}")

    out = []
    for rec, _src, _note in updated:
        out.append(json.dumps(rec, ensure_ascii=False))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

    n_backfilled = sum(1 for _, src, _ in updated if src)
    print(f"✅ 完成：回填 {n_backfilled} 条记录，共 {len(updated)} 条记录重写")
    for rec, src, note in updated:
        if src:
            print(f"  · {rec.get('title')}：{note}")


if __name__ == "__main__":
    main()
