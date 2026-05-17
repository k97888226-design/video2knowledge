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

        self._attach_learning_outputs(result, [])
        for fmt in export_formats:
            if fmt == "markdown":
                result["exports"][fmt] = self._export_result_markdown(result)
            elif fmt == "json":
                result["exports"][fmt] = self._export_result_json(result)
            else:
                result["exports"][fmt] = self._export(root, fmt)

        return result

    def build_from_segments(
        self,
        segments: list[dict],
        language: str = "zh",
        include_timestamps: bool = True,
        export_formats: Optional[list[str]] = None,
    ) -> dict:
        """从带时间戳的片段构建知识框架"""
        full_text = " ".join(seg.get("text", "") for seg in segments)
        export_formats = export_formats or ["markdown", "markmap", "json"]

        result = self.build(full_text, language, export_formats=export_formats)

        if include_timestamps:
            self._add_timestamps_to_tree(
                result["knowledge_tree"],
                segments,
            )

        self._attach_learning_outputs(result, segments)
        self._refresh_learning_exports(result, export_formats)
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

    def _attach_learning_outputs(
        self,
        result: dict,
        segments: list[dict],
    ) -> None:
        """Build interview questions and flashcards from the knowledge tree."""
        nodes = self._flatten_tree(result.get("knowledge_tree", {}))
        usable_nodes = [
            node for node in nodes
            if node.get("title") and node.get("content")
        ]

        if not usable_nodes and result.get("summary"):
            usable_nodes = [{
                "title": result.get("title", "核心内容"),
                "content": result.get("summary", ""),
                "keywords": result.get("keywords", []),
            }]

        interview_questions = []
        flashcards = []

        for node in usable_nodes[:8]:
            evidence = self._evidence_for_node(node, segments)
            timestamp = self._timestamp_for_node(node)
            title = node.get("title", "").strip()
            content = node.get("content", "").strip()
            keywords = node.get("keywords", [])[:3]

            interview_questions.append({
                "question": f"请解释“{title}”的核心含义。",
                "answer": content,
                "evidence": evidence,
                "timestamp": timestamp,
                "keywords": keywords,
            })

        for node in usable_nodes[:12]:
            evidence = self._evidence_for_node(node, segments)
            timestamp = self._timestamp_for_node(node)
            flashcards.append({
                "front": node.get("title", "").strip(),
                "back": node.get("content", "").strip(),
                "evidence": evidence,
                "timestamp": timestamp,
                "tags": node.get("keywords", [])[:3],
            })

        result["interview_questions"] = interview_questions
        result["flashcards"] = flashcards

    def _flatten_tree(self, node: dict) -> list[dict]:
        if not node:
            return []

        items = [node]
        for child in node.get("children", []) or []:
            items.extend(self._flatten_tree(child))
        return items

    def _timestamp_for_node(self, node: dict) -> Optional[dict]:
        if "timestamp_start" not in node:
            return None

        start = float(node.get("timestamp_start", 0) or 0)
        end = float(node.get("timestamp_end", start) or start)
        return {
            "start": round(start, 3),
            "end": round(end, 3),
            "label": f"{self._format_time(start)} - {self._format_time(end)}",
        }

    def _evidence_for_node(self, node: dict, segments: list[dict]) -> str:
        timestamp = self._timestamp_for_node(node)
        if not timestamp:
            return node.get("content", "")

        start = timestamp["start"]
        end = timestamp["end"]
        nearby = [
            seg.get("text", "").strip()
            for seg in segments
            if seg.get("text")
            and float(seg.get("start", 0) or 0) <= end + 1
            and float(seg.get("end", 0) or 0) >= max(0, start - 1)
        ]
        return " ".join(nearby[:3]) or node.get("content", "")

    def _refresh_learning_exports(
        self,
        result: dict,
        export_formats: list[str],
    ) -> None:
        if "markdown" in export_formats:
            result["exports"]["markdown"] = self._export_result_markdown(result)
        if "json" in export_formats:
            result["exports"]["json"] = self._export_result_json(result)

    def _export_result_json(self, result: dict) -> str:
        payload = {key: value for key, value in result.items() if key != "exports"}
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _export_result_markdown(self, result: dict) -> str:
        lines = [f"# {result.get('title', '学习笔记')}", ""]

        if result.get("summary"):
            lines.extend(["## 摘要", "", result["summary"], ""])

        if result.get("keywords"):
            keywords = " | ".join(f"`{kw}`" for kw in result["keywords"][:10])
            lines.extend([f"> 关键词: {keywords}", ""])

        lines.extend(["## 时间戳知识树", ""])
        lines.extend(self._render_tree_markdown(result.get("knowledge_tree", {})))
        lines.append("")

        lines.extend(["## 面试问答", ""])
        for i, item in enumerate(result.get("interview_questions", []), 1):
            lines.append(f"### Q{i}. {item.get('question', '')}")
            if item.get("timestamp"):
                lines.append(f"- 时间戳: {item['timestamp']['label']}")
            lines.append(f"- 回答: {item.get('answer', '')}")
            if item.get("evidence"):
                lines.append(f"- 原文依据: {item['evidence']}")
            lines.append("")

        lines.extend(["## 复习卡片", ""])
        for i, card in enumerate(result.get("flashcards", []), 1):
            lines.append(f"### Card {i}: {card.get('front', '')}")
            if card.get("timestamp"):
                lines.append(f"- 时间戳: {card['timestamp']['label']}")
            lines.append(f"- 答案: {card.get('back', '')}")
            if card.get("evidence"):
                lines.append(f"- 原文依据: {card['evidence']}")
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def _render_tree_markdown(self, node: dict, depth: int = 0) -> list[str]:
        if not node:
            return []

        indent = "  " * depth
        timestamp = self._timestamp_for_node(node)
        time_text = f" [{timestamp['label']}]" if timestamp else ""
        lines = [f"{indent}- {node.get('title', '')}{time_text}"]
        if node.get("content"):
            lines.append(f"{indent}  {node['content']}")

        for child in node.get("children", []) or []:
            lines.extend(self._render_tree_markdown(child, depth + 1))

        return lines

    @staticmethod
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

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
