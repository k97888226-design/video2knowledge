import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Video2Knowledge"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "视频内容智能转知识框架系统"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    OUTPUT_DIR: Path = BASE_DIR / "output"
    TEMP_DIR: Path = BASE_DIR / "temp"
    MODELS_DIR: Path = BASE_DIR / "models"

    WHISPER_MODEL_SIZE: str = "medium"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    MAX_VIDEO_SIZE_MB: int = 2048
    MAX_VIDEO_DURATION_MINUTES: int = 180
    SUPPORTED_LANGUAGES: list = ["zh", "en", "ja", "ko", "yue"]

    SUMMARIZATION_MODEL: str = "facebook/bart-large-cnn"
    SUMMARIZATION_MODEL_ZH: str = "fnlp/bart-base-chinese"

    BILIBILI_SESSDATA: str = ""
    BILIBILI_BUVID3: str = ""

    # Empty string forces yt-dlp to ignore inherited HTTP_PROXY/HTTPS_PROXY.
    # Set this in .env when a proxy is needed, e.g. http://127.0.0.1:7897
    YTDLP_PROXY: str = ""

    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()

for dir_path in [settings.DOWNLOAD_DIR, settings.OUTPUT_DIR, settings.TEMP_DIR, settings.MODELS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
