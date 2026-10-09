import tempfile
from pathlib import Path

from tests.helpers import AppTestCase


class StaticBuild(AppTestCase):
    with_admin = False

    def test_build(self):
        from app.freeze import build_static
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "site"
            build_static(out, base_path="/my-repo", cname="example.eu")
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('http-equiv="Content-Security-Policy"', index)
            self.assertIn("/my-repo/static/css/style.css", index)
            self.assertTrue((out / "projects" / "aws-multi-tier" / "index.html").exists())
            self.assertTrue((out / "404.html").exists())
            self.assertEqual((out / "CNAME").read_text().strip(), "example.eu")
            self.assertFalse((out / "static" / "css" / "admin.css").exists())
            self.assertNotIn("admin", index.lower().replace("administration", ""))
