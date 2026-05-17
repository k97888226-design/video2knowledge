import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.downloader import VideoDownloader


class TestVideoDownloader:
    @pytest.fixture
    def downloader(self):
        return VideoDownloader()

    def test_detect_platform_bilibili_bv(self, downloader):
        platform = downloader.detect_platform(
            "https://www.bilibili.com/video/BV1xx411c7mD"
        )
        assert platform == "bilibili"

    def test_detect_platform_bilibili_b23(self, downloader):
        platform = downloader.detect_platform("https://b23.tv/abc123")
        assert platform == "bilibili"

    def test_detect_platform_youtube(self, downloader):
        platform = downloader.detect_platform(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert platform == "youtube"

    def test_detect_platform_youtube_short(self, downloader):
        platform = downloader.detect_platform("https://youtu.be/dQw4w9WgXcQ")
        assert platform == "youtube"

    def test_detect_platform_generic(self, downloader):
        platform = downloader.detect_platform("https://example.com/video.mp4")
        assert platform == "generic"

    def test_extract_video_id_bilibili_bv(self, downloader):
        video_id = downloader.extract_video_id(
            "https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"
        )
        assert video_id == "BV1xx411c7mD"

    def test_extract_video_id_bilibili_av(self, downloader):
        video_id = downloader.extract_video_id(
            "https://www.bilibili.com/video/av170001", "bilibili"
        )
        assert video_id == "av170001"

    def test_extract_video_id_bilibili_b23(self, downloader):
        video_id = downloader.extract_video_id(
            "https://b23.tv/abcDEF", "bilibili"
        )
        assert video_id == "abcDEF"

    def test_extract_video_id_youtube(self, downloader):
        video_id = downloader.extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"
        )
        assert video_id == "dQw4w9WgXcQ"

    def test_extract_video_id_youtube_short(self, downloader):
        video_id = downloader.extract_video_id(
            "https://youtu.be/dQw4w9WgXcQ", "youtube"
        )
        assert video_id == "dQw4w9WgXcQ"

    def test_extract_video_id_generic_no_id(self, downloader):
        video_id = downloader.extract_video_id(
            "https://example.com/video", "generic"
        )
        assert video_id is None

    def test_separate_audio_video_requires_ffmpeg(self, downloader):
        video_path = downloader.download_dir / f"{uuid.uuid4().hex}.mp4"

        with patch.object(downloader, "_find_ffmpeg", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                downloader.separate_audio_video(str(video_path))

    def test_get_video_info_mock(self, downloader):
        with patch.object(downloader, "get_video_info") as mock_info:
            mock_info.return_value = {
                "id": "test123",
                "title": "测试视频",
                "description": "测试描述",
                "duration": 600,
                "uploader": "测试用户",
                "upload_date": "20240101",
                "thumbnail": "https://example.com/thumb.jpg",
                "subtitles": ["zh-Hans"],
                "automatic_captions": [],
                "platform": "bilibili",
                "video_id": "BVtest123",
            }

            info = downloader.get_video_info("https://test.com")
            assert info["title"] == "测试视频"
            assert info["duration"] == 600
            assert info["platform"] == "bilibili"

    def test_cleanup_downloads(self, downloader):
        downloader.cleanup_downloads(older_than_hours=0)
