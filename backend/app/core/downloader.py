import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import yt_dlp
from loguru import logger

from ..config import settings


class VideoDownloader:
    """视频下载器 - 支持Bilibili、YouTube等平台"""

    BILIBILI_DOMAINS = {
        "bilibili.com", "www.bilibili.com", "m.bilibili.com",
        "b23.tv",
    }

    BILIBILI_VIDEO_PATTERNS = [
        re.compile(r"BV[a-zA-Z0-9]{10}"),
        re.compile(r"av(\d+)"),
        re.compile(r"b23\.tv/[a-zA-Z0-9]+"),
    ]

    def __init__(self):
        self.download_dir = settings.DOWNLOAD_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def detect_platform(self, url: str) -> str:
        """检测视频平台类型"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if any(d in domain for d in self.BILIBILI_DOMAINS):
            return "bilibili"
        elif "youtube.com" in domain or "youtu.be" in domain:
            return "youtube"
        else:
            return "generic"

    def extract_video_id(self, url: str, platform: str) -> Optional[str]:
        """从URL提取视频ID"""
        if platform == "bilibili":
            for pattern in self.BILIBILI_VIDEO_PATTERNS:
                match = pattern.search(url)
                if match:
                    return match.group(0)
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "bvid" in params:
                return params["bvid"][0]
            if "aid" in params:
                return f"av{params['aid'][0]}"
        elif platform == "youtube":
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "v" in params:
                return params["v"][0]
            path_parts = parsed.path.strip("/").split("/")
            if path_parts:
                return path_parts[-1]
        return None

    def get_video_info(self, url: str) -> dict:
        """获取视频元信息（不下载）"""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return {
                    "id": info.get("id", ""),
                    "title": info.get("title", ""),
                    "description": info.get("description", ""),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", ""),
                    "upload_date": info.get("upload_date", ""),
                    "thumbnail": info.get("thumbnail", ""),
                    "subtitles": list(info.get("subtitles", {}).keys()),
                    "automatic_captions": list(info.get("automatic_captions", {}).keys()),
                    "platform": self.detect_platform(url),
                    "video_id": self.extract_video_id(url, self.detect_platform(url)),
                }
            except Exception as e:
                logger.error(f"获取视频信息失败: {e}")
                raise

    def download_audio(self, url: str, output_dir: Optional[Path] = None) -> dict:
        """下载视频音频轨道"""
        output_dir = output_dir or self.download_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_template = str(output_dir / "%(title)s_%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }],
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id", "")
                title = info.get("title", "")
                wav_path = output_dir / f"{title}_{video_id}.wav"

                if not wav_path.exists():
                    possible_paths = list(output_dir.glob(f"*{video_id}*.wav"))
                    wav_path = possible_paths[0] if possible_paths else None

                return {
                    "id": video_id,
                    "title": title,
                    "duration": info.get("duration", 0),
                    "audio_path": str(wav_path) if wav_path else None,
                    "platform": self.detect_platform(url),
                    "audio_format": "wav",
                }
            except Exception as e:
                logger.error(f"下载音频失败: {e}")
                raise

    def download_video(self, url: str, output_dir: Optional[Path] = None) -> dict:
        """下载完整视频文件"""
        output_dir = output_dir or self.download_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_template = str(output_dir / "%(title)s_%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id", "")
                title = info.get("title", "")
                mp4_path = output_dir / f"{title}_{video_id}.mp4"

                if not mp4_path.exists():
                    possible_paths = list(output_dir.glob(f"*{video_id}*.mp4"))
                    mp4_path = possible_paths[0] if possible_paths else None

                return {
                    "id": video_id,
                    "title": title,
                    "duration": info.get("duration", 0),
                    "video_path": str(mp4_path) if mp4_path else None,
                    "platform": self.detect_platform(url),
                    "format": "mp4",
                }
            except Exception as e:
                logger.error(f"下载视频失败: {e}")
                raise

    def download_subtitles(self, url: str, langs: Optional[list] = None) -> dict:
        """下载视频字幕文件"""
        langs = langs or ["zh-Hans", "zh-CN", "zh", "en", "zh-Hant"]

        output_dir = self.download_dir / "subtitles"
        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": langs,
            "skip_download": True,
            "outtmpl": str(output_dir / "%(title)s_%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        subtitle_files = {}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id", "")

                for ext in ["*.vtt", "*.srt", "*.ass", "*.ssa"]:
                    for f in output_dir.glob(f"*{video_id}*{ext.replace('*', '')}"):
                        lang_code = self._detect_subtitle_lang(f.stem)
                        subtitle_files[lang_code] = str(f)

                return {
                    "id": video_id,
                    "title": info.get("title", ""),
                    "subtitle_files": subtitle_files,
                }
            except Exception as e:
                logger.error(f"下载字幕失败: {e}")
                raise

    def separate_audio_video(self, video_path: str) -> dict:
        """从视频文件中分离音频（ffmpeg后端）"""
        video_path = Path(video_path)
        audio_path = video_path.with_suffix(".wav")

        try:
            cmd = [
                "ffmpeg", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-y", str(audio_path),
                "-loglevel", "error",
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            return {
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "sample_rate": 16000,
                "channels": 1,
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"音频分离失败: {e}")
            raise
        except FileNotFoundError:
            logger.error("ffmpeg未安装，请先安装ffmpeg")
            raise

    def _detect_subtitle_lang(self, filename: str) -> str:
        """从文件名检测字幕语言"""
        lang_patterns = {
            "zh-Hans": ["zh-Hans", "zh-CN", "chs", "chi", "简体中文"],
            "zh-Hant": ["zh-Hant", "zh-TW", "cht", "繁體中文"],
            "en": ["en", "eng", "english"],
            "ja": ["ja", "jp", "jpn", "japanese"],
            "ko": ["ko", "kr", "kor", "korean"],
        }

        filename_lower = filename.lower()
        for lang_code, patterns in lang_patterns.items():
            for pattern in patterns:
                if pattern.lower() in filename_lower:
                    return lang_code
        return "unknown"

    def cleanup_downloads(self, pattern: str = "*", older_than_hours: int = 24):
        """清理旧下载文件"""
        import time
        cutoff = time.time() - older_than_hours * 3600

        for f in self.download_dir.rglob(pattern):
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    logger.info(f"已清理: {f}")
                except OSError:
                    pass


downloader = VideoDownloader()
