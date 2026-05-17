import re
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
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
    LanguageCode,
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

SUBTITLE_SUFFIXES = {".srt", ".ass", ".ssa", ".vtt", ".json"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv"}
UPLOAD_SUFFIXES = SUBTITLE_SUFFIXES | AUDIO_SUFFIXES | VIDEO_SUFFIXES


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


def _parse_language(value: str) -> LanguageCode:
    try:
        return LanguageCode(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unsupported language: {value}")


def _parse_export_formats(value: str) -> list[ExportFormat]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values:
        values = [ExportFormat.MARKDOWN.value, ExportFormat.JSON.value]

    try:
        return [ExportFormat(item) for item in values]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unsupported export format: {exc}")


async def _save_upload_file(
    upload: UploadFile,
    allowed_suffixes: set[str],
) -> Path:
    filename = Path(upload.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {allowed}",
        )

    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).stem).strip("._")
    safe_stem = safe_stem or "upload"
    upload_dir = settings.TEMP_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_path = upload_dir / f"{uuid.uuid4().hex}_{safe_stem}{suffix}"

    max_bytes = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
    size = 0
    with open(output_path, "wb") as output:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                output_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.MAX_VIDEO_SIZE_MB} MB limit",
                )
            output.write(chunk)

    await upload.close()
    return output_path


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


@api_router.post("/upload/process", response_model=TaskResponse)
async def process_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subtitle_file: Optional[UploadFile] = File(None),
    language: str = Form("auto"),
    asr_model_size: str = Form("tiny"),
    enable_word_timestamps: bool = Form(False),
    export_formats: str = Form("markdown,json"),
):
    """Process a local subtitle, audio, or video upload."""
    language_code = _parse_language(language)
    formats = _parse_export_formats(export_formats)
    media_path = await _save_upload_file(file, UPLOAD_SUFFIXES)
    suffix = media_path.suffix.lower()

    sidecar_subtitle_path = None
    if subtitle_file and subtitle_file.filename:
        sidecar_subtitle_path = await _save_upload_file(subtitle_file, SUBTITLE_SUFFIXES)

    if suffix in SUBTITLE_SUFFIXES:
        source_type = "subtitle"
    elif suffix in AUDIO_SUFFIXES:
        source_type = "audio"
    elif suffix in VIDEO_SUFFIXES:
        source_type = "video"
    else:
        raise HTTPException(status_code=400, detail="Unsupported upload type")

    if source_type in {"audio", "video"} and not sidecar_subtitle_path:
        raise HTTPException(
            status_code=400,
            detail="稳定模式需要字幕文件：请上传字幕文件，或上传视频时同时选择字幕文件。",
        )

    task = _create_task()
    background_tasks.add_task(
        _process_upload_pipeline,
        task["task_id"],
        str(media_path),
        source_type,
        language_code,
        asr_model_size,
        enable_word_timestamps,
        formats,
        str(sidecar_subtitle_path) if sidecar_subtitle_path else None,
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
            segments,
            request.language.value,
            export_formats=[fmt.value for fmt in request.export_formats],
        ) if segments else knowledge_builder.build(
            "\n\n".join(paragraph_input),
            request.language.value,
            export_formats=[fmt.value for fmt in request.export_formats],
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
                "interview_questions": result.get("interview_questions", []),
                "flashcards": result.get("flashcards", []),
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


async def _process_upload_pipeline(
    task_id: str,
    media_path: str,
    source_type: str,
    language: LanguageCode,
    asr_model_size: str,
    enable_word_timestamps: bool,
    export_formats: list[ExportFormat],
    subtitle_path: Optional[str] = None,
):
    """Process an uploaded local file without downloading from a platform."""
    media_file = Path(media_path)
    subtitle_file = Path(subtitle_path) if subtitle_path else None
    effective_language = language.value if language.value != "auto" else "zh"

    try:
        if not media_file.exists():
            raise FileNotFoundError(f"File not found: {media_file}")
        if subtitle_file and not subtitle_file.exists():
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_file}")

        transcript_text = ""
        segments = []
        asr_info = {}

        if source_type == "subtitle" or subtitle_file:
            source = subtitle_file or media_file
            _update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=20,
                message="正在解析字幕文件...",
            )
            entries = subtitle_parser.parse(str(source))
            transcript_text = subtitle_parser.get_full_text(entries)
            segments = [
                {"text": entry.text, "start": entry.start, "end": entry.end}
                for entry in entries
            ]
        else:
            audio_path = media_file
            if source_type == "video":
                _update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=15,
                    message="正在从视频中提取音频...",
                )
                separated = downloader.separate_audio_video(str(media_file))
                audio_path = Path(separated["audio_path"])

            _update_task(
                task_id,
                status=TaskStatus.TRANSCRIBING,
                progress=35,
                message="正在进行语音识别...",
            )
            asr_engine.load_model(asr_model_size)
            transcribe_language = None if language.value == "auto" else language.value
            if enable_word_timestamps:
                asr_result = asr_engine.transcribe_with_word_timestamps(
                    str(audio_path),
                    language=transcribe_language,
                )
            else:
                asr_result = asr_engine.transcribe(
                    str(audio_path),
                    language=transcribe_language,
                )

            transcript_text = asr_result.get("text", "")
            segments = asr_result.get("segments", [])
            detected_language = asr_result.get("language")
            if (
                language.value == "auto"
                and detected_language in settings.SUPPORTED_LANGUAGES
            ):
                effective_language = detected_language
            asr_info = {
                "language": detected_language,
                "language_probability": asr_result.get("language_probability"),
                "duration_seconds": asr_result.get("duration_seconds"),
                "engine": asr_result.get("engine"),
                "model_size": asr_result.get("model_size"),
                "rtf": asr_result.get("rtf"),
            }

        if not transcript_text:
            raise Exception("未能从上传文件中获取文本内容")

        _update_task(task_id, progress=60, message="正在清洗文本...")
        cleaned_text = text_cleaner.clean(transcript_text, effective_language)

        _update_task(
            task_id,
            status=TaskStatus.SUMMARIZING,
            progress=80,
            message="正在生成知识框架...",
        )
        result = knowledge_builder.build_from_segments(
            segments,
            effective_language,
            export_formats=[fmt.value for fmt in export_formats],
        ) if segments else knowledge_builder.build(
            cleaned_text,
            effective_language,
            export_formats=[fmt.value for fmt in export_formats],
        )

        _update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="处理完成",
            result={
                "title": media_file.stem,
                "source_type": source_type,
                "file_name": media_file.name,
                "asr_info": asr_info,
                "knowledge_tree": result.get("knowledge_tree", {}),
                "summary": result.get("summary", ""),
                "keywords": result.get("keywords", []),
                "statistics": result.get("statistics", {}),
                "interview_questions": result.get("interview_questions", []),
                "flashcards": result.get("flashcards", []),
                "segments": segments[:100],
                "exports": {
                    fmt.value: result.get("exports", {}).get(fmt.value, "")
                    for fmt in export_formats
                },
            },
        )

    except Exception as e:
        logger.error(f"上传任务 {task_id} 失败: {e}")
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
            segments,
            request.language.value,
            export_formats=[fmt.value for fmt in request.export_formats],
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
                "interview_questions": result.get("interview_questions", []),
                "flashcards": result.get("flashcards", []),
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
            segments,
            request.language.value,
            export_formats=[fmt.value for fmt in request.export_formats],
        ) if segments else knowledge_builder.build(
            cleaned_text,
            request.language.value,
            export_formats=[fmt.value for fmt in request.export_formats],
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
                "interview_questions": result.get("interview_questions", []),
                "flashcards": result.get("flashcards", []),
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
