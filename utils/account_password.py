"""Password storage for sys_user. Existing plaintext values remain readable during migration."""

import base64
import hashlib
import hmac
import os

ITERATIONS = 260_000
PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"{PREFIX}${ITERATIONS}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    if not stored.startswith(PREFIX + "$"):
        return hmac.compare_digest(password, stored)
    try:
        prefix, count, raw_salt, raw_digest = stored.split("$")
        if prefix != PREFIX or not 100_000 <= int(count) <= 1_000_000:
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        salt, expected = decode(raw_salt), decode(raw_digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(count))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def password_tag(stored: str) -> str:
    return hashlib.sha256(stored.encode("utf-8")).hexdigest()[:24]
