"""Shared product inspection reports: MySQL metadata and unchanged PDF originals."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from weakref import WeakSet

from pypdf import PdfReader
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from utils.import_service import get_engine

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "product-quality-reports"
UPLOADS = ROOT / "uploads" / "product-quality-reports"
MAX_FILE_SIZE = 30 * 1024 * 1024
REPORT_ID = re.compile(r"[0-9a-f]{64}\Z")
_READY: WeakSet[Engine] = WeakSet()
_LOCK = Lock()
_METADATA = MetaData()
REPORTS = Table(
    "product_quality_report", _METADATA,
    Column("id", String(64), primary_key=True),
    Column("filename", String(255), nullable=False),
    Column("models_json", Text, nullable=False),
    Column("categories_json", Text, nullable=False),
    Column("sources_json", Text, nullable=False),
    Column("search_text", Text, nullable=False),
    Column("report_number", String(100), nullable=False),
    Column("report_date", String(10), nullable=False),
    Column("page_count", Integer, nullable=False),
    Column("file_size", Integer, nullable=False),
    Column("created_by", String(191), nullable=False),
    Column("created_at", DateTime, nullable=False),
    mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
)


def normalize_search(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value).casefold()


def extract_report_date(extracted: str) -> str:
    compact = re.sub(r"\s+", "", extracted)
    compact = re.sub(r"([年月日])\1+", r"\1", compact)
    date_pattern = r"(20\d{2})(?:年|[-/.])(\d{1,2})(?:月|[-/.])(\d{1,2})"
    # Prefer the issue/approval date, never an arrival or testing-start date.
    patterns = [r"(?:报告签发日期|签发日期|批准日期|报告日期|出具日期)[:：]?" + date_pattern,
                r"检测报告.{0,120}?日期(?:日期)*[:：]?" + date_pattern]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            try:
                return datetime(*map(int, match.groups())).date().isoformat()
            except ValueError:
                pass
    return ""


def build_record(raw: bytes, filename: str, categories: list[str], source: str) -> dict[str, Any]:
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename.lower().endswith(".pdf") or len(filename) > 255:
        raise ValueError("请上传文件名不超过 255 个字符的 PDF 报告")
    if not raw or len(raw) > MAX_FILE_SIZE:
        raise ValueError("单份报告不能超过 30 MB，且不能为空")
    if not raw.startswith(b"%PDF-"):
        raise ValueError("文件内容不是有效的 PDF")
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("请先解除 PDF 密码保护再上传")
        page_count = len(reader.pages)
        if not page_count:
            raise ValueError("PDF 没有可预览的页面")
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages[:2])
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF 无法读取，请检查文件是否损坏") from exc

    model_text = filename + "\n" + extracted
    models = sorted({
        (match[0] + match[1]).upper()
        for match in re.findall(r"(?<![A-Za-z0-9])([A-Za-z]{2}\d)[\s*_\-]*(\d{5})(?!\d)", model_text)
    })
    models.extend(sorted({
        a + b for a, b in re.findall(r"(?<!\d)(\d{3})\s*\*\s*(\d{5})(?!\d)", extracted)
    } - set(models)))
    compact = re.sub(r"\s+", "", extracted)
    explicit_number = re.search(r"(?:报告编号|No)[:：.]([A-Za-z]?\d{8,20}[A-Za-z]{0,3})", compact)
    numbers = re.findall(r"SL\d{10,20}TX|\b\d{10}\b|\b\d{2}H\d{6}\b", filename + "\n" + extracted)
    categories = sorted({item.strip()[:100] for item in categories if item.strip()}) or ["常规检测"]
    return {
        "id": hashlib.sha256(raw).hexdigest(), "filename": filename,
        "models": models, "categories": categories, "sources": [source[:1024]],
        "search_text": normalize_search(" ".join([filename, extracted[:16000], *models, *categories, source])),
        "report_number": explicit_number.group(1) if explicit_number else (numbers[0] if numbers else ""),
        "report_date": extract_report_date(extracted),
        "page_count": page_count, "file_size": len(raw),
    }


def _values(record: dict[str, Any], user_name: str) -> dict[str, Any]:
    return {
        **{key: record[key] for key in ("id", "filename", "search_text", "report_number", "report_date", "page_count", "file_size")},
        **{key + "_json": json.dumps(record[key], ensure_ascii=False) for key in ("models", "categories", "sources")},
        "created_by": user_name[:191], "created_at": datetime.now(),
    }


def ensure_ready(engine: Engine | None = None) -> Engine:
    selected = engine if engine is not None else get_engine()
    if selected in _READY:
        return selected
    with _LOCK:
        if selected not in _READY:
            _METADATA.create_all(selected)
            manifest = DATA / "catalog.json"
            records = json.loads(manifest.read_text(encoding="utf-8"))["reports"] if manifest.exists() else []
            for record in records:
                # A duplicate key from another worker is harmless; preserve saved metadata.
                try:
                    with selected.begin() as connection:
                        if connection.execute(select(REPORTS.c.id).where(REPORTS.c.id == record["id"])).first():
                            continue
                        connection.execute(REPORTS.insert().values(**_values(record, "资料导入")))
                except IntegrityError:
                    with selected.connect() as connection:
                        if not connection.execute(select(REPORTS.c.id).where(REPORTS.c.id == record["id"])).first():
                            raise
            _READY.add(selected)
    return selected


def _public(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("models", "categories", "sources"):
        item[key] = json.loads(item.pop(key + "_json"))
    item.pop("search_text", None)
    item["created_at"] = item["created_at"].isoformat(timespec="seconds")
    return item


def catalog(keyword: str = "", category: str = "", page: int = 1, page_size: int = 12,
            engine: Engine | None = None) -> dict[str, Any]:
    selected = ensure_ready(engine)
    with selected.connect() as connection:
        rows = connection.execute(select(REPORTS).order_by(
            REPORTS.c.report_date.desc(), REPORTS.c.created_at.desc(), REPORTS.c.filename.asc(),
        )).mappings().all()
    items = [_public(row) for row in rows]
    categories = sorted({category for item in items for category in item["categories"]})
    terms = [normalize_search(term) for term in keyword.split() if normalize_search(term)]
    filtered = [item for row, item in zip(rows, items)
                if (not category or category in item["categories"])
                and all(term in row["search_text"] for term in terms)]
    start = (page - 1) * page_size
    return {
        "reports": filtered[start:start + page_size], "total": len(filtered),
        "page": page, "page_size": page_size, "categories": categories,
        "summary": {"reports": len(items), "models": len({model for item in items for model in item["models"]}),
                    "categories": len(categories)},
    }


def get_report(report_id: str, engine: Engine | None = None) -> dict[str, Any] | None:
    if not REPORT_ID.fullmatch(report_id):
        return None
    selected = ensure_ready(engine)
    with selected.connect() as connection:
        row = connection.execute(select(REPORTS).where(REPORTS.c.id == report_id)).mappings().first()
    return _public(row) if row else None


def report_path(report_id: str) -> Path | None:
    if not REPORT_ID.fullmatch(report_id):
        return None
    for directory in (DATA / "files", UPLOADS):
        path = directory / (report_id + ".pdf")
        if path.is_file():
            return path
    return None


def save_report(raw: bytes, filename: str, category: str, user_name: str,
                engine: Engine | None = None) -> dict[str, Any]:
    record = build_record(raw, filename, [category], "在线上传")
    selected = ensure_ready(engine)
    previous = get_report(record["id"], selected)
    if previous and report_path(record["id"]):
        return {"report": previous, "duplicate": True}
    UPLOADS.mkdir(parents=True, exist_ok=True)
    target = UPLOADS / (record["id"] + ".pdf")
    descriptor, temporary = tempfile.mkstemp(dir=UPLOADS, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(raw)
        os.replace(temporary, target)
        if not previous:
            try:
                with selected.begin() as connection:
                    connection.execute(REPORTS.insert().values(**_values(record, user_name)))
            except IntegrityError:
                if not get_report(record["id"], selected):
                    raise
                return {"report": get_report(record["id"], selected), "duplicate": True}
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"report": get_report(record["id"], selected), "duplicate": bool(previous)}
