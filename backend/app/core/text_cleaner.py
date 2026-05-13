import re
from typing import Optional

import jieba
from loguru import logger


class TextCleaner:
    """文本清洗与智能分段模块"""

    FILLER_WORDS_ZH = {
        "嗯", "啊", "哦", "呃", "那个", "这个", "就是", "然后", "就是说",
        "怎么说呢", "是吧", "对吧", "对不对", "这样子", "那么", "反正",
        "基本上", "实际上", "其实", "你知道", "我想想", "那个什么",
    }

    FILLER_WORDS_EN = {
        "um", "uh", "er", "ah", "like", "you know", "i mean",
        "sort of", "kind of", "basically", "actually", "literally",
        "right", "okay", "so", "well", "anyway",
    }

    FILLER_PATTERNS_ZH = [
        re.compile(r"([啊嗯哦呃诶哎哟]){2,}"),
        re.compile(r"(那个|这个|就是|然后|就是说)(\s*(那个|这个|就是|然后|就是说)){1,}"),
    ]

    FILLER_PATTERNS_EN = [
        re.compile(r"\b(um+|uh+|er+|ah+)\b", re.IGNORECASE),
        re.compile(r"\b(like|you know|i mean)\b(\s+\1\b)*", re.IGNORECASE),
    ]

    PARAGRAPH_BOUNDARY_MARKERS_ZH = [
        r"(?:首先|第一|其次|再者|另外|此外|接下来|最后|总之|综上所述|那么)\s*[,，]",
        r"(?:所以|因此|因而|于是|这样|那么|可见|显然|当然)\s*[,，]",
        r"(?:但是|然而|不过|可是|却|反而|相反)\s*[,，]",
        r"(?:而且|并且|同时|另外|此外|还不止如此)\s*[,，]",
    ]

    PARAGRAPH_BOUNDARY_MARKERS_EN = [
        r"\b(?:First|Second|Third|Finally|In conclusion|To summarize)\b",
        r"\b(?:Therefore|Thus|Hence|Consequently|As a result)\b",
        r"\b(?:However|Nevertheless|Nonetheless|On the other hand)\b",
        r"\b(?:Moreover|Furthermore|Additionally|In addition)\b",
    ]

    def __init__(self):
        self._ensure_jieba_loaded()

    def clean(
        self,
        text: str,
        language: str = "zh",
        remove_fillers: bool = True,
        normalize_punctuation: bool = True,
        remove_duplicates: bool = True,
    ) -> str:
        """清洗文本"""
        if not text:
            return ""

        text = self._normalize_whitespace(text)

        if normalize_punctuation:
            text = self._normalize_punctuation(text, language)

        if remove_duplicates:
            text = self._remove_duplicate_sentences(text, language)

        if remove_fillers:
            text = self._remove_filler_words(text, language)

        text = self._normalize_whitespace(text)

        return text

    def segment_paragraphs(
        self,
        text: str,
        language: str = "zh",
        method: str = "semantic",
        max_paragraph_length: int = 500,
    ) -> list[str]:
        """智能划分段落"""
        if not text:
            return []

        sentences = self._split_sentences(text, language)

        if method == "boundary":
            paragraphs = self._segment_by_boundary(sentences, language)
        elif method == "length":
            paragraphs = self._segment_by_length(sentences, max_paragraph_length)
        elif method == "semantic":
            paragraphs = self._segment_by_semantic(sentences, language, max_paragraph_length)
        else:
            paragraphs = self._segment_by_boundary(sentences, language)

        return [p for p in paragraphs if p.strip()]

    def extract_key_sentences(
        self,
        text: str,
        language: str = "zh",
        top_k: int = 10,
    ) -> list[dict]:
        """提取关键句子"""
        sentences = self._split_sentences(text, language)

        if len(sentences) <= top_k:
            return [
                {"sentence": s, "score": 1.0, "index": i}
                for i, s in enumerate(sentences)
            ]

        scored_sentences = []
        for i, sentence in enumerate(sentences):
            score = self._score_sentence(sentence, sentences, language)
            scored_sentences.append({
                "sentence": sentence,
                "score": round(score, 4),
                "index": i,
            })

        scored_sentences.sort(key=lambda x: x["score"], reverse=True)
        return scored_sentences[:top_k]

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _normalize_punctuation(self, text: str, language: str) -> str:
        """标点符号规范化"""
        if language == "zh":
            replacements = {
                "！": "!", "？": "?", "，": ",", "。": ".",
                "；": ";", "：": ":", "（": "(", "）": ")",
                "“": '"', "”": '"', "‘": "'", "’": "'",
                "、": ",", "…": "...", "—": "-", "～": "~",
            }
            for old, new in replacements.items():
                text = text.replace(old, new)

            text = re.sub(r"[,.!?;:]+(?=[,.!?;:，。！？；：])", "", text)
            text = re.sub(r"[,!?;:]+", lambda m: m.group(0)[0], text)
            text = re.sub(r"\.{3,}", "...", text)

        else:
            text = re.sub(r"[,.!?;:]+(?=[,.!?;:])", "", text)
            text = re.sub(r"\.{3,}", "...", text)

        return text

    def _remove_filler_words(self, text: str, language: str) -> str:
        """移除语气词"""
        if language == "zh":
            for pattern in self.FILLER_PATTERNS_ZH:
                text = pattern.sub("", text)

            words = text.split()
            words = [
                w for w in words
                if w not in self.FILLER_WORDS_ZH
            ]
            text = " ".join(words)
        else:
            for pattern in self.FILLER_PATTERNS_EN:
                text = pattern.sub("", text)

            words = text.split()
            words = [
                w for w in words
                if w.lower() not in self.FILLER_WORDS_EN
            ]
            text = " ".join(words)

        return text

    def _remove_duplicate_sentences(self, text: str, language: str) -> str:
        """移除重复句子"""
        sentences = self._split_sentences(text, language)
        seen = set()
        unique = []

        for s in sentences:
            normalized = s.strip().lower().rstrip(",.!?;:，。！？；：")
            if len(normalized) < 5:
                unique.append(s)
                continue
            if normalized not in seen:
                seen.add(normalized)
                unique.append(s)

        return " ".join(unique)

    def _split_sentences(self, text: str, language: str) -> list[str]:
        """分句"""
        if language == "zh":
            text = re.sub(r"([。！？!?\n])([^。！？!?\n])", r"\1\n\2", text)
            text = re.sub(r"([，,;；])([^，,;；])", r"\1 \2", text)
        else:
            text = re.sub(r"([.!?])\s+([A-Z])", r"\1\n\2", text)

        sentences = []
        for s in text.split("\n"):
            s = s.strip()
            if not s:
                continue

            if language == "zh" and len(s) > 200:
                sub_sentences = re.split(r"([，,;；])", s)
                merged = []
                for i in range(0, len(sub_sentences) - 1, 2):
                    merged.append(
                        sub_sentences[i].strip() +
                        (sub_sentences[i + 1] if i + 1 < len(sub_sentences) else "")
                    )
                if len(sub_sentences) % 2 == 1:
                    merged.append(sub_sentences[-1].strip())
                sentences.extend(m for m in merged if m.strip())
            else:
                sentences.append(s)

        return [s.strip() for s in sentences if s.strip()]

    def _segment_by_boundary(self, sentences: list[str], language: str) -> list[str]:
        """根据边界词划分段落"""
        paragraphs = []
        current = []

        patterns = (
            self.PARAGRAPH_BOUNDARY_MARKERS_ZH
            if language == "zh"
            else self.PARAGRAPH_BOUNDARY_MARKERS_EN
        )

        for sentence in sentences:
            is_boundary = any(
                re.search(pattern, sentence)
                for pattern in patterns
            )

            if is_boundary and current:
                paragraphs.append(" ".join(current))
                current = []

            current.append(sentence)

        if current:
            paragraphs.append(" ".join(current))

        return paragraphs

    def _segment_by_length(
        self,
        sentences: list[str],
        max_length: int,
    ) -> list[str]:
        """根据长度划分段落"""
        paragraphs = []
        current = []
        current_length = 0

        for sentence in sentences:
            if current_length + len(sentence) > max_length and current:
                paragraphs.append(" ".join(current))
                current = []
                current_length = 0

            current.append(sentence)
            current_length += len(sentence)

        if current:
            paragraphs.append(" ".join(current))

        return paragraphs

    def _segment_by_semantic(
        self,
        sentences: list[str],
        language: str,
        max_length: int,
    ) -> list[str]:
        """基于语义相似度划分段落"""
        if len(sentences) <= 1:
            return [" ".join(sentences)] if sentences else []

        paragraphs = []
        current = [sentences[0]]
        current_length = len(sentences[0])

        for i in range(1, len(sentences)):
            similarity = self._sentence_similarity(
                current[-1], sentences[i], language
            )

            if similarity < 0.3 or current_length + len(sentences[i]) > max_length:
                if current:
                    paragraphs.append(" ".join(current))
                current = [sentences[i]]
                current_length = len(sentences[i])
            else:
                current.append(sentences[i])
                current_length += len(sentences[i])

        if current:
            paragraphs.append(" ".join(current))

        return paragraphs

    def _score_sentence(
        self,
        sentence: str,
        all_sentences: list[str],
        language: str,
    ) -> float:
        """给句子打分（基于TF-IDF类似思想）"""
        words = self._tokenize(sentence, language)
        if not words:
            return 0.0

        tf = {}
        for w in words:
            tf[w] = tf.get(w, 0) + 1

        doc_count = len(all_sentences)
        idf = {}
        for w in set(words):
            count = sum(1 for s in all_sentences if w in self._tokenize(s, language))
            idf[w] = (doc_count / max(count, 1))

        score = sum(
            tf[w] * idf.get(w, 0)
            for w in set(words)
        )
        score = score / len(words)

        return min(score, 10.0)

    def _sentence_similarity(self, a: str, b: str, language: str) -> float:
        """句子相似度"""
        words_a = set(self._tokenize(a, language))
        words_b = set(self._tokenize(b, language))

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union)

    def _tokenize(self, text: str, language: str) -> list[str]:
        """分词"""
        if language == "zh":
            return [w for w in jieba.cut(text) if len(w.strip()) > 1]
        else:
            return re.findall(r"\b[a-zA-Z]+\b", text.lower())

    def _ensure_jieba_loaded(self):
        try:
            jieba.initialize()
        except Exception:
            pass

    def get_statistics(self, text: str, language: str = "zh") -> dict:
        """获取文本统计信息"""
        sentences = self._split_sentences(text, language)
        words = self._tokenize(text, language)
        chars = len(text.replace(" ", ""))

        return {
            "total_sentences": len(sentences),
            "total_words": len(words),
            "total_characters": len(text),
            "chars_no_spaces": chars,
            "avg_sentence_length": round(chars / max(len(sentences), 1), 1),
            "avg_word_length": round(
                sum(len(w) for w in words) / max(len(words), 1), 1
            ) if words else 0,
            "language": language,
        }


text_cleaner = TextCleaner()
