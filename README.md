# 拆片（chaipian）

> 个人自用的短视频逆向解析工具：**粘贴链接 → 下载 → 语音转写 → AI 七维拆解（+画面提示词反推）→ Markdown 报告 + 本地库**。把爆款视频拆成可复制的公式。
> 方法论见 [docs/爆款视频逆向解析调研报告.md](docs/爆款视频逆向解析调研报告.md) 与 [docs/爆款视频拆解模板.md](docs/爆款视频拆解模板.md)。

## 功能

- 支持 B站 / YouTube / 抖音 / 快手 / 小红书等 yt-dlp 可解析的站点（音频轨下载）
- 本地 faster-whisper 转写（免费）或 OpenAI 兼容 ASR 接口
- 任意 OpenAI 兼容 LLM（DeepSeek / 豆包 / 智谱 / OpenAI）按"七维拆解模型"输出结构化 JSON
- **画面提示词反推（可选）**：抽关键帧 + 多模态视觉模型，反推"这条视频用 AI 怎么生成"的文生视频/图生视频提示词（分镜级）
- 自动生成 Markdown 拆解报告（对齐人工模板的 11 个模块 + 提示词反推第 12 节）
- 自动沉淀 `library/index.csv`（与《爆款视频拆解表.csv》同字段，可直接 Excel 打开）、`library/hooks.jsonl`（钩子公式库）和 `library/prompts.jsonl`（提示词库），均支持检索

## 安装

```bash
# 依赖装进工作区 vendor/（不污染全局）
python -m pip install --target vendor -r requirements.txt
```

配置（二选一）：

```bash
copy config.example.json config.json   # 填写 llm.api_key（DeepSeek/豆包/智谱等）
# 或设置环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
```

## Web 界面（推荐日常使用）

```bash
python webui.py            # 默认 http://127.0.0.1:8765，自动打开浏览器
python webui.py --port 9000 --no-open
```

页面上：粘贴链接 → 开始拆解 → 左侧实时日志 → 报告即出；另有钩子库 / 提示词库 / 历史报告三个面板。所有数据只在本机（仅绑定 127.0.0.1）。

## 命令行

```bash
# 拆解一条视频（最简用法）
python main.py "https://www.bilibili.com/video/BVxxxxxx"

# 指定转写引擎与 Whisper 模型（tiny/base/small/medium）
python main.py analyze "https://www.youtube.com/watch?v=xxxx" --engine local --whisper-model small

# 部分视频需要登录态（B站会员/部分抖音内容）
python main.py analyze "链接" --cookies-from-browser chrome

# 输出 LLM 原始 JSON（调试 prompt 用）
python main.py analyze "链接" --json

# 查看报告与检索钩子库 / 提示词库
python main.py list
python main.py hooks 钩子
python main.py prompts 运镜
python main.py config
```

### 启用画面提示词反推（拆出"AI 生成提示词"）

在 `config.json` 里填 vision 配置（base_url/api_key 留空则复用 llm 的）：

```json
"vision": {
  "model": "gpt-4o-mini",
  "base_url": "",
  "api_key": "",
  "max_frames": 8
}
```

- 需要**支持图像输入**的模型：gpt-4o / gpt-4o-mini、豆包视觉系列（火山方舟 `doubao-1.5-vision-pro`）、智谱 `glm-4v`、通义 `qwen-vl-plus` 等；**DeepSeek 纯文本不支持**；
- 启用后会自动下载带画面的视频并抽帧（PyAV 解码，无需安装 ffmpeg），报告新增第 12 节"画面提示词反推"：整体文生视频提示词（中英）、分镜提示词表、风格关键词、图生视频模板、复刻建议；
- 反推结果同时存入 `library/prompts.jsonl`，`python main.py prompts <关键词>` 可检索；
- 不想要时：删掉 vision.model 或加 `--no-vision`。

首次运行本地转写会自动下载 Whisper 模型（small 约 460MB），之后离线可用。

## 产出

```
reports/2026-01-01-标题.md     # 拆解报告（Markdown）
library/index.csv              # 拆解汇总表（Excel 可开）
library/hooks.jsonl            # 钩子/公式库（main.py hooks 可检索）
library/prompts.jsonl          # 反推提示词库（main.py prompts 可检索，需启用 vision）
work/                          # 下载的媒体临时文件
```

## 注意

- 下载解析仅限学习研究自用，请遵守平台用户协议与版权法规；不要搬运发布。
- 完播率、转发、评论区等后台指标需人工在创作者后台补充（报告中有"待补充"标注）。
- 抖音/小红书等平台接口易变，如下载失败可改用 `--cookies-from-browser` 或手动准备本地文件（后续版本支持）。
