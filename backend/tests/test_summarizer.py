import pytest
from unittest.mock import patch, MagicMock

from app.core.summarizer import Summarizer, SummaryPoint


class TestSummarizer:
    @pytest.fixture
    def summarizer(self):
        return Summarizer()

    def test_extractive_summarize_zh(self, summarizer):
        text = (
            "机器学习是人工智能的重要分支。它通过数据训练模型来实现智能决策。"
            "深度学习是机器学习中的热门技术。它使用多层神经网络进行特征提取。"
            "自然语言处理是AI的另一个重要方向。它让计算机理解人类语言。"
            "这些技术都有着广泛的应用。从图像识别到语音合成。"
        )

        result = summarizer._extractive_summarize(text, language="zh", top_k=3)

        assert "summary" in result
        assert "key_points" in result
        assert "keywords" in result
        assert len(result["key_points"]) <= 3
        assert len(result["summary"]) > 0
        assert len(result["keywords"]) > 0

    def test_extractive_summarize_en(self, summarizer):
        text = (
            "Artificial intelligence is transforming the world. "
            "Machine learning algorithms learn from data. "
            "Deep learning uses neural networks for complex tasks. "
            "These technologies have many practical applications."
        )

        result = summarizer._extractive_summarize(text, language="en", top_k=2)

        assert "summary" in result
        assert len(result["key_points"]) <= 2
        assert len(result["keywords"]) > 0

    def test_extractive_summarize_empty(self, summarizer):
        result = summarizer.summarize("", language="zh")
        assert result["summary"] == ""

    def test_extract_keywords(self, summarizer):
        text = "人工智能和机器学习是计算机科学的重要研究方向"
        keywords = summarizer._extract_keywords(text, top_k=5)

        assert len(keywords) > 0
        for kw in keywords:
            assert isinstance(kw, str)

    def test_extract_main_topic(self, summarizer):
        paragraphs = [
            "今天我们来学习Python编程语言的基础知识。",
            "Python是一种解释型语言。",
        ]

        topic = summarizer._extract_main_topic(paragraphs, language="zh")
        assert "Python" in topic

    def test_extract_sub_topic(self, summarizer):
        paragraph = "深度学习是机器学习的一个子领域，主要使用神经网络进行学习。"
        sub_topic = summarizer._extract_sub_topic(paragraph, language="zh")

        assert len(sub_topic) > 0

    def test_generate_hierarchical_summary(self, summarizer):
        paragraphs = [
            "人工智能是计算机科学的一个分支。它研究如何让机器像人一样思考。",
            "机器学习是AI的核心技术。通过数据驱动的方式学习规律。",
            "深度学习使用多层神经网络。在图像识别领域表现优异。",
        ]

        root = summarizer.generate_hierarchical_summary(paragraphs, language="zh")

        assert root.title != ""
        assert len(root.keywords) > 0
        assert root.importance == 1.0
        assert len(root.children) > 0

    def test_summary_point_dataclass(self):
        child1 = SummaryPoint(
            title="子点1",
            content="内容1",
            importance=0.8,
            keywords=["a", "b"],
        )
        child2 = SummaryPoint(
            title="子点2",
            content="内容2",
            importance=0.6,
            keywords=["c"],
        )
        root = SummaryPoint(
            title="主点",
            content="主要内容",
            importance=1.0,
            children=[child1, child2],
            keywords=["x", "y"],
            timestamp=(0.0, 10.0),
        )

        assert len(root.children) == 2
        assert root.title == "主点"
        assert root.timestamp == (0.0, 10.0)

    def test_export_markdown(self, summarizer):
        root = SummaryPoint(
            title="测试标题",
            content="测试内容",
            importance=1.0,
            keywords=["测试"],
            children=[
                SummaryPoint(
                    title="子标题",
                    content="子内容",
                    importance=0.8,
                    keywords=["子"],
                    children=[
                        SummaryPoint("细节", "细节内容", 0.5)
                    ]
                )
            ]
        )

        md = summarizer.export_markdown(root)
        assert "# 测试标题" in md
        assert "子标题" in md
        assert "细节" in md

    def test_export_markmap(self, summarizer):
        root = SummaryPoint(
            title="主题",
            content="内容",
            importance=1.0,
            keywords=["kw"],
            children=[SummaryPoint("子", "子内容", 0.5)],
        )

        mm = summarizer._export_markmap(root)
        assert "markmap" in mm
        assert "主题" in mm
        assert "子" in mm

    def test_export_mermaid(self, summarizer):
        root = SummaryPoint(
            title="主题",
            content="内容",
            importance=1.0,
            children=[SummaryPoint("子", "子内容", 0.5)],
        )

        md = summarizer._export_mermaid(root)
        assert "mindmap" in md
        assert "主题" in md

    def test_export_opml(self, summarizer):
        root = SummaryPoint(
            title="主题",
            content="内容",
            importance=1.0,
            children=[SummaryPoint("子", "子内容", 0.5)],
        )

        opml = summarizer._export_opml(root)
        assert '<?xml' in opml
        assert 'opml' in opml
        assert '主题' in opml

    @patch("app.core.summarizer.Summarizer.load_models")
    def test_summarize_hybrid_method(self, mock_load, summarizer):
        text = "这是一个测试文本。用于验证混合摘要方法。它包含了一些关键词。"
        result = summarizer.summarize(text, language="zh", method="hybrid")

        assert "summary" in result
        assert len(result["summary"]) > 0

    def test_format_time(self, summarizer):
        assert summarizer._format_time(0) == "00:00:00"
        assert summarizer._format_time(65) == "00:01:05"
        assert summarizer._format_time(3661) == "01:01:01"
