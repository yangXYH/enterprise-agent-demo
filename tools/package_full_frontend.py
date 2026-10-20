"""Package the original Vue build, recording exactly which source produced it."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_files():
    frontend = ROOT / "frontend"
    return sorted([*frontend.joinpath("src").rglob("*"), *frontend.joinpath("public").rglob("*"),
                   *frontend.glob("*.json"), *frontend.glob("*.ts"), frontend / "index.html"])


def digest(path):
    raw = path.read_bytes()
    try:
        raw.decode("utf8")
        raw = raw.replace(b"\r\n", b"\n")
    except UnicodeError:
        pass
    return hashlib.sha256(raw).hexdigest()


def main():
    source = ROOT / "frontend/dist"
    target = ROOT / "demo/frontend"
    if not (source / "index.html").is_file():
        raise SystemExit("Build the original frontend first: cd frontend && npm ci && npm run build")
    # Remove only obsolete files from this generated bundle, never project source or uploads.
    target.mkdir(parents=True, exist_ok=True)
    for old in target.rglob("*"):
        if old.is_file() and not (source / old.relative_to(target)).is_file():
            old.unlink()
    shutil.copytree(source, target, dirs_exist_ok=True)
    manifest = {"source": {p.relative_to(ROOT).as_posix(): digest(p) for p in source_files() if p.is_file()},
                "bundle": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(target.rglob("*")) if p.is_file()}}
    (ROOT / "demo/frontend-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"Packaged original Vue app: {len(manifest['source'])} source files, {len(manifest['bundle'])} bundle files")


if __name__ == "__main__":
    main()
