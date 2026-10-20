"""Build a portable seed catalog from PDFs and PDFs inside ZIP archives.

Run from the repository root: python -m tools.import_product_quality_reports SOURCE
Repeated import is safe: identical bytes share one record and original file.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from utils import product_quality_report_service as service


def categories_for(source: str) -> list[str]:
    parts = source.replace("\\", "/").split("/")[:-1]
    categories = []
    for part in parts:
        if part.endswith(".zip") or part == "示例科技检测报告":
            continue
        categories.append("2026年报告" if part == "26年" else part)
    return categories or ["常规检测"]


def import_directory(source: Path) -> dict:
    manifest = service.DATA / "catalog.json"
    existing = json.loads(manifest.read_text(encoding="utf-8"))["reports"] if manifest.exists() else []
    records = {record["id"]: record for record in existing}
    files = service.DATA / "files"
    files.mkdir(parents=True, exist_ok=True)
    count = 0
    skipped = []

    def add(raw: bytes, relative: str):
        nonlocal count
        record = service.build_record(raw, relative.rsplit("/", 1)[-1], categories_for(relative), relative)
        count += 1
        previous = records.get(record["id"])
        if previous:
            new_source = relative not in previous["sources"]
            previous["report_number"] = record["report_number"]
            previous["report_date"] = record["report_date"]
            for key in ("models", "categories", "sources"):
                previous[key] = sorted(set(previous[key]) | set(record[key]))
            if new_source:
                previous["search_text"] += service.normalize_search(relative + " " + " ".join(record["categories"]))
        else:
            records[record["id"]] = record
        target = files / (record["id"] + ".pdf")
        if not target.exists():
            target.write_bytes(raw)

    for file in sorted(source.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(source).as_posix()
        if file.suffix.lower() == ".pdf":
            add(file.read_bytes(), relative)
        elif file.suffix.lower() == ".zip":
            with zipfile.ZipFile(file) as archive:
                for entry in archive.infolist():
                    if entry.is_dir():
                        continue
                    name = entry.filename
                    if not entry.flag_bits & 0x800:
                        try:
                            name = name.encode("cp437").decode("gbk")
                        except UnicodeError:
                            pass
                    if name.lower().endswith(".pdf"):
                        if entry.file_size > service.MAX_FILE_SIZE:
                            raise ValueError(f"压缩包内报告过大：{name}")
                        with archive.open(entry) as stream:
                            add(stream.read(service.MAX_FILE_SIZE + 1), relative + "/" + name)
                    else:
                        skipped.append(relative + "/" + name)
        else:
            skipped.append(relative)
    result = {"reports": sorted(records.values(), key=lambda item: item["filename"]),
              "imported_pdf_copies": count, "unique_reports": len(records), "skipped": skipped}
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    arguments = parser.parse_args()
    if not arguments.source.is_dir():
        parser.error("source 必须是报告文件夹")
    result = import_directory(arguments.source)
    print(json.dumps({key: value for key, value in result.items() if key != "reports"}, ensure_ascii=False))
