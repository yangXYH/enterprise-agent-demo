"""Report ingestion, shared persistence, search and protected original-file access."""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import product_quality_report_routes as routes
from tools.import_product_quality_reports import import_directory
from utils import product_quality_report_service as service


def pdf_bytes(width=100):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=100)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.patches = [patch.object(service, "DATA", root / "data"),
                        patch.object(service, "UPLOADS", root / "uploads"),
                        patch.object(service, "get_engine", return_value=self.engine)]
        for item in self.patches:
            item.start()
        self.raw = pdf_bytes()
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def test_search_normalizes_model_and_persists_for_other_readers(self):
        saved = service.save_report(self.raw, "TX5 09001-双肩包.pdf", "常规检测", "管理员")
        self.assertEqual(saved["report"]["models"], ["TX509001"])
        for keyword in ("tx5", "TX5-09001", "TX5_09001", "TX5 09001", "双肩包"):
            self.assertEqual(service.catalog(keyword)["total"], 1)
        self.assertEqual(service.catalog("BP4")["total"], 0)
        self.assertEqual(service.catalog(category="抗菌报告")["total"], 0)
        self.assertEqual(service.catalog()["summary"]["reports"], 1)
        self.assertNotIn("search_text", service.catalog()["reports"][0])
        self.assertEqual(service.report_path(saved["report"]["id"]).read_bytes(), self.raw)

    def test_duplicate_upload_keeps_original_name_and_record(self):
        first = service.save_report(self.raw, "TX509001.pdf", "常规检测", "A")
        again = service.save_report(self.raw, "改名.pdf", "其他", "B")
        self.assertFalse(first["duplicate"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["report"]["filename"], "TX509001.pdf")
        self.assertEqual(service.catalog()["total"], 1)

    def test_seed_merges_sources_and_repeat_import_is_idempotent(self):
        source = Path(self.directory.name) / "source"
        (source / "儿童书包").mkdir(parents=True)
        (source / "TX509001.pdf").write_bytes(self.raw)
        (source / "儿童书包" / "副本.pdf").write_bytes(self.raw)
        imported = import_directory(source)
        repeat = import_directory(source)
        self.assertEqual(imported, repeat)
        self.assertEqual(imported["imported_pdf_copies"], 2)
        self.assertEqual(imported["unique_reports"], 1)
        self.assertEqual(len(imported["reports"][0]["sources"]), 2)
        self.assertEqual(service.catalog(category="儿童书包")["total"], 1)
        # A fresh process sees the same seed without inserting another record.
        service._READY.discard(self.engine)
        self.assertEqual(service.catalog()["total"], 1)

    def test_pagination_retains_global_summary(self):
        for index in range(3):
            service.save_report(pdf_bytes(100 + index), f"BP40900{index}.pdf", "常规检测", "A")
        result = service.catalog(page=2, page_size=2)
        self.assertEqual(len(result["reports"]), 1)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["summary"]["models"], 3)

    def test_report_date_prefers_signature_over_arrival(self):
        self.assertEqual(service.extract_report_date("到样日期 2022 年 08 月 09 日 批准日期：2022 年08月12日"), "2022-08-12")
        self.assertEqual(service.extract_report_date("检测报告 SL62306262095501TX 日期 日期 :2023 年年 年年 04 月月 月月 01 日 到样日期 2023-03-24"), "2023-04-01")
        self.assertEqual(service.extract_report_date("样品受理/测试开始日期 2022-11-22 报告签发日期 2023-07-06"), "2023-07-06")
        self.assertEqual(service.extract_report_date("到样日期 2022-08-09"), "")

    def test_rejects_invalid_encrypted_and_oversized_files(self):
        for raw, name in ((b"not pdf", "x.pdf"), (self.raw, "x.exe"),
                          (b"%PDF-" + b"x" * service.MAX_FILE_SIZE, "x.pdf")):
            with self.assertRaises(ValueError):
                service.save_report(raw, name, "", "A")
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        stream = BytesIO()
        writer.write(stream)
        with self.assertRaises(ValueError):
            service.build_record(stream.getvalue(), "x.pdf", [], "test")
        # Permission-only encryption is readable without asking for a password.
        writer.encrypt("", owner_password="owner")
        stream = BytesIO()
        writer.write(stream)
        self.assertEqual(service.build_record(stream.getvalue(), "x.pdf", [], "test")["page_count"], 1)

    def test_api_returns_original_bytes_and_utf8_filename(self):
        saved = service.save_report(self.raw, "TX509001-双肩包.pdf", "常规检测", "A")["report"]
        with patch.object(routes, "authorize", return_value={"role": "operator"}):
            for download in (False, True):
                response = self.client.get(f"/api/product-quality-reports/{saved['id']}/file", params={"download": download})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, self.raw)
                disposition = response.headers["content-disposition"]
                self.assertTrue(disposition.startswith("attachment" if download else "inline"))
                self.assertIn("filename*=utf-8", disposition)
            self.assertEqual(self.client.get("/api/product-quality-reports/not-an-id/file").status_code, 404)
            self.assertEqual(self.client.get("/api/product-quality-reports", params={"page": 0}).status_code, 422)

    def test_auth_and_page_permission_cover_catalog_file_and_upload(self):
        saved = service.save_report(self.raw, "TX509001.pdf", "常规检测", "A")["report"]
        for status in (401, 403):
            with patch.object(routes, "authorize", side_effect=HTTPException(status, "denied")):
                self.assertEqual(self.client.get("/api/product-quality-reports").status_code, status)
                self.assertEqual(self.client.get(f"/api/product-quality-reports/{saved['id']}/file").status_code, status)
                self.assertEqual(self.client.post("/api/product-quality-reports/upload", files={"file": ("x.pdf", self.raw)}).status_code, status)

    def test_only_managers_upload_and_validation_is_reported(self):
        with patch.object(routes, "authorize", return_value={"role": "operator"}):
            self.assertFalse(self.client.get("/api/product-quality-reports").json()["can_upload"])
            self.assertEqual(self.client.post("/api/product-quality-reports/upload", files={"file": ("x.pdf", self.raw)}).status_code, 403)
        with patch.object(routes, "authorize", return_value={"role": "admin", "real_name": "A"}):
            self.assertTrue(self.client.get("/api/product-quality-reports").json()["can_upload"])
            response = self.client.post("/api/product-quality-reports/upload", files={"file": ("TX509001.pdf", self.raw)}, data={"category": "防水检测"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["report"]["categories"], ["防水检测"])
            response = self.client.post("/api/product-quality-reports/upload", files={"file": ("x.pdf", b"invalid")})
            self.assertEqual(response.status_code, 400)

    def test_permission_helper_honors_saved_page_grants(self):
        import main
        request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
        with patch.object(main, "_get_authenticated_user", return_value={"username": "cs", "role": "operator"}), \
             patch.object(main, "_get_mysql_engine", return_value=self.engine), \
             patch.object(routes.permission_service, "legacy_name_if_unique", return_value=""), \
             patch.object(routes.permission_service, "allowed_page_keys", return_value=[]):
            with self.assertRaises(HTTPException) as raised:
                routes.authorize(request)
            self.assertEqual(raised.exception.status_code, 403)
        with patch.object(main, "_get_authenticated_user", return_value={"role": "admin"}):
            self.assertEqual(routes.authorize(request)["role"], "admin")


if __name__ == "__main__":
    unittest.main()
