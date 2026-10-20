import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import BackgroundTasks, UploadFile

import main


class SkuJstLookupApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_template_endpoint_returns_excel(self) -> None:
        with patch.object(
            main.inventory_service,
            "build_sku_jst_lookup_template",
            return_value=b"xlsx-bytes",
        ):
            response = await main.download_sku_jst_lookup_template()

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.openxmlformats", response.media_type)

    async def test_import_endpoint_parses_upload(self) -> None:
        upload = UploadFile(filename="mapping.xlsx", file=BytesIO(b"xlsx-content"))
        with TemporaryDirectory() as tmp_dir:
            temp_path = Path(tmp_dir) / "upload.xlsx"
            temp_path.write_bytes(b"xlsx-content")
            with (
                patch.object(
                    main,
                    "_save_upload_to_temp_file",
                    return_value=temp_path,
                ),
                patch.object(
                    main.inventory_service,
                    "import_sku_jst_lookup_excel",
                    return_value={
                        "rows_read": 2,
                        "imported": 2,
                        "skipped": 0,
                        "sku_codes": ["SKU-1", "SKU-2"],
                    },
                ) as import_service,
            ):
                background_tasks = BackgroundTasks()
                response = await main.import_sku_jst_lookup(upload, background_tasks)

        import_service.assert_called_once_with(temp_path, None)
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"]["imported"], 2)
        self.assertTrue(response["data"]["sync_triggered"])
        self.assertEqual(len(background_tasks.tasks), 1)
        self.assertFalse(temp_path.exists())

    async def test_import_endpoint_rejects_non_xlsx(self) -> None:
        upload = UploadFile(filename="mapping.csv", file=BytesIO(b"csv-content"))
        with self.assertRaises(Exception) as raised:
            await main.import_sku_jst_lookup(upload, BackgroundTasks())
        self.assertEqual(raised.exception.status_code, 400)

    async def test_list_endpoint_passes_filters(self) -> None:
        payload = {
            "items": [{"sku_code": "SKU-1", "lookup_code": "JST-1"}],
            "total": 1,
            "page": 2,
            "page_size": 50,
        }
        with patch.object(
            main.inventory_service,
            "list_sku_jst_lookup_mappings",
            return_value=payload,
        ) as list_service:
            response = await main.list_sku_jst_lookup(
                sku_code="SKU-1",
                page=2,
                page_size=50,
            )

        list_service.assert_called_once_with(None, "SKU-1", 2, 50)
        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0]["lookup_code"], "JST-1")


if __name__ == "__main__":
    unittest.main()
