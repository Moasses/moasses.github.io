import unittest

from app.content import ValidationError, clean_url
from tests.helpers import AppTestCase


class Urls(unittest.TestCase):
    def test_good(self):
        for u in ("https://github.com/moasses", "http://example.com/x?a=1", "mailto:a@b.de",
                  "/publications/", "#projects", ""):
            self.assertEqual(clean_url(u), u)

    def test_bad(self):
        for u in ("javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>", "//evil.com",
                  "vbscript:x", "https://a b.com", "https://user@evil.com", "/../etc/passwd",
                  'https://x.com/"onmouseover=', "\\\\evil", "ftp://x.com"):
            with self.subTest(u=u):
                with self.assertRaises(ValidationError):
                    clean_url(u)


class Store(AppTestCase):
    def store(self):
        return self.app.extensions["content"]

    def test_xss_is_escaped_on_page(self):
        doc = self.store().get_copy()
        doc["profile"]["intro"] = '<script>alert("x")</script><img src=x onerror=alert(1)>'
        self.store().save(doc)
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_control_and_bidi_chars_removed(self):
        doc = self.store().get_copy()
        doc["profile"]["tagline"] = "safe‮text\x00"
        self.store().save(doc)
        self.assertEqual(self.store().get()["profile"]["tagline"], "safetext")

    def test_duplicate_project_slug_rejected(self):
        doc = self.store().get_copy()
        doc["projects"][1]["slug"] = doc["projects"][0]["slug"]
        with self.assertRaises(ValidationError):
            self.store().save(doc)

    def test_media_must_exist(self):
        doc = self.store().get_copy()
        doc["projects"][0]["image"] = "static:../../instance/admin.json"
        with self.assertRaises(ValidationError):
            self.store().save(doc)

    def test_save_creates_backup_and_restore_works(self):
        before = self.store().get()["profile"]["first_name"]
        doc = self.store().get_copy()
        doc["profile"]["first_name"] = "Changed"
        self.store().save(doc)
        backups = self.store().list_history()
        self.assertEqual(len(backups), 1)
        self.store().restore(backups[0])
        self.assertEqual(self.store().get()["profile"]["first_name"], before)

    def test_restore_rejects_bad_names(self):
        with self.assertRaises(ValidationError):
            self.store().restore("../instance/admin.json")
