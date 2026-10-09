"""Shared test helpers: every test runs against a throw-away copy of the content."""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
PASSWORD = "correct horse battery staple"


class AppTestCase(unittest.TestCase):
    env = "development"
    extra_env: dict[str, str] = {}
    with_admin = True

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="site-test-"))
        shutil.copytree(ROOT / "content", self.tmp / "content",
                        ignore=shutil.ignore_patterns("history", "uploads"))
        (self.tmp / "content" / "uploads").mkdir()
        (self.tmp / "content" / "history").mkdir()
        self._old_env = dict(os.environ)
        os.environ.update({"CONTENT_DIR": str(self.tmp / "content"),
                           "INSTANCE_DIR": str(self.tmp / "instance"),
                           **self.extra_env})
        from app import create_app
        from app.security import AdminAccount
        self.app = create_app(self.env, {"TESTING": True})
        if self.with_admin and self.app.config["ADMIN_ENABLED"]:
            AdminAccount(self.tmp / "instance" / "admin.json").create("armin", PASSWORD, TOTP_SECRET)
        self.client = self.app.test_client()
        self.admin = self.app.config.get("ADMIN_PATH", "/admin")

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- helpers ---------------------------------------------------------
    ORIGIN = {"Origin": "http://localhost"}

    def csrf(self, path: str) -> str:
        html = self.client.get(path).get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        assert m, f"no csrf token on {path}"
        return m.group(1)

    def post(self, path: str, data: dict | None = None, token_from: str | None = None, **kw):  # type: ignore[no-untyped-def]
        data = dict(data or {})
        data.setdefault("csrf_token", self.csrf(token_from or path))
        return self.client.post(path, data=data, headers=self.ORIGIN, **kw)

    def login(self) -> None:
        from app.security import totp_now
        r = self.post(f"{self.admin}/login", {"username": "armin", "password": PASSWORD})
        assert r.status_code == 302, r.status_code
        r = self.post(f"{self.admin}/login/2fa", {"code": totp_now(TOTP_SECRET)})
        assert r.status_code == 302 and r.headers["Location"].endswith(f"{self.admin}/"), r.status_code

    @staticmethod
    def png_bytes() -> bytes:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), (39, 57, 131)).save(buf, "PNG")
        return buf.getvalue()
