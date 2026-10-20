"""Check the Git candidate file set without printing any matched secret values."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_EXTENSIONS = {".xlsx", ".xls", ".pdf", ".docx", ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".log"}
SECRET_PATTERNS = [r"sk-[A-Za-z0-9_-]{20,}", r"AKIA[0-9A-Z]{16}",
                   r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                   r"eyJ[A-Za-z0-9_-]{12,}\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"]


def main() -> int:
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=ROOT, capture_output=True, check=True)
    candidates = sorted(set(Path(name.decode("utf8")) for name in result.stdout.split(b"\0") if name))
    findings = []
    scanned = 0
    for relative in candidates:
        path = ROOT / relative
        if not path.is_file():
            continue
        scanned += 1
        parts = {part.lower() for part in relative.parts}
        if {"node_modules", ".venv", "uploads", "outputs", ".git"} & parts:
            findings.append((str(relative), "private runtime/dependency directory"))
        if path.suffix.lower() in PRIVATE_EXTENSIONS:
            findings.append((str(relative), "private document or runtime file type"))
        if path.name.startswith(".env") and not path.name.endswith(".example"):
            findings.append((str(relative), "non-template environment file"))
        if path.stat().st_size > 5 * 1024 * 1024:
            findings.append((str(relative), "unexpected large public file"))
        try:
            source = path.read_text(encoding="utf8")
        except (UnicodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, source):
                findings.append((str(relative), "credential-like literal; inspect locally"))
        if re.search(r"[C-F]:[\\/]Users[\\/]", source, re.I):
            findings.append((str(relative), "personal user-directory path"))
    payload = json.loads((ROOT / "data/shop_report.json").read_text(encoding="utf8"))
    if not payload.get("source", {}).get("synthetic"):
        findings.append(("data/shop_report.json", "snapshot is not marked synthetic"))
    for name, reason in findings:
        print(f"FAIL {name}: {reason}")
    print(f"Public candidate check: {scanned} files, {len(findings)} findings. Pattern checks do not replace review.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
