import re
from typing import Optional, Union
from collections import Counter
from dataclasses import dataclass, field

import jieba
import jieba.analyse
from loguru import logger

from ..config import settings
from .text_cleaner import TextCleaner


@dataclass
class SummaryPoint:
    """摘要要点"""
    title: str
    content: str
    importance: float
    children: list["SummaryPoint"] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    timestamp: Optional[tuple[float, float]] = None
    source_index: Optional[int] = None


class Summarizer:
    """基于深度学习的摘要生成系统"""

    def __init__(self):
        self.model = None
        self.model_zh = None
        self.tokenizer = None
        self.tokenizer_zh = None
        self.text_cleaner = TextCleaner()
        self._models_loaded = False

    def load_models(self) -> None:
        """加载摘要模型"""
        if self._models_loaded:
            return

        try:
            from transformers import (
                AutoTokenizer,
                AutoModelForSeq2SeqLM,
                pipeline,
            )

            logger.info("正在加载摘要模型...")

            self.tokenizer = AutoTokenizer.from_pretrained(
                settings.SUMMARIZATION_MODEL
            )
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                settings.SUMMARIZATION_MODEL
            )
            self.summarizer_pipeline = pipeline(
                "summarization",
                model=self.model,
                tokenizer=self.tokenizer,
            )

            try:
                self.tokenizer_zh = AutoTokenizer.from_pretrained(
                    settings.SUMMARIZATION_MODEL_ZH
                )
                self.model_zh = AutoModelForSeq2SeqLM.from_pretrained(
                    settings.SUMMARIZATION_MODEL_ZH
                )
                self.summarizer_pipeline_zh = pipeline(
                    "summarization",
                    model=self.model_zh,
                    tokenizer=self.tokenizer_zh,
                )
            except Exception as e:
                logger.warning(f"中文摘要模型加载失败，使用基础模型: {e}")
                self.model_zh = None

            self._models_loaded = True
            logger.info("摘要模型加载完成")

        except ImportError:
            logger.error("transformers未安装，使用抽取式摘要")
            self._models_loaded = False

    def summarize(
        self,
        text: str,
        language: str = "zh",
        max_length: int = 150,
        min_length: int = 40,
        method: str = "hybrid",
    ) -> dict:
        """生成文本摘要"""
        if not text:
            return {"summary": "", "key_points": [], "keywords": []}

        if method == "extractive":
            return self._extractive_summarize(text, language)
        elif method == "abstractive":
            return self._abstractive_summarize(text, language, max_length, min_length)
        else:
            return self._hybrid_summarize(text, language, max_length, min_length)

    def generate_hierarchical_summary(
        self,
        paragraphs: list[str],
        language: str = "zh",
    ) -> SummaryPoint:
        """生成层级化摘要结构"""
        if not paragraphs:
            return SummaryPoint(title="无内容", content="", importance=0.0)

        topic = self._extract_main_topic(paragraphs, language)
        keywords = self._extract_keywords(" ".join(paragraphs), top_k=10)

        root = SummaryPoint(
            title=topic,
            content=" ".join(paragraphs)[:200] + "...",
            importance=1.0,
            keywords=keywords,
        )

        for i, para in enumerate(paragraphs):
            if len(para.strip()) < 20:
                continue

            sub_topic = self._extract_sub_topic(para, language)
            summary = self._extractive_summarize(para, language)
            para_keywords = self._extract_keywords(para, top_k=3)

            child = SummaryPoint(
                title=sub_topic,
                content=summary.get("summary", para[:100]),
                importance=self._score_importance(para, paragraphs, language),
                keywords=para_keywords,
                source_index=i,
            )

            detail_points = self._extract_detail_points(para, language)
            for dp in detail_points:
                child.children.append(SummaryPoint(
                    title=dp,
                    content=dp,
                    importance=0.5,
                ))

            root.children.append(child)

        return root

    def export_markdown(
        self,
        root: SummaryPoint,
        include_keywords: bool = True,
        include_source: bool = False,
    ) -> str:
        """导出为Markdown格式的思维导图"""
        lines = []
        lines.append(f"# {root.title}")
        lines.append("")

        if include_keywords and root.keywords:
            kw_str = " | ".join(f"`{kw}`" for kw in root.keywords[:8])
            lines.append(f"> **关键词**: {kw_str}")
            lines.append("")

        for i, child in enumerate(root.children, 1):
            prefix = f"## {i}."
            lines.append(f"{prefix} {child.title}")

            if include_keywords and child.keywords:
                kw_str = ", ".join(f"`{kw}`" for kw in child.keywords)
                lines.append(f"   *关键词: {kw_str}*")

            lines.append("")
            lines.append(f"   {child.content}")
            lines.append("")

            if child.children:
                for j, grandchild in enumerate(child.children, 1):
                    lines.append(f"   - **{grandchild.title}**")
                    lines.append(f"     {grandchild.content}")
                    lines.append("")

            if include_source and child.timestamp:
                start, end = child.timestamp
                lines.append(
                    f"   *时间戳: {self._format_time(start)} - "
                    f"{self._format_time(end)}*"
                )
                lines.append("")

        return "\n".join(lines)

    def export_mindmap(
        self,
        root: SummaryPoint,
        format: str = "markmap",
    ) -> str:
        """导出为思维导图格式"""
        if format == "markmap":
            return self._export_markmap(root)
        elif format == "mermaid":
            return self._export_mermaid(root)
        elif format == "opml":
            return self._export_opml(root)
        else:
            return self._export_markmap(root)

    def _extractive_summarize(
        self,
        text: str,
        language: str,
        top_k: int = 5,
    ) -> dict:
        """抽取式摘要"""
        sentences = self.text_cleaner._split_sentences(text, language)
        if len(sentences) <= top_k:
            return {
                "summary": " ".join(sentences),
                "key_points": sentences,
                "keywords": self._extract_keywords(text),
            }

        scored = []
        for i, sentence in enumerate(sentences):
            score = self._score_sentence_extractive(sentence, sentences, language)
            scored.append((score, sentence, i))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_sentences = scored[:top_k]
        top_sentences.sort(key=lambda x: x[2])

        key_points = [s[1] for s in top_sentences]
        summary = " ".join(key_points)
        keywords = self._extract_keywords(text)

        return {
            "summary": summary,
            "key_points": key_points,
            "keywords": keywords,
            "sentence_scores": [
                {"sentence": s, "score": round(sc, 4)}
                for sc, s, _ in top_sentences
            ],
        }

    def _abstractive_summarize(
        self,
        text: str,
        language: str,
        max_length: int,
        min_length: int,
    ) -> dict:
        """生成式摘要（基于Transformer模型）"""
        if not self._models_loaded:
            self.load_models()

        if self.model is None:
            return self._extractive_summarize(text, language)

        input_length = len(text)
        if input_length < min_length:
            max_length = min(input_length - 1, max_length)
            min_length = min(min_length, max_length - 1)

        if language == "zh" and self.model_zh:
            pipeline = self.summarizer_pipeline_zh
        else:
            pipeline = self.summarizer_pipeline

        try:
            result = pipeline(
                text,
                max_length=max_length,
                min_length=min_length,
                do_sample=False,
                truncation=True,
            )
            summary = result[0]["summary_text"]
        except Exception as e:
            logger.warning(f"生成式摘要失败，回退到抽取式: {e}")
            return self._extractive_summarize(text, language)

        keywords = self._extract_keywords(text)

        return {
            "summary": summary,
            "method": "abstractive",
            "keywords": keywords,
            "input_length": input_length,
            "output_length": len(summary),
        }

    def _hybrid_summarize(
        self,
        text: str,
        language: str,
        max_length: int,
        min_length: int,
    ) -> dict:
        """混合摘要"""
        extractive = self._extractive_summarize(text, language)

        if len(text) < 100 or not self._models_loaded:
            return extractive

        try:
            if self.model is not None:
                abstractive = self._abstractive_summarize(
                    text, language, max_length, min_length
                )
                return {
                    **abstractive,
                    "extractive_key_points": extractive.get("key_points", []),
                    "method": "hybrid",
                }
        except Exception:
            pass

        return extractive

    def _extract_keywords(
        self,
        text: str,
        top_k: int = 8,
    ) -> list[str]:
        """提取关键词"""
        if not text:
            return []

        try:
            keywords = jieba.analyse.extract_tags(
                text,
                topK=top_k,
                withWeight=False,
            )
            return keywords
        except Exception:
            return self._fallback_keyword_extraction(text, top_k)

    def _fallback_keyword_extraction(
        self,
        text: str,
        top_k: int,
    ) -> list[str]:
        """回退关键词提取（基于词频）"""
        words = [w for w in jieba.cut(text) if len(w) > 1]
        counter = Counter(words)

        stop_words = {"这个", "那个", "什么", "怎么", "为什么", "可以", "因为",
                       "所以", "但是", "然后", "如果", "一个", "一种", "一些",
                       "我们", "你们", "他们", "它们", "她们", "自己"}
        for sw in stop_words:
            counter.pop(sw, None)

        return [word for word, _ in counter.most_common(top_k)]

    def _extract_main_topic(
        self,
        paragraphs: list[str],
        language: str,
    ) -> str:
        """提取主主题"""
        all_text = " ".join(paragraphs)
        sentences = self.text_cleaner._split_sentences(all_text, language)

        if sentences:
            topic = sentences[0]
            if len(topic) > 50:
                topic = topic[:50] + "..."
            return topic
        return "未知主题"

    def _extract_sub_topic(
        self,
        paragraph: str,
        language: str,
    ) -> str:
        """提取子主题"""
        sentences = self.text_cleaner._split_sentences(paragraph, language)
        if not sentences:
            return ""

        first = sentences[0]
        keywords = self._extract_keywords(paragraph, top_k=3)

        if keywords:
            return f"{keywords[0]}: {first[:40]}{'...' if len(first) > 40 else ''}"
        return first[:50]

    def _extract_detail_points(
        self,
        paragraph: str,
        language: str,
    ) -> list[str]:
        """提取详细要点"""
        sentences = self.text_cleaner._split_sentences(paragraph, language)
        points = []

        for s in sentences:
            s = s.strip()
            if len(s) > 10 and not s.endswith("..."):
                points.append(s)

        return points[:5]

    def _score_sentence_extractive(
        self,
        sentence: str,
        all_sentences: list[str],
        language: str,
    ) -> float:
        """抽取式句子打分"""
        words = set(self._tokenize(sentence, language))
        if not words:
            return 0.0

        position_score = 0.0
        if len(all_sentences) > 0:
            idx = all_sentences.index(sentence) if sentence in all_sentences else 0
            position_score = max(0, 1.0 - idx / len(all_sentences))

        keyword_bonus = 0.0
        important_patterns = [
            r"key|关键|重要|核心|主要|总之|总结|结论|因此|所以",
            r"important|key|critical|essential|therefore|conclusion|summary",
        ]
        for pattern in important_patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                keyword_bonus += 0.3

        tf_idf_score = 0.0
        doc_count = len(all_sentences)
        for w in words:
            count = sum(1 for s in all_sentences if w in self._tokenize(s, language))
            tf_idf_score += 1 / max(count, 1)

        tf_idf_score = tf_idf_score / max(len(words), 1)

        return min(position_score * 0.3 + keyword_bonus + tf_idf_score * 0.5, 1.0)

    def _score_importance(
        self,
        paragraph: str,
        all_paragraphs: list[str],
        language: str,
    ) -> float:
        """评估段落重要性"""
        sentences = self.text_cleaner._split_sentences(paragraph, language)
        if not sentences:
            return 0.0

        scores = [
            self._score_sentence_extractive(s, sentences, language)
            for s in sentences
        ]
        return sum(scores) / len(scores)

    def _tokenize(self, text: str, language: str) -> list[str]:
        if language == "zh":
            return [w for w in jieba.cut(text) if len(w) > 1]
        else:
            return re.findall(r"\b[a-zA-Z]+\b", text.lower())

    @staticmethod
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _export_markmap(self, root: SummaryPoint) -> str:
        lines = ["---", "markmap:", "  colorFreezeLevel: 2", "---", ""]
        lines.append(f"# {root.title}")
        lines.append("")

        for i, child in enumerate(root.children):
            prefix = "##" if child.children else "-"
            lines.append(f"{prefix} **{child.title}**")

            if child.keywords:
                kw = " ".join(f"`{k}`" for k in child.keywords[:3])
                lines.append(f"  *{kw}*")

            l0_prefix = "  -" if child.children else ""
            for gc in child.children:
                lines.append(f"  {l0_prefix} {gc.title}")

            lines.append("")

        return "\n".join(lines)

    def _export_mermaid(self, root: SummaryPoint) -> str:
        lines = ["mindmap"]
        lines.append(f"  root(({root.title}))")

        for child in root.children:
            safe_title = child.title.replace('"', "'").replace("(", "[").replace(")", "]")
            lines.append(f"    {safe_title}")

            for gc in child.children:
                safe_gc = gc.title.replace('"', "'").replace("(", "[").replace(")", "]")
                lines.append(f"      {safe_gc}")

        return "\n".join(lines)

    def _export_opml(self, root: SummaryPoint) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<opml version="2.0">',
            "  <head>",
            f"    <title>{root.title}</title>",
            "  </head>",
            "  <body>",
            f'    <outline text="{root.title}">',
        ]

        for child in root.children:
            safe_title = child.title.replace('"', "'").replace("&", "&amp;")
            if child.children:
                lines.append(f'      <outline text="{safe_title}">')
                for gc in child.children:
                    safe_gc = gc.title.replace('"', "'").replace("&", "&amp;")
                    lines.append(f'        <outline text="{safe_gc}"/>')
                lines.append("      </outline>")
            else:
                lines.append(f'      <outline text="{safe_title}"/>')

        lines.extend([
            "    </outline>",
            "  </body>",
            "</opml>",
        ])
        return "\n".join(lines)


summarizer = Summarizer()
