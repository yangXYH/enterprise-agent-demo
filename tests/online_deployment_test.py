"""Deployment setup preserves server credentials and confines static file access."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_online", ROOT / "tools/prepare_online.py")
online = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online)


class OnlineDeploymentTest(unittest.TestCase):
    def test_generated_credentials_are_distinct_and_restarts_preserve_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = online.prepare(directory, "demo.example.com")
            before = path.read_bytes()
            values = dict(line.split("=", 1) for line in before.decode().splitlines() if line and not line.startswith("#"))
            self.assertEqual(values["DEMO_PUBLIC_HOST"], "demo.example.com")
            self.assertEqual(len(values["DEMO_DB_PASSWORD"]), 48)
            self.assertNotEqual(values["DEMO_DB_PASSWORD"], values["DEMO_ROOT_PASSWORD"])
            online.prepare(directory)
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_domains_cannot_inject_server_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for domain in ("https://example.com/", "example.com\nOTHER=bad", "a..com", "-bad.example"):
                with self.subTest(domain=domain), self.assertRaises(ValueError):
                    online.prepare(directory, domain)
            self.assertFalse((directory / ".env.online").exists())

    def test_static_routes_cannot_escape_the_frontend_directory(self):
        with patch.object(main, "_FRONTEND_DIST", ROOT / "demo/frontend"):
            self.assertEqual(main._resolve_frontend_file("index.html"), (ROOT / "demo/frontend/index.html").resolve())
            for path in ("../../main.py", "../../.env.online", str(ROOT / "main.py")):
                with self.subTest(path=path):
                    self.assertIsNone(main._resolve_frontend_file(path))


if __name__ == "__main__":
    unittest.main()
