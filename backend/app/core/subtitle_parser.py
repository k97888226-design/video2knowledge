import re
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import timedelta

import pysrt
from loguru import logger


@dataclass
class SubtitleEntry:
    """字幕条目数据结构"""
    index: int
    start: float
    end: float
    text: str
    style: Optional[str] = None
    speaker: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    @property
    def start_timedelta(self) -> timedelta:
        return timedelta(seconds=self.start)

    @property
    def end_timedelta(self) -> timedelta:
        return timedelta(seconds=self.end)


class SubtitleParser:
    """字幕文件解析器 - 支持SRT, ASS/SSA, VTT, JSON格式"""

    SUPPORTED_FORMATS = {".srt", ".ass", ".ssa", ".vtt", ".sbv", ".json"}

    def parse(self, file_path: str) -> list[SubtitleEntry]:
        """解析字幕文件，自动识别格式"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"字幕文件不存在: {file_path}")

        suffix = file_path.suffix.lower()

        if suffix == ".srt":
            return self.parse_srt(file_path)
        elif suffix in (".ass", ".ssa"):
            return self.parse_ass(file_path)
        elif suffix == ".vtt":
            return self.parse_vtt(file_path)
        elif suffix == ".json":
            return self.parse_json(file_path)
        else:
            raise ValueError(f"不支持的字幕格式: {suffix}")

    def parse_srt(self, file_path: Path) -> list[SubtitleEntry]:
        """解析SRT字幕文件"""
        subs = pysrt.open(str(file_path))
        entries = []

        for sub in subs:
            start_seconds = self._time_to_seconds(
                sub.start.hours, sub.start.minutes,
                sub.start.seconds, sub.start.milliseconds
            )
            end_seconds = self._time_to_seconds(
                sub.end.hours, sub.end.minutes,
                sub.end.seconds, sub.end.milliseconds
            )

            text = sub.text.replace("\n", " ").strip()
            text = re.sub(r"<[^>]+>", "", text)

            entries.append(SubtitleEntry(
                index=sub.index,
                start=start_seconds,
                end=end_seconds,
                text=text,
            ))

        return entries

    def parse_ass(self, file_path: Path) -> list[SubtitleEntry]:
        """解析ASS/SSA字幕文件"""
        content = file_path.read_text(encoding="utf-8-sig", errors="ignore")

        events_section = False
        format_fields = []
        entries = []
        index = 0

        ass_tags_pattern = re.compile(r"\{[^}]*\}")

        for line in content.splitlines():
            line = line.strip()

            if line.lower().startswith("[events]"):
                events_section = True
                continue

            if events_section and line.lower().startswith("format:"):
                format_fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
                continue

            if events_section and line.lower().startswith("dialogue:"):
                parts = line.split(":", 1)[1].split(",", len(format_fields) - 1)
                if len(parts) < len(format_fields):
                    continue

                dialogue = {}
                for i, field_name in enumerate(format_fields):
                    if i < len(parts):
                        dialogue[field_name] = parts[i].strip()

                text = dialogue.get("text", "")
                text = ass_tags_pattern.sub("", text)
                text = text.replace("\\N", " ").replace("\\n", " ").strip()
                text = re.sub(r"\\[a-z]+\d*", "", text)

                if not text:
                    continue

                start = self._ass_time_to_seconds(dialogue.get("start", "0:00:00.00"))
                end = self._ass_time_to_seconds(dialogue.get("end", "0:00:00.00"))

                entries.append(SubtitleEntry(
                    index=index,
                    start=start,
                    end=end,
                    text=text,
                    style=dialogue.get("style", "Default"),
                    speaker=dialogue.get("name", None),
                    metadata={
                        "layer": dialogue.get("layer", "0"),
                        "margin_l": dialogue.get("marginl", "0"),
                        "margin_r": dialogue.get("marginr", "0"),
                        "margin_v": dialogue.get("marginv", "0"),
                        "effect": dialogue.get("effect", ""),
                    }
                ))
                index += 1

        return entries

    def parse_vtt(self, file_path: Path) -> list[SubtitleEntry]:
        """解析WebVTT字幕文件"""
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        content = re.sub(r"WEBVTT.*?\n\n", "", content, flags=re.DOTALL)
        content = re.sub(r"NOTE.*?\n\n", "", content, flags=re.DOTALL)

        entries = []
        index = 0
        vtt_tag_pattern = re.compile(r"<[^>]+>")
        vtt_cue_pattern = re.compile(r"<c[^>]*>")

        blocks = re.split(r"\n\n+", content.strip())

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 2:
                continue

            time_line = None
            text_lines = []

            for line in lines:
                if "-->" in line:
                    time_line = line.strip()
                elif not line.strip().isdigit():
                    text_lines.append(line)

            if time_line is None:
                continue

            try:
                parts = time_line.split("-->")
                start = self._vtt_time_to_seconds(parts[0].strip())
                end = self._vtt_time_to_seconds(parts[1].strip())
            except (ValueError, IndexError):
                continue

            text = " ".join(text_lines)
            text = vtt_tag_pattern.sub("", text)
            text = re.sub(r"&[a-z]+;", "", text)
            text = text.strip()

            if not text:
                continue

            entries.append(SubtitleEntry(
                index=index,
                start=start,
                end=end,
                text=text,
            ))
            index += 1

        return entries

    def parse_json(self, file_path: Path) -> list[SubtitleEntry]:
        """解析JSON格式字幕"""
        content = json.loads(file_path.read_text(encoding="utf-8"))

        if isinstance(content, list):
            return self._parse_json_list(content)
        elif isinstance(content, dict):
            return self._parse_json_dict(content)
        else:
            raise ValueError("不支持的JSON字幕格式")

    def _parse_json_list(self, data: list) -> list[SubtitleEntry]:
        entries = []
        for i, item in enumerate(data):
            entries.append(SubtitleEntry(
                index=item.get("index", i),
                start=item.get("start", item.get("from", 0)),
                end=item.get("end", item.get("to", 0)),
                text=item.get("text", item.get("content", "")),
            ))
        return entries

    def _parse_json_dict(self, data: dict) -> list[SubtitleEntry]:
        entries = []
        body = data.get("body", [])

        for i, item in enumerate(body):
            entries.append(SubtitleEntry(
                index=i,
                start=item.get("from", 0),
                end=item.get("to", 0),
                text=item.get("content", ""),
            ))
        return entries

    def merge_subtitles(
        self,
        primary: list[SubtitleEntry],
        secondary: list[SubtitleEntry],
        max_gap: float = 0.5,
    ) -> list[SubtitleEntry]:
        """合并两套字幕（按时间戳对齐）"""
        if not primary or not secondary:
            return primary or secondary

        merged = []
        sec_index = 0

        for pri_entry in primary:
            best_match = None

            while sec_index < len(secondary):
                sec_entry = secondary[sec_index]
                overlap = self._compute_overlap(pri_entry, sec_entry)

                if overlap > 0:
                    if best_match is None or overlap > best_match[1]:
                        best_match = (sec_entry, overlap)
                    sec_index += 1
                elif sec_entry.start > pri_entry.end + max_gap:
                    break
                else:
                    sec_index += 1

            if best_match:
                merged_text = f"{pri_entry.text} {best_match[0].text}"
            else:
                merged_text = pri_entry.text

            merged.append(SubtitleEntry(
                index=pri_entry.index,
                start=pri_entry.start,
                end=pri_entry.end,
                text=merged_text.strip(),
            ))

        return merged

    def align_segments_with_subtitles(
        self,
        asr_segments: list[dict],
        subtitle_entries: list[SubtitleEntry],
        max_offset: float = 2.0,
    ) -> list[dict]:
        """将ASR结果与字幕时间戳对齐"""
        aligned = []

        for seg in asr_segments:
            best_entry = None
            best_score = 0

            for entry in subtitle_entries:
                offset = abs(seg.get("start", 0) - entry.start)

                if offset < max_offset:
                    text_similarity = self._text_similarity(
                        seg.get("text", ""),
                        entry.text,
                    )
                    score = text_similarity / (1 + offset)

                    if score > best_score:
                        best_score = score
                        best_entry = entry

            aligned_seg = dict(seg)
            if best_entry:
                aligned_seg["subtitle_start"] = best_entry.start
                aligned_seg["subtitle_end"] = best_entry.end
                aligned_seg["subtitle_text"] = best_entry.text
                aligned_seg["alignment_score"] = round(best_score, 4)

            aligned.append(aligned_seg)

        return aligned

    def export_srt(self, entries: list[SubtitleEntry], output_path: str) -> None:
        """导出为SRT格式"""
        output_path = Path(output_path)

        lines = []
        for entry in entries:
            lines.append(str(entry.index + 1))
            lines.append(
                f"{self._format_srt_time(entry.start)} --> "
                f"{self._format_srt_time(entry.end)}"
            )
            lines.append(entry.text)
            lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")

    def get_full_text(self, entries: list[SubtitleEntry]) -> str:
        """获取完整文本（合并所有字幕）"""
        return " ".join(entry.text for entry in entries)

    def get_text_with_timestamps(self, entries: list[SubtitleEntry]) -> str:
        """获取带时间戳的文本"""
        lines = []
        for entry in entries:
            time_str = f"[{self._format_time_compact(entry.start)} -> {self._format_time_compact(entry.end)}]"
            lines.append(f"{time_str} {entry.text}")
        return "\n".join(lines)

    def _compute_overlap(self, a: SubtitleEntry, b: SubtitleEntry) -> float:
        """计算两个字幕条目时间重叠度"""
        overlap_start = max(a.start, b.start)
        overlap_end = min(a.end, b.end)
        if overlap_start < overlap_end:
            return overlap_end - overlap_start
        return 0.0

    def _text_similarity(self, a: str, b: str) -> float:
        """简单文本相似度计算"""
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return 0.0
        intersection = a_set & b_set
        union = a_set | b_set
        return len(intersection) / len(union)

    @staticmethod
    def _time_to_seconds(h: int, m: int, s: int, ms: int) -> float:
        return h * 3600 + m * 60 + s + ms / 1000.0

    @staticmethod
    def _ass_time_to_seconds(time_str: str) -> float:
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            s, cs = s.split(".") if "." in s else (s, "00")
            return int(h) * 3600 + int(m) * 60 + int(s) + int(cs.ljust(2, "0")) / 100.0
        return 0.0

    @staticmethod
    def _vtt_time_to_seconds(time_str: str) -> float:
        time_str = time_str.strip()
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s_ms = parts
            s_ms_parts = s_ms.split(".")
            s = int(s_ms_parts[0])
            ms = int(s_ms_parts[1].ljust(3, "0")[:3]) if len(s_ms_parts) > 1 else 0
            return int(h) * 3600 + int(m) * 60 + s + ms / 1000.0
        return 0.0

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_time_compact(seconds: float) -> str:
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


subtitle_parser = SubtitleParser()
