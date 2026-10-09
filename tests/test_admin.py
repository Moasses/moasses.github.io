import io
import os
import unittest

from tests.helpers import PASSWORD, TOTP_SECRET, AppTestCase


class Auth(AppTestCase):
    def test_admin_requires_login(self):
        for path in ("/", "/c/projects", "/media", "/history", "/export", "/audit"):
            r = self.client.get(self.admin + path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/login", r.headers["Location"])

    def test_post_without_csrf_rejected(self):
        r = self.client.post(f"{self.admin}/login", data={"username": "armin", "password": PASSWORD},
                             headers=self.ORIGIN)
        self.assertEqual(r.status_code, 400)

    def test_post_from_other_origin_rejected(self):
        token = self.csrf(f"{self.admin}/login")
        r = self.client.post(f"{self.admin}/login", headers={"Origin": "https://evil.example"},
                             data={"username": "armin", "password": PASSWORD, "csrf_token": token})
        self.assertEqual(r.status_code, 400)

    def test_password_alone_is_not_enough(self):
        r = self.post(f"{self.admin}/login", {"username": "armin", "password": PASSWORD})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(f"{self.admin}/").status_code, 302)   # still needs 2FA
        r = self.post(f"{self.admin}/login/2fa", {"code": "000000"})
        self.assertEqual(r.status_code, 401)

    def test_full_login_and_session_cookie_flags(self):
        self.login()
        self.assertEqual(self.client.get(f"{self.admin}/").status_code, 200)

    def test_bruteforce_is_rate_limited(self):
        for _ in range(5):
            r = self.post(f"{self.admin}/login", {"username": "armin", "password": "wrong-password-x"})
            self.assertEqual(r.status_code, 401)
        r = self.post(f"{self.admin}/login", {"username": "armin", "password": PASSWORD})
        self.assertEqual(r.status_code, 429)        # even the right password is refused now

    def test_wrong_username_same_message(self):
        a = self.post(f"{self.admin}/login", {"username": "nobody", "password": "x" * 12}).get_data(as_text=True)
        b = self.post(f"{self.admin}/login", {"username": "armin", "password": "x" * 12}).get_data(as_text=True)
        self.assertIn("Invalid username or password", a)
        self.assertIn("Invalid username or password", b)

    def test_totp_code_cannot_be_replayed(self):
        from app.security import totp_now
        code = totp_now(TOTP_SECRET)
        self.post(f"{self.admin}/login", {"username": "armin", "password": PASSWORD})
        self.assertEqual(self.post(f"{self.admin}/login/2fa", {"code": code}).status_code, 302)
        self.post(f"{self.admin}/logout", token_from=f"{self.admin}/")
        self.post(f"{self.admin}/login", {"username": "armin", "password": PASSWORD})
        self.assertEqual(self.post(f"{self.admin}/login/2fa", {"code": code}).status_code, 401)

    def test_logout_revokes_old_cookie(self):
        self.login()
        cookie = self.client.get_cookie(self.app.config["SESSION_COOKIE_NAME"]).value
        self.post(f"{self.admin}/logout", token_from=f"{self.admin}/")
        thief = self.app.test_client()
        thief.set_cookie(self.app.config["SESSION_COOKIE_NAME"], cookie)
        self.assertEqual(thief.get(f"{self.admin}/").status_code, 302)


class Editing(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_create_edit_delete_project(self):
        base = f"{self.admin}/c/projects"
        r = self.post(f"{base}/new", {"title": "Kubernetes Homelab", "slug": "", "year": "2026",
                                      "summary": "k3s cluster", "tags": "k3s\nArgo CD"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/projects/kubernetes-homelab/").status_code, 200)
        item = next(p for p in self.app.extensions["content"].get()["projects"] if p["slug"] == "kubernetes-homelab")
        r = self.post(f"{base}/{item['id']}", {"title": "Kubernetes Homelab v2", "slug": "kubernetes-homelab"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("Kubernetes Homelab v2", self.client.get("/").get_data(as_text=True))
        r = self.post(f"{base}/{item['id']}/delete")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/projects/kubernetes-homelab/").status_code, 404)

    def test_javascript_url_rejected_by_form(self):
        r = self.post(f"{self.admin}/c/projects/new", {"title": "X", "slug": "x", "link": "javascript:alert(1)"})
        self.assertEqual(r.status_code, 422)

    def test_profile_edit(self):
        values = {"first_name": "Armin", "last_name": "Moasses", "roles": "A Cloud Engineer,",
                  "email": "armin.moasses@gmail.com", "footer": "©"}
        r = self.post(f"{self.admin}/c/profile/edit", values)
        self.assertEqual(r.status_code, 302)
        self.assertIn("A Cloud Engineer,", self.client.get("/").get_data(as_text=True))

    def test_upload_rules(self):
        url = f"{self.admin}/media/upload"
        svg = (io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'), "x.svg")
        fake = (io.BytesIO(b"<?php system($_GET['c']); ?>"), "shell.png")
        good = (io.BytesIO(self.png_bytes()), "diagram.png")
        uploads = self.app.extensions["content"].uploads
        self.post(url, {"file": svg}, token_from=f"{self.admin}/media", content_type="multipart/form-data")
        self.post(url, {"file": fake}, token_from=f"{self.admin}/media", content_type="multipart/form-data")
        self.assertEqual(list(uploads.iterdir()), [])
        self.post(url, {"file": good}, token_from=f"{self.admin}/media", content_type="multipart/form-data")
        files = list(uploads.iterdir())
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.endswith(".webp"))          # re-encoded, random name
        r = self.client.get(f"/uploads/{files[0].name}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("sandbox", r.headers["Content-Security-Policy"])
        r.close()

    def test_admin_pages_have_strict_headers(self):
        r = self.client.get(f"{self.admin}/")
        self.assertIn("script-src 'none'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_every_admin_page_renders(self):
        from app.schema import ALL
        for path in ["/", "/media", "/history", "/account", "/audit"] + [f"/c/{c.key}" for c in ALL]:
            with self.subTest(path=path):
                self.assertIn(self.client.get(self.admin + path, follow_redirects=True).status_code, (200,))


class IpAllowList(AppTestCase):
    extra_env = {"ADMIN_ALLOWED_IPS": "10.0.0.0/8"}

    def test_other_ips_get_404(self):
        self.assertEqual(self.client.get(f"{self.admin}/login").status_code, 404)


class StaticExportHasNoAdmin(AppTestCase):
    env = "export"

    def test_no_admin_routes(self):
        self.assertFalse(self.app.config["ADMIN_ENABLED"])
        self.assertEqual(self.client.get("/admin/login").status_code, 404)


class ProductionConfig(unittest.TestCase):
    def _cfg(self, **env):
        from app.config import ConfigError, build_config
        old = dict(os.environ)
        os.environ.update(env)
        try:
            return build_config("production")
        except ConfigError as e:
            return e
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_refuses_weak_setups(self):
        from app.config import ConfigError
        self.assertIsInstance(self._cfg(SECRET_KEY="short"), ConfigError)
        self.assertIsInstance(self._cfg(SECRET_KEY="x" * 40, ADMIN_PATH="/admin", SITE_URL="https://a.eu"), ConfigError)
        self.assertIsInstance(self._cfg(SECRET_KEY="x" * 40, ADMIN_PATH="/my-panel-9", SITE_URL="http://a.eu"), ConfigError)

    def test_good_setup(self):
        cfg = self._cfg(SECRET_KEY="x" * 40, ADMIN_PATH="/my-panel-9", SITE_URL="https://a.eu")
        self.assertIsInstance(cfg, dict)
        self.assertTrue(cfg["SESSION_COOKIE_SECURE"])
        self.assertEqual(cfg["SESSION_COOKIE_NAME"], "__Host-admin")
        self.assertFalse(cfg["DEBUG"])
