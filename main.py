#!/usr/bin/env python3
"""拆片：把爆款视频拆成公式 —— 链接 → 下载 → 转写 → AI 七维拆解 → 报告 + 库"""
import argparse
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent
_VENDOR = _ROOT / "vendor"
if _VENDOR.exists():
    sys.path.insert(0, str(_VENDOR))

from breakdown.config import llm_key_ready, load_config  # noqa: E402
from breakdown.service import run_pipeline  # noqa: E402
from breakdown import library as lib  # noqa: E402
from breakdown import utils  # noqa: E402

API_KEY_HINT = (
    "❌ 未配置 LLM API Key：请编辑 config.json（参考 config.example.json）或设置环境变量 LLM_API_KEY。\n"
    "   可用 OpenAI 兼容接口：DeepSeek(https://api.deepseek.com/v1) ｜ 火山方舟豆包(https://ark.cn-beijing.volces.com/api/v3) ｜ 智谱(https://open.bigmodel.cn/api/paas/v4)"
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _is_image_file(path):
    try:
        return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    except OSError:
        return False


def cmd_analyze_image(args, cfg):
    """单图深度反推（截图/封面 → 六维分析 + AI 生成提示词），不转写、不入库"""
    from breakdown.vision import analyze_single_image

    vision = cfg.get("vision") or {}
    if not vision.get("model"):
        print(
            "❌ 未启用画面提示词反推：config.json 中 vision.model 为空（需支持图像的模型，如 gpt-4o / doubao-vision / glm-4.6v）",
            file=sys.stderr,
        )
        sys.exit(2)
    path = pathlib.Path(args.url)
    meta = {"url": str(path.resolve()), "title": path.name, "platform": "本地图片", "duration": 0}
    print("🖼 单图深度反推（六维分析）…", file=sys.stderr)
    result = analyze_single_image(path, meta, cfg)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    qp = result.get("quick_prompt") or {}
    print("══════ 单图六维反推结果 ══════")
    if qp.get("zh") or qp.get("en"):
        print(f"📌 快速提示词（可直接粘贴）：\n  {qp.get('zh') or qp.get('en')}\n")
    if result.get("description_zh"):
        print(f"【画面深度描述】\n{result['description_zh']}\n")
    for label, key in (
        ("主体", "subject"), ("环境", "environment"), ("镜头语言", "camera"),
        ("光影", "lighting"), ("美术风格", "style"), ("氛围情绪", "mood"),
    ):
        block = result.get(key)
        if isinstance(block, dict):
            print(f"【{label}】")
            for k, v in block.items():
                if v:
                    print(f"  · {k}：{v}")
            print()
    neg = result.get("negative_prompt") or ""
    if neg:
        print(f"🚫 负面提示词：{neg}")
    params = result.get("params")
    if isinstance(params, dict) and any(params.values()):
        print("🔧 参数建议：" + " ｜ ".join(f"{k} {v}" for k, v in params.items() if v))
    notes = result.get("recreate_notes") or ""
    if notes:
        print(f"💡 复刻建议：{notes}")
    print("════════════════════════════")


def cmd_analyze(args):
    cfg = load_config()
    if _is_image_file(pathlib.Path(args.url)):
        cmd_analyze_image(args, cfg)
        return
    if not llm_key_ready(cfg):
        print(API_KEY_HINT, file=sys.stderr)
        sys.exit(2)
    try:
        opts = {
            "engine": args.engine,
            "whisper_model": args.whisper_model,
            "lang": args.lang,
            "cookies_from_browser": args.cookies_from_browser,
            "cookies_file": args.cookies_file,
            "vision": not args.no_vision,
        }
        report_path, meta, result = run_pipeline(
            args.url, cfg, opts, on_progress=lambda line: print(line, file=sys.stderr)
        )
        print(f"\n✅ 完成：{report_path}")
        if args.json:
            json_path = report_path.with_suffix(".json")
            json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"   LLM 原始 JSON：{json_path}")
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ 拆解失败：{e}", file=sys.stderr)
        sys.exit(1)


def build_parser():
    p = argparse.ArgumentParser(
        prog="chaipian",
        description="拆片：把爆款视频拆成公式 —— 链接 → 下载 → 转写 → AI 七维拆解 → 报告 + 库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python main.py <视频链接>\n  python main.py analyze <视频链接> --engine local --whisper-model small\n  python main.py hooks 钩子\n  python main.py list",
    )
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("analyze", help="拆解一条视频（默认命令，可省略）")
    a.add_argument("url", help="视频链接（B站 / YouTube / 抖音 / 快手 / 小红书等 yt-dlp 支持的站点），或本地视频/音频/图片文件路径（图片走单图六维反推）")
    a.add_argument("--engine", choices=["local", "api"], default=None, help="转写引擎：local=faster-whisper 本地免费（默认），api=OpenAI 兼容 ASR 接口")
    a.add_argument("--whisper-model", default=None, help="本地 Whisper 模型：tiny/base/small/medium/large-v3（默认取 config.json 的 transcribe.whisper_model）")
    a.add_argument("--lang", default="zh", help="转写语言（默认 zh）")
    a.add_argument("--cookies-from-browser", default=None, help="浏览器 cookies（chrome/edge/firefox），新版 Chrome/Edge 可能解密失败，优先用 --cookies-file")
    a.add_argument("--cookies-file", default=None, help="Netscape 格式 cookies.txt 路径（推荐：浏览器扩展 Get cookies.txt LOCALLY 导出）")
    a.add_argument("--json", action="store_true", help="同时输出 LLM 原始 JSON，便于调试 prompt")
    a.add_argument("--no-vision", action="store_true", help="跳过画面提示词反推（即使已配置 vision.model）")

    sub.add_parser("list", help="列出已生成的拆解报告")
    h = sub.add_parser("hooks", help="搜索钩子库（历次拆解积累的公式）")
    h.add_argument("query", nargs="?", default="", help="关键词，留空则列出全部")
    vp = sub.add_parser("prompts", help="搜索反推的视频生成提示词库")
    vp.add_argument("query", nargs="?", default="", help="关键词，留空则列出全部")
    sub.add_parser("config", help="查看当前配置与配置方法")
    return p


def main():
    raw = sys.argv[1:]
    if raw and (raw[0].startswith(("http://", "https://")) or pathlib.Path(raw[0]).is_file()):
        raw = ["analyze"] + raw
    args = build_parser().parse_args(raw)
    cfg = load_config()

    if not args.cmd:
        build_parser().print_help()
        return
    if args.cmd == "analyze":
        cmd_analyze(args)
    elif args.cmd == "list":
        reports = _ROOT / cfg["paths"]["reports"]
        files = sorted(reports.glob("*.md"))
        if not files:
            print("暂无拆解报告。")
        for pth in files:
            print(f"  {pth.name}")
    elif args.cmd == "hooks":
        results = lib.search_hooks(_ROOT / cfg["paths"]["library"], args.query)
        if not results:
            print("钩子库为空，或没有匹配的结果。先跑一次 analyze 吧。")
        for r in results:
            print(f"── {r['date']} ｜ {r['title'][:30]}")
            print(f"   钩子类型：{r.get('hook_type') or '-'} ｜ 一句话钩子：{r.get('hook_one_liner') or '-'}")
            print(f"   钩子公式：{r.get('hook_formula') or '-'}")
            for i, p in enumerate((r.get("reusable") or [])[:3], 1):
                if p:
                    print(f"   可复用{i}：{p}")
            print(f"   可迁移选题：{r.get('transfer_topic') or '-'} ｜ {r.get('url')}")
    elif args.cmd == "prompts":
        results = lib.search_prompts(_ROOT / cfg["paths"]["library"], args.query)
        if not results:
            print("提示词库为空，或没有匹配的结果。配置 vision.model 后跑一次 analyze 吧。")
        for r in results:
            print(f"── {r['date']} ｜ {r['title'][:30]} ｜ {r['platform']}")
            print(f"   类型判断：{r.get('video_type') or '-'}")
            quick = r.get("quick_zh") or r.get("quick_en") or ""
            if quick:
                print(f"   快速提示词：{quick[:80]}")
            neg = r.get("negative_prompt") or ""
            if neg:
                print(f"   负面提示词：{neg[:120]}")
            print(f"   整体提示词(ZH)：{r.get('overall_zh') or '-'}")
            print(f"   整体提示词(EN)：{r.get('overall_en') or '-'}")
            kws = r.get("style_keywords") or []
            print(f"   风格关键词：{', '.join(kws[:8]) if kws else '-'}")
            print(f"   复刻建议：{(r.get('recreate_notes') or '-')[:120]} ｜ {r['url']}")
    elif args.cmd == "config":
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        print("\n配置方法：")
        print("  1) 复制 config.example.json 为 config.json 并填写 api_key；")
        print("  2) 或设置环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。")
        print("  LLM 选型：DeepSeek(deepseek-chat) / 豆包(doubao-*) / GLM(glm-4-plus) / OpenAI(gpt-4o-mini)，按量付费，单次拆解约几分钱。")


if __name__ == "__main__":
    main()
