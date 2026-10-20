"""Import SKU settlement workbooks with an explicit dry-run/apply switch.

Usage:
  .venv/Scripts/python tools/import_sku_return_data.py "C:/.../SKU退货率页面" --dry-run
  .venv/Scripts/python tools/import_sku_return_data.py "C:/.../SKU退货率页面" --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.sku_return_service import import_source_tree  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="SKU 退货结算单全量导入与质量对账")
    parser.add_argument("root", type=Path, help="包含年份结算单目录的根目录")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只扫描并打印质量报告，不连接数据库")
    mode.add_argument("--apply", action="store_true", help="写入暂存版本，校验后原子发布")
    parser.add_argument("--report", type=Path, help="另存完整 JSON 质量报告")
    arguments = parser.parse_args()
    if arguments.apply:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    started = time.monotonic()
    result = import_source_tree(arguments.root, apply=arguments.apply)
    report = result["report"] if arguments.apply else result
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result.get("status", "dry_run") if arguments.apply else "dry_run",
        "run_id": result.get("run_id") if arguments.apply else None,
        "manifest_sha256": report["manifest_sha256"],
        "file_count": report["file_count"],
        "source_units": report["source_units"],
        "auxiliary_sheets": report["auxiliary_sheets"],
        "scanned_rows": report["scanned_rows"],
        "target_rows": report["target_rows"],
        "isolated_rows": report["isolated_rows"],
        "duplicate_rows": report["duplicate_rows"],
        "included_rows": report["included_rows"],
        "by_document_type": report["by_document_type"],
        "quality": report["quality"],
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
