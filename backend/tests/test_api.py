import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import task_store


class MockSummarizer:
    def summarize(self, text, language="zh", max_length=150, min_length=40, method="hybrid"):
        return {
            "summary": "测试摘要内容",
            "key_points": ["要点1", "要点2", "要点3"],
            "keywords": ["测试", "摘要", "关键词"],
            "method": method,
        }

    def generate_hierarchical_summary(self, paragraphs, language="zh"):
        from app.core.summarizer import SummaryPoint
        root = SummaryPoint(
            title="测试主题",
            content="测试内容",
            importance=1.0,
            keywords=["测试"],
        )
        child = SummaryPoint(
            title="子主题1",
            content="子内容",
            importance=0.8,
            keywords=["子测试"],
        )
        root.children.append(child)
        return root


class TestAPIRoutes:
    @pytest.fixture
    def client(self):
        task_store.clear()
        return TestClient(app)

    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "asr_models_available" in data

    def test_root_endpoint(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/ui/"

    def test_get_video_info_bad_url(self, client):
        response = client.post(
            "/api/v1/video/info?url=not-a-valid-url"
        )
        assert response.status_code in [400, 422]

    @patch("app.api.routes._process_video_pipeline")
    def test_process_video_creates_task(self, mock_pipeline, client):
        mock_pipeline.return_value = None

        response = client.post(
            "/api/v1/video/process",
            json={
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "language": "zh",
                "use_asr": True,
                "asr_model_size": "medium",
                "summarization_method": "hybrid",
                "export_formats": ["markdown", "json"],
                "generate_mindmap": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_process_video_invalid_request(self, client):
        response = client.post(
            "/api/v1/video/process",
            json={},
        )
        assert response.status_code == 422

    @patch("app.api.routes._process_upload_pipeline")
    def test_process_upload_subtitle_file(self, mock_pipeline, client):
        mock_pipeline.return_value = None

        response = client.post(
            "/api/v1/upload/process",
            data={
                "language": "zh",
                "asr_model_size": "tiny",
                "export_formats": "markdown,json",
            },
            files={
                "file": (
                    "sample.srt",
                    b"1\n00:00:01,000 --> 00:00:03,500\nsample subtitle\n",
                    "application/x-subrip",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    @patch("app.api.routes._process_upload_pipeline")
    def test_process_upload_rejects_unknown_file_type(self, mock_pipeline, client):
        response = client.post(
            "/api/v1/upload/process",
            data={"language": "zh"},
            files={
                "file": (
                    "sample.txt",
                    b"plain text",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 400
        mock_pipeline.assert_not_called()

    @patch("app.api.routes._process_upload_pipeline")
    def test_process_upload_video_requires_subtitle(self, mock_pipeline, client):
        response = client.post(
            "/api/v1/upload/process",
            data={"language": "zh"},
            files={
                "file": (
                    "sample.mp4",
                    b"not a real video",
                    "video/mp4",
                )
            },
        )

        assert response.status_code == 400
        assert "字幕" in response.json()["detail"]
        mock_pipeline.assert_not_called()

    @patch("app.api.routes._process_upload_pipeline")
    def test_process_upload_video_with_subtitle_file(self, mock_pipeline, client):
        mock_pipeline.return_value = None

        response = client.post(
            "/api/v1/upload/process",
            data={
                "language": "zh",
                "export_formats": "markdown,json",
            },
            files={
                "file": ("sample.mp4", b"not a real video", "video/mp4"),
                "subtitle_file": (
                    "sample.srt",
                    b"1\n00:00:01,000 --> 00:00:03,500\nsample subtitle\n",
                    "application/x-subrip",
                ),
            },
        )

        assert response.status_code == 200
        assert "task_id" in response.json()

    @patch("app.api.routes._process_subtitle_pipeline")
    def test_process_subtitle(self, mock_pipeline, client):
        mock_pipeline.return_value = None

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write("1\n00:00:01,000 --> 00:00:03,500\n测试字幕\n")
            tmp_path = f.name

        try:
            response = client.post(
                "/api/v1/subtitle/process",
                json={
                    "file_path": tmp_path,
                    "language": "zh",
                    "export_formats": ["markdown"],
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("app.api.routes._process_audio_pipeline")
    def test_process_audio(self, mock_pipeline, client):
        mock_pipeline.return_value = None

        response = client.post(
            "/api/v1/audio/process",
            json={
                "file_path": "/nonexistent/test.wav",
                "language": "auto",
                "asr_model_size": "tiny",
                "enable_word_timestamps": False,
                "export_formats": ["markdown"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_get_task_not_found(self, client):
        response = client.get("/api/v1/task/nonexistent-id")
        assert response.status_code == 404

    def test_get_task_status(self, client):
        task_id = "test-task-id"
        task_store[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "message": "测试任务",
            "result": None,
            "error": None,
        }

        response = client.get(f"/api/v1/task/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "pending"

    def test_list_tasks(self, client):
        task_store.clear()
        for i in range(3):
            task_store[f"test-{i}"] = {
                "task_id": f"test-{i}",
                "status": "completed",
                "progress": 100.0,
                "message": f"完成 {i}",
                "result": None,
                "error": None,
            }

        response = client.get("/api/v1/tasks?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    def test_export_nonexistent_task(self, client):
        response = client.get("/api/v1/task/nonexistent/export/markdown")
        assert response.status_code == 404

    def test_export_uncompleted_task(self, client):
        task_id = "pending-task"
        task_store[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "message": "",
            "result": None,
            "error": None,
        }

        response = client.get(f"/api/v1/task/{task_id}/export/markdown")
        assert response.status_code == 400

    @patch("app.api.routes._process_video_pipeline")
    def test_batch_process(self, mock_pipeline, client):
        mock_pipeline.return_value = None

        response = client.post(
            "/api/v1/batch/process",
            json={
                "urls": [
                    "https://www.bilibili.com/video/BV1xx411c7mD",
                    "https://www.bilibili.com/video/BV1GJ411x7h7",
                ],
                "language": "auto",
                "asr_model_size": "medium",
                "export_formats": ["markdown", "json"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "batch_id" in data
        assert "task_ids" in data
        assert data["total"] == 2

    def test_batch_empty_urls(self, client):
        response = client.post(
            "/api/v1/batch/process",
            json={
                "urls": [],
                "language": "auto",
                "export_formats": ["markdown"],
            },
        )
        assert response.status_code == 422

    def test_api_docs_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client):
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "/api/v1/health" in schema["paths"]
        assert "/api/v1/video/process" in schema["paths"]
        assert "/api/v1/upload/process" in schema["paths"]
        assert "/api/v1/batch/process" in schema["paths"]
