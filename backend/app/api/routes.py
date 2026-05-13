import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from loguru import logger

from .schemas import (
    VideoProcessRequest,
    SubtitleProcessRequest,
    AudioProcessRequest,
    BatchProcessRequest,
    VideoInfoResponse,
    TaskResponse,
    HealthResponse,
    TaskStatus,
    ExportFormat,
)
from ..config import settings
from ..core.downloader import downloader
from ..core.asr import asr_engine
from ..core.subtitle_parser import subtitle_parser, SubtitleEntry
from ..core.text_cleaner import text_cleaner
from ..core.summarizer import summarizer
from ..core.knowledge_builder import knowledge_builder

api_router = APIRouter(prefix=settings.API_PREFIX)

task_store: dict[str, dict] = {}


def _create_task() -> dict:
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "progress": 0.0,
        "message": "任务已创建",
        "result": None,
        "error": None,
    }
    task_store[task_id] = task
    return task


def _update_task(task_id: str, **kwargs):
    if task_id in task_store:
        task_store[task_id].update(kwargs)


@api_router.get("/health", response_model=HealthResponse)
async def health_check():
    """系统健康检查"""
    return HealthResponse(
        status="ok",
        version=settings.PROJECT_VERSION,
        asr_models_available=asr_engine.MODEL_SIZES,
        supported_platforms=["bilibili", "youtube", "generic"],
    )


@api_router.post("/video/info", response_model=VideoInfoResponse)
async def get_video_info(url: str):
    """获取视频元信息"""
    try:
        info = downloader.get_video_info(url)
        return VideoInfoResponse(**info)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取视频信息失败: {str(e)}")


@api_router.post("/video/process", response_model=TaskResponse)
async def process_video(
    request: VideoProcessRequest,
    background_tasks: BackgroundTasks,
):
    """处理视频：下载 -> 转写 -> 摘要 -> 知识框架"""
    task = _create_task()

    background_tasks.add_task(
        _process_video_pipeline,
        task["task_id"],
        request,
    )

    return TaskResponse(**task)


async def _process_video_pipeline(task_id: str, request: VideoProcessRequest):
    """视频处理流水线"""
    try:
        _update_task(task_id, status=TaskStatus.DOWNLOADING, progress=10,
                     message="正在获取视频信息...")

        info = downloader.get_video_info(request.url)

        _update_task(task_id, progress=20,
                     message=f"正在下载: {info.get('title', '')}")

        subtitle_data = _try_download_subtitles(request.url, request.language)
        transcript_text = ""
        segments = []

        if subtitle_data and subtitle_data.get("subtitle_files"):
            _update_task(task_id, progress=40,
                         message="正在解析字幕文件...")

            all_entries = []
            for lang_code, file_path in subtitle_data["subtitle_files"].items():
                entries = subtitle_parser.parse(file_path)
                all_entries.extend(entries)

            all_entries.sort(key=lambda x: x.start)
            transcript_text = subtitle_parser.get_full_text(all_entries)
            segments = [
                {
                    "text": e.text,
                    "start": e.start,
                    "end": e.end,
                }
                for e in all_entries
            ]

        elif request.use_asr:
            _update_task(task_id, status=TaskStatus.DOWNLOADING, progress=30,
                         message="无字幕，正在下载音频...")

            audio_result = downloader.download_audio(request.url)

            if audio_result.get("audio_path"):
                _update_task(
                    task_id, status=TaskStatus.TRANSCRIBING, progress=50,
                    message="正在进行语音识别..."
                )

                asr_result = asr_engine.transcribe(
                    audio_result["audio_path"],
                    language=request.language.value if request.language.value != "auto" else None,
                )

                transcript_text = asr_result.get("text", "")
                segments = asr_result.get("segments", [])
            else:
                raise Exception("无法下载音频")

        if not transcript_text:
            raise Exception("未能获取视频文本内容")

        _update_task(task_id, progress=60, message="正在清洗文本...")
        cleaned_text = text_cleaner.clean(transcript_text, request.language.value)

        _update_task(task_id, status=TaskStatus.SUMMARIZING, progress=70,
                     message="正在生成知识框架...")

        paragraph_input = text_cleaner.segment_paragraphs(
            cleaned_text, request.language.value, method="semantic"
        )

        result = knowledge_builder.build_from_segments(
            segments, request.language.value
        ) if segments else knowledge_builder.build(
            "\n\n".join(paragraph_input), request.language.value
        )

        exports = {}
        for fmt in request.export_formats:
            exports[fmt.value] = result.get("exports", {}).get(fmt.value, "")

        _update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="处理完成",
            result={
                "title": result.get("title", info.get("title", "")),
                "video_info": info,
                "knowledge_tree": result.get("knowledge_tree", {}),
                "summary": result.get("summary", ""),
                "keywords": result.get("keywords", []),
                "statistics": result.get("statistics", {}),
                "segments": segments[:50],
                "exports": exports,
            }
        )

        if request.webhook_url:
            await _send_webhook(str(request.webhook_url), task_store[task_id])

    except Exception as e:
        logger.error(f"任务 {task_id} 失败: {e}")
        _update_task(
            task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="处理失败",
            error=str(e),
        )


def _try_download_subtitles(url: str, language) -> Optional[dict]:
    """尝试下载字幕"""
    try:
        langs = ["zh-Hans", "zh-CN", "zh", "en"]
        if language and language.value not in ["auto"]:
            langs.insert(0, language.value)
        return downloader.download_subtitles(url, langs)
    except Exception:
        return None


async def _send_webhook(webhook_url: str, task_data: dict):
    """发送webhook通知"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=task_data, timeout=10)
    except Exception as e:
        logger.warning(f"Webhook发送失败: {e}")


@api_router.post("/subtitle/process", response_model=TaskResponse)
async def process_subtitle(
    request: SubtitleProcessRequest,
    background_tasks: BackgroundTasks,
):
    """处理字幕文件"""
    task = _create_task()

    background_tasks.add_task(
        _process_subtitle_pipeline,
        task["task_id"],
        request,
    )

    return TaskResponse(**task)


async def _process_subtitle_pipeline(task_id: str, request: SubtitleProcessRequest):
    """字幕处理流水线"""
    try:
        file_path = Path(request.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {request.file_path}")

        _update_task(task_id, status=TaskStatus.PROCESSING, progress=20,
                     message="正在解析字幕...")

        entries = subtitle_parser.parse(str(file_path))
        full_text = subtitle_parser.get_full_text(entries)

        _update_task(task_id, progress=40, message="正在清洗文本...")
        cleaned_text = text_cleaner.clean(full_text, request.language.value)

        _update_task(task_id, status=TaskStatus.SUMMARIZING, progress=60,
                     message="正在生成知识框架...")

        segments = [
            {"text": e.text, "start": e.start, "end": e.end}
            for e in entries
        ]

        result = knowledge_builder.build_from_segments(
            segments, request.language.value
        )

        _update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="处理完成",
            result={
                "title": file_path.stem,
                "knowledge_tree": result.get("knowledge_tree", {}),
                "summary": result.get("summary", ""),
                "keywords": result.get("keywords", []),
                "statistics": result.get("statistics", {}),
                "exports": {
                    fmt.value: result.get("exports", {}).get(fmt.value, "")
                    for fmt in request.export_formats
                },
            }
        )

    except Exception as e:
        logger.error(f"任务 {task_id} 失败: {e}")
        _update_task(
            task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="处理失败",
            error=str(e),
        )


@api_router.post("/audio/process", response_model=TaskResponse)
async def process_audio(
    request: AudioProcessRequest,
    background_tasks: BackgroundTasks,
):
    """处理音频文件"""
    task = _create_task()

    background_tasks.add_task(
        _process_audio_pipeline,
        task["task_id"],
        request,
    )

    return TaskResponse(**task)


async def _process_audio_pipeline(task_id: str, request: AudioProcessRequest):
    """音频处理流水线"""
    try:
        file_path = Path(request.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {request.file_path}")

        _update_task(task_id, status=TaskStatus.PROCESSING, progress=10,
                     message="正在加载ASR模型...")

        asr_engine.load_model(request.asr_model_size)

        _update_task(task_id, status=TaskStatus.TRANSCRIBING, progress=30,
                     message="正在进行语音识别...")

        if request.enable_word_timestamps:
            asr_result = asr_engine.transcribe_with_word_timestamps(
                str(file_path),
                language=request.language.value if request.language.value != "auto" else None,
            )
        else:
            asr_result = asr_engine.transcribe(
                str(file_path),
                language=request.language.value if request.language.value != "auto" else None,
            )

        transcript_text = asr_result.get("text", "")
        segments = asr_result.get("segments", [])

        _update_task(task_id, progress=60, message="正在清洗文本...")
        cleaned_text = text_cleaner.clean(transcript_text, request.language.value)

        _update_task(task_id, status=TaskStatus.SUMMARIZING, progress=80,
                     message="正在生成知识框架...")

        result = knowledge_builder.build_from_segments(
            segments, request.language.value
        ) if segments else knowledge_builder.build(
            cleaned_text, request.language.value
        )

        _update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="处理完成",
            result={
                "title": file_path.stem,
                "asr_info": {
                    "language": asr_result.get("language", ""),
                    "language_probability": asr_result.get("language_probability"),
                    "duration_seconds": asr_result.get("duration_seconds"),
                    "engine": asr_result.get("engine"),
                    "model_size": asr_result.get("model_size"),
                    "rtf": asr_result.get("rtf"),
                },
                "knowledge_tree": result.get("knowledge_tree", {}),
                "summary": result.get("summary", ""),
                "keywords": result.get("keywords", []),
                "statistics": result.get("statistics", {}),
                "segments": segments[:100],
                "exports": {
                    fmt.value: result.get("exports", {}).get(fmt.value, "")
                    for fmt in request.export_formats
                },
            }
        )

    except Exception as e:
        logger.error(f"任务 {task_id} 失败: {e}")
        _update_task(
            task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="处理失败",
            error=str(e),
        )


@api_router.post("/batch/process", response_model=dict)
async def process_batch(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks,
):
    """批量处理视频"""
    batch_id = str(uuid.uuid4())
    tasks = []

    for url in request.urls:
        video_request = VideoProcessRequest(
            url=url,
            language=request.language,
            asr_model_size=request.asr_model_size,
            export_formats=request.export_formats,
            generate_mindmap=True,
        )

        task = _create_task()
        tasks.append(task["task_id"])

        background_tasks.add_task(
            _process_video_pipeline,
            task["task_id"],
            video_request,
        )

    return {
        "batch_id": batch_id,
        "task_ids": tasks,
        "total": len(tasks),
    }


@api_router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """查询任务状态"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskResponse(**task)


@api_router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(limit: int = 20):
    """列出最近任务"""
    tasks = list(task_store.values())
    tasks.sort(key=lambda t: t.get("task_id", ""), reverse=True)
    return [TaskResponse(**t) for t in tasks[:limit]]


@api_router.get("/task/{task_id}/export/{format}")
async def export_task_result(task_id: str, format: str):
    """导出任务结果"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task["status"] != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务未完成")

    result = task.get("result", {})
    exports = result.get("exports", {})

    if format not in exports:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")

    output_dir = settings.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task_id}.{format}"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(exports[format])

    content_types = {
        "markdown": "text/markdown",
        "markmap": "text/markdown",
        "mermaid": "text/plain",
        "opml": "application/xml",
        "json": "application/json",
    }

    return FileResponse(
        output_path,
        media_type=content_types.get(format, "text/plain"),
        filename=f"knowledge_{task_id[:8]}.{format}",
    )
