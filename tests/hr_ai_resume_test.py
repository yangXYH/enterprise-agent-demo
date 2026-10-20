import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
from utils import operating_analysis_ai


class HrAiResumeTest(unittest.IsolatedAsyncioTestCase):
    async def test_hr_ai_uses_the_same_operating_runtime_as_company_qa(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"name":"张三"}'))]
        )

        class CompletionStub:
            def __init__(self):
                self.calls = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                return completion

        completions = CompletionStub()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        env = {
            "OPERATING_AI_KEY": "company-key",
            "OPERATING_AI_MODEL": "company-model",
            "OPERATING_AI_TIMEOUT_SECONDS": "12",
            "LLM_API_KEY": "legacy-key",
            "LLM_MODEL": "legacy-model",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(
            operating_analysis_ai, "_client", return_value=client
        ) as company_client, patch.object(main, "AsyncOpenAI") as legacy_client:
            payload, model = await main._call_hr_ai_json(
                [{"role": "user", "content": "extract"}], max_tokens=100
            )

        self.assertEqual(payload, {"name": "张三"})
        self.assertEqual(model, "company-model")
        self.assertEqual(completions.calls[0]["model"], "company-model")
        company_client.assert_called_once()
        legacy_client.assert_not_called()

    def test_json_parser_accepts_reasoning_fences_and_uses_final_object(self):
        raw = (
            '<think>先考虑 {"draft":true}</think>\n```json\n'
            '{"data":{"name":"李四","skills":["Excel",],},}\n```'
        )
        self.assertEqual(
            main._extract_llm_json_object(raw),
            {"name": "李四", "skills": ["Excel"]},
        )

    def test_interview_fields_cross_check_model_digits_with_source(self):
        text = """姓名：王小明
求职意向：直播运营
性别：女
年龄：28岁
出生年月：1998.03
联系电话：138-1234-5678
"""
        normalized = main._normalize_interview_resume_data(
            {
                "candidate_name": "王小明",
                "job_title": "招商主管",
                "phone": "13812345679",
                "gender": "男",
            },
            resume_text=text,
            filename="王小明-简历.pdf",
        )
        self.assertEqual(normalized["name"], "王小明")
        self.assertEqual(normalized["position"], "直播运营")
        self.assertEqual(normalized["phone"], "13812345678")
        self.assertEqual(normalized["gender"], "女")
        self.assertEqual(normalized["age"], "28")
        self.assertEqual(normalized["birthday"], "1998.03")

    def test_resume_review_accepts_aliases_and_discards_extra_reasoning(self):
        result = main._parse_resume_llm_json(
            """{
              "candidate_name": "赵六",
              "education_background": {"degree":"本科","school":"某大学"},
              "core_skills": "Excel、招聘、数据分析",
              "work_experience": [{"company":"甲公司","position":"招聘专员","period":"2022-2025"}],
              "matching_score": "86分",
              "assessment": "《匹配优势》有三年招聘经验。\\n《风险短板》行业经验待核验。\\n《面试核验建议》追问招聘漏斗数据。",
              "reasoning": "这个字段不应进入响应"
            }"""
        )
        self.assertEqual(result.name, "赵六")
        self.assertEqual(result.skills, ["Excel", "招聘", "数据分析"])
        self.assertEqual(result.match_score, 86)
        self.assertIn("甲公司", result.experience)


if __name__ == "__main__":
    unittest.main()
