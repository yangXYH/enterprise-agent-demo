"""Create server-local demo credentials; never overwrite an existing deployment."""
from __future__ import annotations

import argparse
import os
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(directory: Path, domain: str = "") -> Path:
    hostname = domain.strip().rstrip(".").lower()
    if hostname and (len(hostname) > 253 or "." not in hostname or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in hostname.split(".")
    )):
        raise ValueError("Use a domain name such as demo.example.com, without a URL, path or port.")
    target = directory / ".env.online"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("Existing .env.online retained. Edit it explicitly to change your domain or model configuration.")
        return target
    with os.fdopen(descriptor, "w", encoding="utf8", newline="\n") as output:
        output.write("# Server-local synthetic demo configuration. Do not commit this file.\n")
        output.write(f"DEMO_DB_PASSWORD={secrets.token_hex(24)}\n")
        output.write(f"DEMO_ROOT_PASSWORD={secrets.token_hex(24)}\n")
        output.write(f"DEMO_PUBLIC_HOST={hostname or ':80'}\n")
        output.write("# Optional model integration, using your own compatible service.\n")
        output.write("# LLM_API_KEY=\n# LLM_BASE_URL=\n# LLM_MODEL=\n")
    print("Created .env.online with generated demo database credentials; secret values are not printed.")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default="", help="Optional public domain; omit to use HTTP on the server IP.")
    args = parser.parse_args()
    try:
        prepare(ROOT, args.domain)
    except ValueError as error:
        parser.error(str(error))
    print("Start: docker compose --env-file .env.online -f compose.online.yml up -d --build")


if __name__ == "__main__":
    main()
