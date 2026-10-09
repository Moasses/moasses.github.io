"""Armin Moasses - personal website (Flask).

`create_app()` is the application factory used by the dev server, gunicorn
(production), the static site builder and the test-suite.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Flask, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import build_config
from .content import ContentStore
from .security import PUBLIC_CSP, apply_security_headers

__version__ = "1.0.0"


def create_app(env: str | None = None, overrides: dict[str, Any] | None = None) -> Flask:
    cfg = build_config(env)
    if overrides:
        cfg.update(overrides)

    app = Flask(__name__, instance_path=str(cfg["INSTANCE_DIR"]), instance_relative_config=False)
    app.config.update(cfg)
    app.json.sort_keys = False
    app.jinja_env.autoescape = True          # explicit: every value is HTML-escaped
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    if app.config["TRUST_PROXY"]:
        # only trust X-Forwarded-* from the configured number of reverse proxies
        n = app.config["TRUST_PROXY"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)  # type: ignore[method-assign]

    store = ContentStore(app.config["CONTENT_DIR"], app.static_folder)  # type: ignore[arg-type]
    store.get()                               # fail fast if content.json is invalid
    app.extensions["content"] = store

    from .public import bp as public_bp
    app.register_blueprint(public_bp)

    if app.config["ADMIN_ENABLED"]:
        from .admin import bp as admin_bp, init_admin
        init_admin(app)
        app.register_blueprint(admin_bp, url_prefix=app.config["ADMIN_PATH"])

    from .cli import register_cli
    register_cli(app)

    # ------------------------------------------------------------ templating
    def media_url(ref: str) -> str:
        if not ref:
            return ""
        kind, _, name = ref.partition(":")
        if kind == "static":
            return url_for("static", filename=name)
        if kind == "uploads":
            return url_for("public.upload", name=name)
        return ""

    def link(url: str) -> str:
        """Site-relative links (/…) follow the deployment base path (GitHub project pages)."""
        if url.startswith("/") and not url.startswith("//"):
            return request.script_root + url
        return url

    @app.context_processor
    def inject() -> dict[str, Any]:
        return {
            "content": store.get(),
            "media_url": media_url,
            "link": link,
            "year": datetime.now(timezone.utc).year,
            "static_export": app.config["STATIC_EXPORT"],
            "export_csp": PUBLIC_CSP.replace("; frame-ancestors 'none'", ""),
            "site_url": app.config["SITE_URL"],
        }

    @app.template_filter("paragraphs")
    def paragraphs(text: str) -> list[str]:
        return [p.strip() for p in (text or "").split("\n\n") if p.strip()]

    # --------------------------------------------------------------- headers
    @app.after_request
    def headers(response):  # type: ignore[no-untyped-def]
        bp = request.blueprints[0] if request.blueprints else ""
        if request.endpoint == "public.upload":
            kind = "pdf" if response.mimetype == "application/pdf" else "upload"
        else:
            kind = "admin" if bp == "admin" else "public"
        return apply_security_headers(response, kind=kind, https=app.config["HTTPS"])

    # ---------------------------------------------------------------- errors
    def error_page(code: int, title: str, text: str):  # type: ignore[no-untyped-def]
        return render_template("error.html", code=code, title=title, text=text), code

    app.register_error_handler(400, lambda e: error_page(400, "Bad request", "The request could not be understood."))
    app.register_error_handler(403, lambda e: error_page(403, "Forbidden", "You do not have access to this page."))
    app.register_error_handler(404, lambda e: error_page(404, "Page not found", "This page does not exist."))
    app.register_error_handler(405, lambda e: error_page(405, "Not allowed", "This action is not allowed here."))
    app.register_error_handler(413, lambda e: error_page(413, "Too large", "The upload is too large."))
    app.register_error_handler(429, lambda e: error_page(429, "Slow down", "Too many attempts. Please wait and try again later."))
    app.register_error_handler(500, lambda e: error_page(500, "Server error", "Something went wrong."))
    return app
