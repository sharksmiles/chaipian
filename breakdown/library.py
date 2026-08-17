"""本地库：index.csv（与《爆款视频拆解表.csv》同字段）+ hooks.jsonl（钩子/公式库）"""
import csv
import datetime
import hashlib
import json
import pathlib

CSV_HEADERS = [
    "拆解日期", "视频链接", "平台", "账号名称", "粉丝量级", "发布时间", "时长(秒)", "赛道",
    "点赞数", "评论数", "转发数", "收藏数", "完播率(%)", "平均播放时长(秒)", "涨粉数", "发布时段",
    "标题原文", "标题公式", "封面视觉焦点", "前3秒画面", "前3秒台词", "钩子类型", "钩子公式",
    "结构骨架", "反转点数量", "结尾收尾方式", "平均镜头时长(秒)", "BGM曲目", "BGM是否卡点",
    "语速(字/分钟)", "置顶评论", "高赞评论1", "高赞评论2", "评论热点", "一句话钩子公式",
    "可复用点1", "可复用点2", "可复用点3", "可迁移选题", "数据结论", "灵感备注",
]


def _g(d, *keys, default=""):
    cur = d if isinstance(d, dict) else {}
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def _join_timeline(hk, field):
    parts = []
    for seg in _g(hk, "timeline") or []:
        v = _g(seg, field)
        if v:
            parts.append(str(v))
    return "；".join(parts)


def _reusable(f, i):
    items = _g(f, "reusable") or []
    return items[i] if isinstance(items, list) and i < len(items) else ""


def _row(result, meta):
    r = result if isinstance(result, dict) else {}
    b = _g(r, "basic")
    d = _g(r, "data_snapshot")
    tc = _g(r, "title_cover")
    hk = _g(r, "hook_3s")
    st = _g(r, "structure")
    so = _g(r, "sound")
    v = _g(r, "visuals")
    f = _g(r, "formula")
    row = {
        "拆解日期": datetime.date.today().isoformat(),
        "视频链接": meta["url"],
        "平台": meta["platform"],
        "账号名称": meta["uploader"],
        "粉丝量级": "",
        "发布时间": meta["upload_date"],
        "时长(秒)": meta["duration"],
        "赛道": _g(b, "category"),
        "点赞数": meta["like_count"] if meta["like_count"] is not None else "",
        "评论数": meta["comment_count"] if meta["comment_count"] is not None else "",
        "转发数": "", "收藏数": "", "完播率(%)": "", "平均播放时长(秒)": "", "涨粉数": "", "发布时段": "",
        "标题原文": _g(tc, "title") or meta["title"],
        "标题公式": _g(tc, "title_formula"),
        "封面视觉焦点": _g(tc, "cover_focus"),
        "前3秒画面": _join_timeline(hk, "visual"),
        "前3秒台词": _join_timeline(hk, "script"),
        "钩子类型": _g(hk, "hook_type"),
        "钩子公式": _g(hk, "hook_formula"),
        "结构骨架": _g(st, "skeleton"),
        "反转点数量": _g(st, "twist_count"),
        "结尾收尾方式": _g(st, "ending"),
        "平均镜头时长(秒)": _g(v, "avg_shot"),
        "BGM曲目": _g(so, "bgm"),
        "BGM是否卡点": "",
        "语速(字/分钟)": _g(so, "speech_speed"),
        "置顶评论": "", "高赞评论1": "", "高赞评论2": "", "评论热点": "",
        "一句话钩子公式": _g(f, "hook_one_liner"),
        "可复用点1": _reusable(f, 0),
        "可复用点2": _reusable(f, 1),
        "可复用点3": _reusable(f, 2),
        "可迁移选题": _g(f, "transfer_topic"),
        "数据结论": _g(d, "note"),
        "灵感备注": _g(r, "notes"),
    }
    return [str(row.get(h, "")) for h in CSV_HEADERS]


def append_index(result, meta, libdir):
    libdir = pathlib.Path(libdir)
    libdir.mkdir(parents=True, exist_ok=True)
    path = libdir / "index.csv"
    with open(path, "a", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp)
        if path.stat().st_size == 0:
            w.writerow(CSV_HEADERS)
        w.writerow(_row(result, meta))


def append_hook(result, meta, libdir):
    libdir = pathlib.Path(libdir)
    libdir.mkdir(parents=True, exist_ok=True)
    r = result if isinstance(result, dict) else {}
    f = _g(r, "formula")
    hk = _g(r, "hook_3s")
    record = {
        "date": datetime.date.today().isoformat(),
        "url": meta["url"],
        "platform": meta["platform"],
        "title": meta["title"],
        "hook_type": _g(hk, "hook_type"),
        "hook_formula": _g(hk, "hook_formula"),
        "hook_one_liner": _g(f, "hook_one_liner"),
        "structure_chain": _g(f, "structure_chain"),
        "rhythm": _g(f, "rhythm"),
        "reusable": _g(f, "reusable") or [],
        "transfer_topic": _g(f, "transfer_topic"),
    }
    with open(libdir / "hooks.jsonl", "a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def _line_id(line):
    """记录行指纹：用于前端定位/删除（稳定且不依赖行号）"""
    return hashlib.md5(line.encode("utf-8")).hexdigest()[:12]


def _read_lines(path):
    """读 JSONL 文件，返回 (非空行列表, 原始文件内容是否以换行结尾)"""
    if not path.exists():
        return []
    return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def search_hooks(libdir, query=""):
    path = pathlib.Path(libdir) / "hooks.jsonl"
    if not path.exists():
        return []
    query = (query or "").strip().lower()
    results = []
    for line in reversed(_read_lines(path)):  # 最新拆解在前
        rec = _parse_line(line)
        if rec is None:
            continue
        if not query or query in json.dumps(rec, ensure_ascii=False).lower():
            rec["id"] = _line_id(line)
            results.append(rec)
    return results


def append_prompt(result, meta, libdir):
    """把反推的视频生成提示词存入 prompts.jsonl（与报告第 12 节内容保持一致，含全部分镜提示词）"""
    libdir = pathlib.Path(libdir)
    libdir.mkdir(parents=True, exist_ok=True)
    r = result if isinstance(result, dict) else {}
    vp = _g(r, "visual_prompts")
    if not isinstance(vp, dict) or not vp:
        return
    op = _g(vp, "overall_prompt")
    if not isinstance(op, dict):
        op = {}
    kws = _g(vp, "style_keywords")
    scenes = []
    for seg in _g(vp, "scene_prompts") or []:
        if not isinstance(seg, dict):
            continue
        scenes.append(
            {
                "time": _g(seg, "time"),
                "visual": _g(seg, "visual"),
                "prompt_zh": _g(seg, "prompt_zh"),
                "prompt_en": _g(seg, "prompt_en"),
                "camera": _g(seg, "camera"),
                "style": _g(seg, "style"),
            }
        )
    record = {
        "date": datetime.date.today().isoformat(),
        "url": meta["url"],
        "platform": meta["platform"],
        "title": meta["title"],
        "video_type": _g(vp, "video_type"),
        "quick_zh": _g(vp, "quick_prompt", "zh"),
        "quick_en": _g(vp, "quick_prompt", "en"),
        "negative_prompt": _g(vp, "negative_prompt"),
        "overall_zh": _g(op, "zh"),
        "overall_en": _g(op, "en"),
        "scene_count": len(scenes),
        "scene_prompts": scenes,
        "style_keywords": kws if isinstance(kws, list) else [],
        "image_to_video_prompt": _g(vp, "image_to_video_prompt"),
        "recreate_notes": _g(vp, "recreate_notes"),
    }
    with open(libdir / "prompts.jsonl", "a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def search_prompts(libdir, query=""):
    path = pathlib.Path(libdir) / "prompts.jsonl"
    if not path.exists():
        return []
    query = (query or "").strip().lower()
    results = []
    for line in reversed(_read_lines(path)):  # 最新拆解在前
        rec = _parse_line(line)
        if rec is None:
            continue
        if not query or query in json.dumps(rec, ensure_ascii=False).lower():
            rec["id"] = _line_id(line)
            rec["pack"] = get_prompt_pack(libdir, rec.get("url", ""))
            results.append(rec)
    return results


def _parse_line(line):
    """解析单行 JSONL，失败返回 None（跳过坏行）"""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except Exception:  # noqa: BLE001
        return None


def delete_records(libdir, kind, ids):
    """按记录 id（行指纹）删除 hooks/prompts 库记录，返回删除条数。

    kind: "hooks" | "prompts"；ids: 行指纹列表（来自 search_* 返回的 rec["id"]）。
    只删库记录，不动 index.csv 汇总表与 prompt_packs 改写包。
    """
    fname = "hooks.jsonl" if kind == "hooks" else "prompts.jsonl"
    path = pathlib.Path(libdir) / fname
    if not path.exists():
        return 0
    ids = set(ids or [])
    kept = []
    removed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if _line_id(line) in ids:
            removed += 1
            continue
        kept.append(line)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed


def get_prompt_pack(libdir, url):
    """按 url 查已改写的提示词包（prompt_packs.jsonl）"""
    path = pathlib.Path(libdir) / "prompt_packs.jsonl"
    if not path.exists() or not url:
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if rec.get("url") == url:
            return rec.get("pack")
    return None


def save_prompt_pack(libdir, url, pack):
    """保存/覆盖某 url 的改写提示词包"""
    libdir = pathlib.Path(libdir)
    libdir.mkdir(parents=True, exist_ok=True)
    path = libdir / "prompt_packs.jsonl"
    lines = []
    if path.exists():
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = []
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if rec.get("url") != url:
            kept.append(line)
    kept.append(json.dumps({"url": url, "pack": pack}, ensure_ascii=False))
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
