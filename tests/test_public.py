from tests.helpers import AppTestCase


class PublicPages(AppTestCase):
    def test_pages_render(self):
        for path in ("/", "/publications/", "/projects/aws-multi-tier/", "/imprint/", "/privacy/",
                     "/robots.txt", "/sitemap.xml", "/.well-known/security.txt", "/healthz"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_cv_content_present(self):
        html = self.client.get("/").get_data(as_text=True)
        for text in ("Armin", "Moasses", "OptiFaaS", "Technische Universität Berlin", "Terraform"):
            self.assertIn(text, html)

    def test_unknown_pages_404(self):
        self.assertEqual(self.client.get("/projects/nope/").status_code, 404)
        self.assertEqual(self.client.get("/nope").status_code, 404)

    def test_security_headers(self):
        r = self.client.get("/")
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("require-trusted-types-for 'script'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertIn("camera=()", r.headers["Permissions-Policy"])
        self.assertEqual(r.headers["Cross-Origin-Opener-Policy"], "same-origin")

    def test_visitors_get_no_cookies(self):
        for path in ("/", "/publications/", "/projects/aws-multi-tier/"):
            self.assertNotIn("Set-Cookie", self.client.get(path).headers)

    def test_no_inline_scripts_or_styles(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn(" style=", html)
        self.assertNotIn("onclick", html.lower())
        import re
        for tag in re.findall(r"<script[^>]*>", html):
            self.assertTrue('src="' in tag or 'type="application/json"' in tag, tag)

    def test_upload_route_rejects_traversal_and_unknown_names(self):
        for name in ("..%2Fcontent.json", "content.json", "x.svg", "abc.png", "%2e%2e%2fadmin.json"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(f"/uploads/{name}").status_code, 404)

    def test_phone_hidden_by_default(self):
        self.assertNotIn("6117212", self.client.get("/").get_data(as_text=True))

    def test_admin_link_not_exposed(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn(self.admin + "/", html)
