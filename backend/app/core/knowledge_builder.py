import json
from typing import Optional

from loguru import logger

from .summarizer import Summarizer, SummaryPoint
from .text_cleaner import TextCleaner


class KnowledgeBuilder:
    """知识框架构建器 - 将文本内容结构化为层次化知识图谱"""

    def __init__(self):
        self.summarizer = Summarizer()
        self.text_cleaner = TextCleaner()

    def build(
        self,
        text: str,
        language: str = "zh",
        max_depth: int = 3,
        export_formats: Optional[list[str]] = None,
    ) -> dict:
        """从文本构建知识框架"""
        if not text:
            return {"error": "文本为空"}

        export_formats = export_formats or ["markdown", "markmap", "json"]

        cleaned_text = self.text_cleaner.clean(text, language)

        paragraphs = self.text_cleaner.segment_paragraphs(
            cleaned_text, language, method="semantic"
        )

        stats = self.text_cleaner.get_statistics(cleaned_text, language)

        root = self.summarizer.generate_hierarchical_summary(
            paragraphs, language
        )

        summary = self.summarizer.summarize(cleaned_text, language, method="hybrid")

        result = {
            "title": root.title,
            "statistics": stats,
            "summary": summary.get("summary", ""),
            "keywords": root.keywords,
            "knowledge_tree": self._serialize_tree(root, max_depth),
            "key_points": summary.get("key_points", []),
            "exports": {},
        }

        for fmt in export_formats:
            result["exports"][fmt] = self._export(root, fmt)

        return result

    def build_from_segments(
        self,
        segments: list[dict],
        language: str = "zh",
        include_timestamps: bool = True,
    ) -> dict:
        """从带时间戳的片段构建知识框架"""
        full_text = " ".join(seg.get("text", "") for seg in segments)

        result = self.build(full_text, language)

        if include_timestamps:
            self._add_timestamps_to_tree(
                result["knowledge_tree"],
                segments,
            )

        return result

    def merge_multiple_sources(
        self,
        sources: list[dict],
        language: str = "zh",
    ) -> dict:
        """合并多个来源构建综合知识框架"""
        all_text = ""
        source_metadata = []

        for source in sources:
            source_text = source.get("text", "")
            all_text += source_text + "\n\n"
            source_metadata.append({
                "title": source.get("title", "未知"),
                "url": source.get("url", ""),
                "platform": source.get("platform", ""),
                "duration": source.get("duration", 0),
            })

        result = self.build(all_text, language)
        result["sources"] = source_metadata
        result["source_count"] = len(source_metadata)

        return result

    def _serialize_tree(
        self,
        node: SummaryPoint,
        max_depth: int,
        current_depth: int = 0,
    ) -> dict:
        """序列化知识树"""
        serialized = {
            "title": node.title,
            "content": node.content[:300] if node.content else "",
            "importance": round(node.importance, 4),
            "keywords": node.keywords,
        }

        if node.timestamp:
            serialized["timestamp_start"] = round(node.timestamp[0], 2)
            serialized["timestamp_end"] = round(node.timestamp[1], 2)

        if current_depth < max_depth and node.children:
            serialized["children"] = [
                self._serialize_tree(child, max_depth, current_depth + 1)
                for child in node.children
            ]

        return serialized

    def _add_timestamps_to_tree(
        self,
        node: dict,
        segments: list[dict],
    ) -> None:
        """为知识树节点添加时间戳"""
        if "children" in node:
            for child in node["children"]:
                self._add_timestamps_to_tree(child, segments)

        keywords = set(node.get("keywords", []))
        for seg in segments:
            seg_text = seg.get("text", "")
            if any(kw in seg_text for kw in keywords):
                node["timestamp_start"] = seg.get("start", 0)
                node["timestamp_end"] = seg.get("end", 0)
                break

    def _export(self, root: SummaryPoint, format: str) -> str:
        """导出为指定格式"""
        if format == "markdown":
            return self.summarizer.export_markdown(root)
        elif format == "markmap":
            return self.summarizer.export_mindmap(root, "markmap")
        elif format == "mermaid":
            return self.summarizer.export_mindmap(root, "mermaid")
        elif format == "opml":
            return self.summarizer.export_mindmap(root, "opml")
        elif format == "json":
            return json.dumps(
                self._serialize_tree(root, max_depth=10),
                ensure_ascii=False,
                indent=2,
            )
        else:
            raise ValueError(f"不支持的导出格式: {format}")

    def export_file(
        self,
        result: dict,
        output_path: str,
        format: str = "markdown",
    ) -> None:
        """导出到文件"""
        content = result.get("exports", {}).get(format, "")
        if not content:
            content = self._export(
                SummaryPoint(
                    title=result.get("title", ""),
                    content=result.get("summary", ""),
                    importance=1.0,
                    keywords=result.get("keywords", []),
                ),
                format,
            )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"已导出到: {output_path}")


knowledge_builder = KnowledgeBuilder()
