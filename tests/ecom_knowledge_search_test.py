import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

from utils import ecom_knowledge_service as service


class EcomKnowledgeHybridSearchTest(unittest.TestCase):
    def setUp(self):
        service.invalidate_bm25_cache()

    def tearDown(self):
        service.invalidate_bm25_cache()

    def test_cross_library_search_ranks_relevant_document_and_keeps_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "support").mkdir()
            (root / "warehouse").mkdir()
            (root / "support" / "售后规则.txt").write_text(
                "退换货规则：签收后七天内可以申请退货，商品需保持完好。",
                encoding="utf-8",
            )
            (root / "warehouse" / "盘点流程.txt").write_text(
                "仓库每月盘点一次，盘点差异由仓库主管复核。",
                encoding="utf-8",
            )

            with patch.object(service, "_KNOWLEDGE_ROOT", root):
                results, candidate_count = service._hybrid_recall(
                    "退款有效期多久", ["support", "warehouse"], top_k=4
                )

            self.assertEqual(candidate_count, 2)
            self.assertTrue(results)
            self.assertEqual(results[0]["library"], "support")
            self.assertEqual(results[0]["name"], "售后规则.txt")
            self.assertTrue(results[0]["matched_by"])

    def test_plain_text_evidence_snippet_is_not_dropped(self):
        snippet = service._qa_make_snippet("普通制度正文第一行\n普通制度正文第二行")
        self.assertIn("普通制度正文第一行", snippet)

    def test_large_spreadsheet_uses_streaming_extraction_instead_of_being_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "知识表.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["主题", "内容"])
            sheet.append(["AI 模特", "人物构图与灯光关键词"])
            workbook.save(path)
            workbook.close()

            with patch.object(service, "_KB_QA_MAX_FILE_BYTES", 1):
                extracted = service._qa_extract_text(path)

            self.assertIn("AI 模特", extracted)
            self.assertIn("人物构图与灯光关键词", extracted)


if __name__ == "__main__":
    unittest.main()
