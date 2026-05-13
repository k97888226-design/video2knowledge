import tempfile
from pathlib import Path

import pytest

from app.core.subtitle_parser import SubtitleParser, SubtitleEntry


class TestSubtitleParser:
    @pytest.fixture
    def parser(self):
        return SubtitleParser()

    @pytest.fixture
    def srt_content(self):
        return """1
00:00:01,000 --> 00:00:03,500
这是第一句字幕

2
00:00:04,000 --> 00:00:07,200
这是第二句字幕

3
00:00:08,000 --> 00:00:12,000
这是第三句字幕
"""

    @pytest.fixture
    def ass_content(self):
        return """[Script Info]
Title: Test

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,这是第一行ASS字幕
Dialogue: 0,0:00:04.00,0:00:06.50,Default,,0,0,0,,{\\i1}这是第二行\\N带格式的字幕
"""

    @pytest.fixture
    def vtt_content(self):
        return """WEBVTT

00:00:01.000 --> 00:00:03.500
第一句VTT字幕

00:00:04.000 --> 00:00:07.200
第二句VTT字幕

00:00:08.000 --> 00:00:12.000
第三句<c.vtt>VTT字幕</c>
"""

    def test_parse_srt(self, parser, srt_content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write(srt_content)
            tmp_path = f.name

        try:
            entries = parser.parse(tmp_path)
            assert len(entries) == 3
            assert entries[0].text == "这是第一句字幕"
            assert entries[0].start == 1.0
            assert entries[0].end == 3.5
            assert entries[1].text == "这是第二句字幕"
            assert entries[2].text == "这是第三句字幕"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_ass(self, parser, ass_content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ass", delete=False, encoding="utf-8-sig"
        ) as f:
            f.write(ass_content)
            tmp_path = f.name

        try:
            entries = parser.parse(tmp_path)
            assert len(entries) >= 1
            assert "ASS字幕" in entries[0].text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_vtt(self, parser, vtt_content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".vtt", delete=False, encoding="utf-8"
        ) as f:
            f.write(vtt_content)
            tmp_path = f.name

        try:
            entries = parser.parse(tmp_path)
            assert len(entries) >= 1
            assert "VTT" in entries[0].text or "VTT" in entries[-1].text

            for entry in entries:
                assert entry.text != ""
                assert "WEBVTT" not in entry.text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_get_full_text(self, parser, srt_content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write(srt_content)
            tmp_path = f.name

        try:
            entries = parser.parse(tmp_path)
            full_text = parser.get_full_text(entries)
            assert "第一句字幕" in full_text
            assert "第二句字幕" in full_text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_get_text_with_timestamps(self, parser, srt_content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write(srt_content)
            tmp_path = f.name

        try:
            entries = parser.parse(tmp_path)
            text = parser.get_text_with_timestamps(entries)
            assert "00:00:01" in text
            assert "字幕" in text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_export_srt(self, parser, srt_content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write(srt_content)
            tmp_path = f.name

        try:
            entries = parser.parse(tmp_path)
            export_path = tmp_path.replace(".srt", "_export.srt")
            parser.export_srt(entries, export_path)

            exported_entries = parser.parse(export_path)
            assert len(exported_entries) == len(entries)
            assert exported_entries[0].text == entries[0].text

            Path(export_path).unlink(missing_ok=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_nonexistent_file(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("nonexistent.srt")

    def test_parse_unsupported_format(self, parser):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("test")
            tmp_path = f.name

        try:
            with pytest.raises(ValueError):
                parser.parse(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_subtitle_entry_properties(self):
        entry = SubtitleEntry(
            index=0,
            start=1.5,
            end=3.5,
            text="测试文本",
        )

        assert entry.duration == 2.0
        assert entry.index == 0
        assert entry.text == "测试文本"

    def test_merge_subtitles(self, parser):
        primary = [
            SubtitleEntry(0, 0.0, 2.0, "Hello"),
            SubtitleEntry(1, 2.5, 5.0, "World"),
        ]
        secondary = [
            SubtitleEntry(0, 0.1, 1.9, "你好"),
            SubtitleEntry(1, 2.6, 4.9, "世界"),
        ]

        merged = parser.merge_subtitles(primary, secondary)
        assert len(merged) == 2
        assert "Hello" in merged[0].text
        assert "World" in merged[1].text

    def test_align_segments_with_subtitles(self, parser):
        asr_segments = [
            {"start": 0.0, "end": 2.0, "text": "Hello world"},
            {"start": 2.5, "end": 5.0, "text": "Nice to meet"},
        ]
        subtitle_entries = [
            SubtitleEntry(0, 0.1, 1.9, "Hello world"),
            SubtitleEntry(1, 2.6, 4.8, "Nice to meet you"),
        ]

        aligned = parser.align_segments_with_subtitles(asr_segments, subtitle_entries)
        assert len(aligned) == 2
        assert "alignment_score" in aligned[0]
