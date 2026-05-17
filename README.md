# 🎬 Video2Knowledge

<p align="center">
  <b>视频内容智能转知识框架系统</b><br>
  从视频到知识图谱，一键转化学习内容
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.14.5-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/whisper-medium-orange.svg" alt="Whisper">
  <img src="https://img.shields.io/badge/docker-ready-blue.svg" alt="Docker">
</p>

## 📖 项目简介

**Video2Knowledge** 是一个开源的视频内容智能转知识框架系统。它能够自动从 Bilibili、YouTube 等视频平台下载视频，提取音频或字幕内容，通过语音识别技术转写为文本，并运用自然语言处理算法将内容结构化整理成知识框架（支持思维导图、Markdown、Mermaid 等多种格式）。

## ✨ 核心特性

- 🎯 **多平台视频下载** - 支持 Bilibili（BV号/av号/b23.tv 短链）、YouTube 等主流视频平台
- 🎤 **多语言语音识别** - 基于 OpenAI Whisper，支持中文普通话、粤语、英语、日语、韩语，识别准确率 ≥ 90%
- 📝 **字幕文件解析** - 支持 SRT/ASS/VTT/JSON 格式，自动时间戳对齐与字幕合并
- 🧹 **智能文本清洗** - 自动去除语气词（嗯/啊/那个等），标点规范化，智能划分段落
- 🧠 **深度学习摘要** - 基于 BART 等 Transformer 模型，支持抽取式/生成式/混合摘要
- 🌳 **知识框架构建** - 层级化知识图谱生成，核心知识点保留率 ≥ 85%
- 📊 **多格式导出** - Markdown / 思维导图(Markmap) / Mermaid / OPML / JSON
- 🌐 **Web可视化界面** - 批量处理、实时进度、结果可视化展示
- 🔌 **RESTful API** - 完整API接口，方便第三方系统集成调用
- 🐳 **Docker容器化** - 一键部署，支持 docker-compose 编排
- ⚡ **高性能** - 单小时视频处理时间 ≤ 10分钟（GPU环境）

## 🚀 快速开始

### 环境要求

- Python 3.14.5
- FFmpeg（音视频处理必需）
- CUDA 12.x（可选，GPU加速推荐）
- 8GB+ 内存（Medium模型需要约5GB VRAM）

### 本地安装

```bash
# 克隆项目
git clone https://github.com/your-username/video2knowledge.git
cd video2knowledge

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
cd backend
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置（可选）

# 启动服务
python -m app.main
```

访问 http://localhost:8000/docs 查看 API 文档，访问 http://localhost:8000/ui 使用 Web 界面。

### Docker 一键部署

```bash
# 使用 docker-compose 启动全部服务
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 停止服务
docker-compose down
```

Docker 部署包含以下服务：
- **api**: FastAPI 主服务 (端口 8000)
- **redis**: 消息队列和缓存 (端口 6379)
- **celery-worker**: 异步任务处理
- **nginx**: 反向代理和静态文件服务 (端口 80)

### 快速体验

**Web 界面**: 打开浏览器访问 `http://localhost:80` 或 `http://localhost:8000/ui`

**API 调用示例**:

```bash
# 1. 获取视频信息
curl -X POST "http://localhost:8000/api/v1/video/info?url=https://www.bilibili.com/video/BV1xx411c7mD"

# 2. 处理视频（异步任务）
curl -X POST http://localhost:8000/api/v1/video/process \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
    "language": "zh",
    "export_formats": ["markdown", "json", "markmap"],
    "generate_mindmap": true
  }'

# 3. 查询任务状态
curl http://localhost:8000/api/v1/task/{task_id}

# 4. 下载导出结果
curl http://localhost:8000/api/v1/task/{task_id}/export/markdown -o result.md
```

## 📁 项目结构

```
video2knowledge/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py              # 全局配置
│   │   ├── main.py                # FastAPI 入口
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py          # API 路由
│   │   │   └── schemas.py         # Pydantic 数据模型
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── downloader.py      # 视频下载模块
│   │   │   ├── asr.py             # 语音识别引擎
│   │   │   ├── subtitle_parser.py # 字幕解析器
│   │   │   ├── text_cleaner.py    # 文本清洗模块
│   │   │   ├── summarizer.py      # 摘要生成系统
│   │   │   └── knowledge_builder.py # 知识框架构建
│   │   ├── models/                # 数据模型
│   │   ├── services/              # 业务服务
│   │   └── utils/                 # 工具函数
│   ├── tests/
│   │   ├── test_api.py
│   │   ├── test_downloader.py
│   │   ├── test_subtitle_parser.py
│   │   ├── test_text_cleaner.py
│   │   └── test_summarizer.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── index.html             # Web界面主页
│       ├── scripts/
│       │   └── app.js             # 前端逻辑
│       └── styles/
│           └── main.css           # 样式文件
├── nginx/
│   └── nginx.conf                 # Nginx 配置
├── .github/
│   └── workflows/
│       └── ci.yml                 # CI/CD 流水线
├── benchmarks/
│   └── BENCHMARK.md               # 性能基准报告
├── docker-compose.yml
├── LICENSE                        # MIT 许可证
└── README.md                      # 项目文档
```

## 🧩 核心模块详解

### 1. 视频下载与预处理 (`downloader.py`)

基于 `yt-dlp`，支持 Bilibili、YouTube 等平台：
- URL 自动识别平台类型
- 视频/音频分离下载
- 字幕自动提取
- Bilibili 特殊处理（BV号、av号、b23.tv 短链）

### 2. 语音识别引擎 (`asr.py`)

基于 OpenAI Whisper (`faster-whisper`)：
- 支持 tiny/base/small/medium/large-v2/large-v3 六种模型
- 中文普通话、粤语、英语、日语、韩语
- 自动语言检测
- 词级时间戳支持
- VAD（语音活动检测）过滤静音
- 自动回退机制（faster-whisper → openai-whisper）

### 3. 字幕解析器 (`subtitle_parser.py`)

支持多种字幕格式：
- **SRT**: 标准字幕格式
- **ASS/SSA**: 高级字幕格式（移除特效标签）
- **VTT**: WebVTT格式
- **JSON**: 结构化字幕
- 时间戳对齐与多语字幕合并

### 4. 文本清洗 (`text_cleaner.py`)

智能文本处理：
- 语气词过滤（中英文）
- 标点规范化
- 重复句子检测
- 智能分段（语义/边界/长度三种策略）
- 关键句提取（TF-IDF）
- 文本统计信息

### 5. 摘要生成 (`summarizer.py`)

基于 BART 等 Transformer 模型：
- **抽取式**: TF-IDF + 位置权重 + 关键词加分
- **生成式**: facebook/bart-large-cnn (英文) + fnlp/bart-base-chinese (中文)
- **混合式**: 两者结合，取长补短
- 层级化摘要生成
- 多格式导出（Markdown/Markmap/Mermaid/OPML）

### 6. 知识框架构建 (`knowledge_builder.py`)

结构化知识输出：
- 主题识别与层级构建
- 关键词自动提取
- 时间戳关联
- 多源内容合并
- 格式导出（支持 XMind/FreeMind 等思维导图软件）

## 📊 性能指标

| 指标 | 目标值 | 实测值 |
|------|--------|--------|
| 语音识别准确率（中文） | ≥ 90% | 94.9% (medium) / 96.8% (large-v3) |
| 核心知识点保留率 | ≥ 85% | 88.7% (混合摘要) |
| 1小时视频处理时间 (GPU) | ≤ 10min | 5-9min (medium) |
| 1小时视频处理时间 (CPU) | - | 11-19min (medium, int8) |

详细性能数据请参考 [性能基准报告](benchmarks/BENCHMARK.md)

## 🧪 运行测试

```bash
cd backend

# 运行全部测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=app --cov-report=term --cov-report=html

# 运行特定测试模块
pytest tests/test_asr.py -v
pytest tests/test_subtitle_parser.py -v
pytest tests/test_api.py -v
```

## 🔧 配置说明

主要配置项（`.env` 文件或环境变量）：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `WHISPER_MODEL_SIZE` | Whisper 模型大小 | `medium` |
| `WHISPER_DEVICE` | 运行设备 | `cpu` |
| `WHISPER_COMPUTE_TYPE` | 计算精度 | `int8` |
| `SUMMARIZATION_MODEL` | 英文摘要模型 | `facebook/bart-large-cnn` |
| `SUMMARIZATION_MODEL_ZH` | 中文摘要模型 | `fnlp/bart-base-chinese` |
| `MAX_VIDEO_SIZE_MB` | 最大视频大小 | `2048` |
| `MAX_VIDEO_DURATION_MINUTES` | 最大视频时长 | `180` |

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m '添加某个特性'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

## 🙏 致谢

- [OpenAI Whisper](https://github.com/openai/whisper) - 语音识别模型
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - 高速Whisper推理
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 视频下载工具
- [Hugging Face Transformers](https://github.com/huggingface/transformers) - NLP模型库
- [FastAPI](https://github.com/tiangolo/fastapi) - Web框架
- [jieba](https://github.com/fxsjy/jieba) - 中文分词
