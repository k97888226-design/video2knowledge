from app.core.knowledge_builder import KnowledgeBuilder


class TestKnowledgeBuilder:
    def test_build_from_segments_creates_learning_pack(self):
        builder = KnowledgeBuilder()
        segments = [
            {
                "text": "Python 项目要强调业务价值和技术难点。",
                "start": 1.0,
                "end": 3.0,
            },
            {
                "text": "面试时要用数据说明自己的贡献。",
                "start": 4.0,
                "end": 6.0,
            },
        ]

        result = builder.build_from_segments(
            segments,
            language="zh",
            export_formats=["markdown", "json"],
        )

        assert result["interview_questions"]
        assert result["flashcards"]
        assert "时间戳知识树" in result["exports"]["markdown"]
        assert "面试问答" in result["exports"]["markdown"]
        assert "复习卡片" in result["exports"]["markdown"]
