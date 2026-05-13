from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class LanguageCode(str, Enum):
    ZH = "zh"
    EN = "en"
    JA = "ja"
    KO = "ko"
    YUE = "yue"
    AUTO = "auto"


class ExportFormat(str, Enum):
    MARKDOWN = "markdown"
    MARKMAP = "markmap"
    MERMAID = "mermaid"
    OPML = "opml"
    JSON = "json"


class VideoProcessRequest(BaseModel):
    url: str = Field(..., description="视频URL（支持Bilibili、YouTube等）")
    language: LanguageCode = Field(LanguageCode.AUTO, description="源语言")
    use_asr: bool = Field(True, description="是否使用语音识别（无字幕时）")
    asr_model_size: str = Field("medium", description="Whisper模型大小")
    summarization_method: str = Field("hybrid", description="摘要方法")
    export_formats: list[ExportFormat] = Field(
        [ExportFormat.MARKDOWN, ExportFormat.JSON],
        description="导出格式列表"
    )
    generate_mindmap: bool = Field(True, description="是否生成思维导图")
    webhook_url: Optional[HttpUrl] = Field(None, description="完成回调URL")


class SubtitleProcessRequest(BaseModel):
    file_path: str = Field(..., description="字幕文件路径")
    language: LanguageCode = Field(LanguageCode.ZH, description="字幕语言")
    summarization_method: str = Field("hybrid", description="摘要方法")
    export_formats: list[ExportFormat] = Field(
        [ExportFormat.MARKDOWN, ExportFormat.JSON],
        description="导出格式列表"
    )
    generate_mindmap: bool = Field(True, description="是否生成思维导图")


class AudioProcessRequest(BaseModel):
    file_path: str = Field(..., description="音频文件路径")
    language: LanguageCode = Field(LanguageCode.AUTO, description="音频语言")
    asr_model_size: str = Field("medium", description="Whisper模型大小")
    enable_word_timestamps: bool = Field(False, description="是否启用词级时间戳")
    summarization_method: str = Field("hybrid", description="摘要方法")
    export_formats: list[ExportFormat] = Field(
        [ExportFormat.MARKDOWN, ExportFormat.JSON],
        description="导出格式列表"
    )
    generate_mindmap: bool = Field(True, description="是否生成思维导图")


class BatchProcessRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=20, description="视频URL列表")
    language: LanguageCode = Field(LanguageCode.AUTO, description="源语言")
    asr_model_size: str = Field("medium", description="Whisper模型大小")
    export_formats: list[ExportFormat] = Field(
        [ExportFormat.MARKDOWN, ExportFormat.JSON],
        description="导出格式列表"
    )


class VideoInfoResponse(BaseModel):
    id: str
    title: str
    description: str
    duration: int
    uploader: str
    upload_date: str
    thumbnail: str
    subtitles: list[str]
    automatic_captions: list[str]
    platform: str
    video_id: Optional[str]


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float = Field(0.0, ge=0.0, le=100.0)
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    asr_models_available: list[str]
    supported_platforms: list[str]


class APIError(BaseModel):
    code: int
    message: str
    detail: Optional[str] = None
