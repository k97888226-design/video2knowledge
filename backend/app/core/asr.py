import time
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger

from ..config import settings


class ASREngine:
    """多语言语音识别引擎 - 基于OpenAI Whisper"""

    LANGUAGE_MAP = {
        "zh": "chinese (mandarin)",
        "yue": "chinese (cantonese)",
        "en": "english",
        "ja": "japanese",
        "ko": "korean",
        "auto": "auto-detect",
    }

    MODEL_SIZES = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]

    def __init__(self):
        self.model = None
        self.model_size = settings.WHISPER_MODEL_SIZE
        self.device = settings.WHISPER_DEVICE
        self.compute_type = settings.WHISPER_COMPUTE_TYPE
        self._loaded_model_size = None

    def load_model(self, model_size: Optional[str] = None) -> None:
        """加载Whisper模型"""
        model_size = model_size or self.model_size

        if model_size not in self.MODEL_SIZES:
            raise ValueError(f"不支持的模型大小: {model_size}. 可选: {self.MODEL_SIZES}")

        if self._loaded_model_size == model_size and self.model is not None:
            return

        try:
            from faster_whisper import WhisperModel

            logger.info(f"正在加载 Whisper {model_size} 模型...")
            self.model = WhisperModel(
                model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._loaded_model_size = model_size
            logger.info(f"Whisper {model_size} 模型加载完成")

        except ImportError:
            logger.warning("faster-whisper 未安装，回退到 openai-whisper")
            self._load_openai_whisper(model_size)

    def _load_openai_whisper(self, model_size: str) -> None:
        """回退到openai-whisper实现"""
        import whisper

        logger.info(f"正在加载 OpenAI Whisper {model_size} 模型...")
        self.model = whisper.load_model(model_size)
        self._loaded_model_size = model_size
        self._use_faster_whisper = False
        logger.info(f"OpenAI Whisper {model_size} 模型加载完成")

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> dict:
        """语音转文本"""
        if self.model is None:
            self.load_model()

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        start_time = time.time()

        try:
            result = self._transcribe_faster_whisper(audio_path, language, task)
        except AttributeError:
            result = self._transcribe_openai_whisper(audio_path, language, task)

        elapsed = time.time() - start_time
        audio_duration = result.get("duration_seconds", 0)
        if audio_duration > 0:
            result["rtf"] = elapsed / audio_duration

        return result

    def _transcribe_faster_whisper(
        self,
        audio_path: Path,
        language: Optional[str],
        task: str,
    ) -> dict:
        """使用faster-whisper进行转录"""
        self._ensure_model_loaded()

        transcribe_options = {
            "task": task,
            "beam_size": 5,
            "best_of": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
        }

        if language and language != "auto":
            transcribe_options["language"] = language

        segments_result, info = self.model.transcribe(
            str(audio_path), **transcribe_options
        )

        segments = []
        full_text = []
        raw_segments = []

        for segment in segments_result:
            seg_dict = {
                "id": segment.id,
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": segment.text.strip(),
                "avg_logprob": round(segment.avg_logprob, 4) if segment.avg_logprob else None,
                "no_speech_prob": round(segment.no_speech_prob, 4) if segment.no_speech_prob else None,
            }
            segments.append(seg_dict)
            raw_segments.append(seg_dict)
            if seg_dict["text"]:
                full_text.append(seg_dict["text"])

        detected_language = info.language
        language_prob = info.language_probability

        return {
            "text": " ".join(full_text),
            "segments": segments,
            "raw_segments": raw_segments,
            "language": detected_language,
            "language_probability": round(language_prob, 4) if language_prob else None,
            "duration_seconds": round(info.duration, 2),
            "model_size": self._loaded_model_size,
            "engine": "faster-whisper",
        }

    def _transcribe_openai_whisper(
        self,
        audio_path: Path,
        language: Optional[str],
        task: str,
    ) -> dict:
        """使用openai-whisper进行转录"""
        transcribe_options = {
            "task": task,
            "fp16": False,
            "verbose": False,
        }

        if language and language != "auto":
            transcribe_options["language"] = language

        result = self.model.transcribe(str(audio_path), **transcribe_options)

        segments = []
        for i, seg in enumerate(result.get("segments", [])):
            segments.append({
                "id": seg.get("id", i),
                "start": round(seg["start"], 3),
                "end": round(seg["end"], 3),
                "text": seg["text"].strip(),
                "avg_logprob": round(seg.get("avg_logprob", 0), 4),
                "no_speech_prob": round(seg.get("no_speech_prob", 0), 4),
            })

        return {
            "text": result["text"].strip(),
            "segments": segments,
            "raw_segments": segments,
            "language": result.get("language", "unknown"),
            "duration_seconds": round(result.get("duration", 0), 2),
            "model_size": self._loaded_model_size,
            "engine": "openai-whisper",
        }

    def transcribe_with_word_timestamps(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> dict:
        """带词级时间戳的语音识别"""
        result = self.transcribe(audio_path, language)

        self._ensure_model_loaded()

        try:
            word_segments, info = self.model.transcribe(
                str(audio_path),
                word_timestamps=True,
                vad_filter=True,
            )

            word_timestamps = []
            for segment in word_segments:
                if segment.words:
                    for word in segment.words:
                        word_timestamps.append({
                            "word": word.word,
                            "start": round(word.start, 3),
                            "end": round(word.end, 3),
                            "probability": round(word.probability, 4) if word.probability else None,
                        })

            result["word_timestamps"] = word_timestamps
        except Exception as e:
            logger.warning(f"词级时间戳提取失败: {e}")
            result["word_timestamps"] = []

        return result

    def detect_language(self, audio_path: str) -> dict:
        """检测音频语言"""
        if self.model is None:
            self.load_model("base")

        audio_path = Path(audio_path)

        try:
            _, info = self.model.transcribe(
                str(audio_path),
                beam_size=1,
                best_of=1,
                vad_filter=True,
            )

            return {
                "language": info.language,
                "language_name": self.LANGUAGE_MAP.get(info.language, info.language),
                "probability": round(info.language_probability, 4),
            }
        except AttributeError:
            return self._detect_language_openai(audio_path)

    def _detect_language_openai(self, audio_path: Path) -> dict:
        """OpenAI Whisper语言检测"""
        import whisper

        audio = whisper.load_audio(str(audio_path))
        audio = whisper.pad_or_trim(audio)

        mel = whisper.log_mel_spectrogram(audio).to(self.model.device)
        _, probs = self.model.detect_language(mel)
        lang = max(probs, key=probs.get)

        return {
            "language": lang,
            "language_name": self.LANGUAGE_MAP.get(lang, lang),
            "probability": round(probs[lang], 4),
        }

    def _ensure_model_loaded(self):
        if self.model is None:
            self.load_model()

    def get_available_models(self) -> list:
        """获取可用的模型列表"""
        return [
            {
                "size": size,
                "description": self._get_model_description(size),
                "vram": self._get_model_vram(size),
                "relative_speed": self._get_model_speed(size),
            }
            for size in self.MODEL_SIZES
        ]

    def _get_model_description(self, size: str) -> str:
        descriptions = {
            "tiny": "最小模型，适合快速测试",
            "base": "基础模型，平衡速度与准确率",
            "small": "小型模型，适合资源受限环境",
            "medium": "中型模型，较高准确率（推荐）",
            "large": "大型模型，高准确率",
            "large-v2": "大型v2模型，优化中文识别",
            "large-v3": "大型v3模型，最新架构",
        }
        return descriptions.get(size, "")

    def _get_model_vram(self, size: str) -> str:
        vram = {
            "tiny": "~1 GB", "base": "~1 GB", "small": "~2 GB",
            "medium": "~5 GB", "large": "~10 GB",
            "large-v2": "~10 GB", "large-v3": "~10 GB",
        }
        return vram.get(size, "")

    def _get_model_speed(self, size: str) -> str:
        speeds = {
            "tiny": "10x", "base": "7x", "small": "4x",
            "medium": "2x", "large": "1x",
            "large-v2": "1x", "large-v3": "1x",
        }
        return speeds.get(size, "")


asr_engine = ASREngine()
