import tempfile
from pathlib import Path

import pytest

from app.core.text_cleaner import TextCleaner


class TestTextCleaner:
    @pytest.fixture
    def cleaner(self):
        return TextCleaner()

    def test_clean_removes_fillers_zh(self, cleaner):
        text = "那个 就是 嗯 然后 我们来看看这个问题 啊 对吧"
        result = cleaner.clean(text, language="zh")

        assert "那个" not in result
        assert "嗯" not in result
        assert "啊" not in result
        assert "这个问题" in result

    def test_clean_removes_fillers_en(self, cleaner):
        text = "um so basically you know this is the main point uh you see"
        result = cleaner.clean(text, language="en")

        assert "um" not in result.lower()
        assert "uh" not in result.lower()

    def test_clean_empty_text(self, cleaner):
        result = cleaner.clean("")
        assert result == ""

    def test_normalize_punctuation_zh(self, cleaner):
        text = "你好！这是测试，看看效果。真的吗？"
        result = cleaner.clean(text, language="zh")

        assert "！" not in result
        assert "？" not in result
        assert "。" not in result

    def test_normalize_punctuation_en(self, cleaner):
        text = "Hello!! How are you??? Good..."
        result = cleaner.clean(text, language="en")
        assert "!!" not in result
        assert "???" not in result

    def test_segment_paragraphs_semantic(self, cleaner):
        text = "今天我们讲机器学习。首先介绍监督学习。然后介绍无监督学习。总的来说这些都很重要。"

        paragraphs = cleaner.segment_paragraphs(text, language="zh", method="semantic")

        assert len(paragraphs) >= 1
        for p in paragraphs:
            assert isinstance(p, str)
            assert len(p) > 0

    def test_segment_paragraphs_length(self, cleaner):
        text = "第一段。" * 50
        paragraphs = cleaner.segment_paragraphs(
            text, language="zh", method="length", max_paragraph_length=100
        )

        assert len(paragraphs) >= 1

    def test_segment_paragraphs_boundary(self, cleaner):
        text = "首先介绍背景知识。其次讨论核心算法。但是需要注意一些问题。"

        paragraphs = cleaner.segment_paragraphs(text, language="zh", method="boundary")

        assert len(paragraphs) >= 1

    def test_extract_key_sentences(self, cleaner):
        text = "Python是一门编程语言。它在AI领域很流行。Python语法简洁。它的库生态丰富。AI是最热门的方向。"

        result = cleaner.extract_key_sentences(text, language="zh", top_k=3)

        assert len(result) <= 3
        for r in result:
            assert "sentence" in r
            assert "score" in r
            assert "index" in r

    def test_get_statistics(self, cleaner):
        text = "这是一个测试文本。用来验证统计功能。"

        stats = cleaner.get_statistics(text, language="zh")

        assert "total_sentences" in stats
        assert "total_words" in stats
        assert "total_characters" in stats
        assert stats["total_sentences"] >= 1
        assert stats["language"] == "zh"

    def test_remove_duplicate_sentences(self, cleaner):
        text = "这是第一句。这是第一句。这是第二句。"

        result = cleaner.clean(text, language="zh", remove_duplicates=True)

        occurrences = result.count("这是第一句")
        assert occurrences == 1
