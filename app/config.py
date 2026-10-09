"""Configuration from environment variables (see .env.example).

APP_ENV
  development  local machine, admin panel at /admin, plain http://localhost
  production   real server behind HTTPS reverse proxy; strict checks on start-up
  export       used by `python manage.py build` to produce the static GitHub Pages
               site; the admin panel is not even registered.
"""
from __future__ import annotations

import ipaddress
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _secret_key(instance_dir: Path) -> str:
    """Development: create a random key once and keep it in instance/ (not in git)."""
    path = instance_dir / "secret_key"
    if not path.exists():
        instance_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        os.chmod(path, 0o600)
    return path.read_text(encoding="utf-8").strip()


def _networks(value: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets = []
    for part in filter(None, (p.strip() for p in value.split(","))):
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError as exc:
            raise ConfigError(f"ADMIN_ALLOWED_IPS: '{part}' is not an IP or network") from exc
    return nets


def build_config(env: str | None = None) -> dict:
    env = (env or os.environ.get("APP_ENV", "development")).strip().lower()
    if env not in {"development", "production", "export"}:
        raise ConfigError("APP_ENV must be development, production or export")

    instance_dir = Path(os.environ.get("INSTANCE_DIR", BASE_DIR / "instance")).resolve()
    content_dir = Path(os.environ.get("CONTENT_DIR", BASE_DIR / "content")).resolve()
    production = env == "production"

    cfg: dict = {
        "APP_ENV": env,
        "DEBUG": False,                       # never use the Werkzeug debugger (remote code execution risk)
        "TESTING": False,
        "INSTANCE_DIR": instance_dir,
        "CONTENT_DIR": content_dir,
        "SITE_URL": os.environ.get("SITE_URL", "").rstrip("/"),
        "STATIC_EXPORT": env == "export",
        "ADMIN_ENABLED": env != "export" and os.environ.get("ADMIN_ENABLED", "1") != "0",
        "HTTPS": production,
        "TRUST_PROXY": int(os.environ.get("TRUST_PROXY", "1" if production else "0")),
        "MAX_CONTENT_LENGTH": 12 * 1024 * 1024,      # request size cap (uploads)
        "MAX_FORM_MEMORY_SIZE": 512 * 1024,
        "MAX_FORM_PARTS": 300,
        "TEMPLATES_AUTO_RELOAD": not production,
        "SEND_FILE_MAX_AGE_DEFAULT": timedelta(hours=12) if production else 0,
        "JSON_SORT_KEYS": False,
        # session cookie (used by the admin panel only - visitors get no cookies)
        "SESSION_COOKIE_NAME": "__Host-admin" if production else "admin_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SECURE": production,
        "SESSION_COOKIE_SAMESITE": "Strict",
        "SESSION_COOKIE_PATH": "/",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=8),     # absolute max
        "ADMIN_IDLE_TIMEOUT": int(os.environ.get("ADMIN_IDLE_MINUTES", "30")) * 60,
        "ADMIN_ALLOWED_IPS": _networks(os.environ.get("ADMIN_ALLOWED_IPS", "")),
        "LOGIN_IP_LIMIT": (5, 15 * 60),          # 5 failures per 15 min per IP
        "LOGIN_ACCOUNT_LIMIT": (20, 60 * 60),    # 20 failures per hour in total
    }

    admin_path = os.environ.get("ADMIN_PATH", "/admin").strip()
    if not re.fullmatch(r"/[A-Za-z0-9\-_]{3,64}", admin_path):
        raise ConfigError("ADMIN_PATH must look like /some-private-path (letters, digits, - and _)")
    cfg["ADMIN_PATH"] = admin_path

    if env == "export":
        cfg["SECRET_KEY"] = secrets.token_urlsafe(32)     # never used for anything persistent
    elif production:
        key = os.environ.get("SECRET_KEY", "")
        if len(key) < 32:
            raise ConfigError("Production needs SECRET_KEY with at least 32 random characters "
                              "(generate: python -c \"import secrets;print(secrets.token_urlsafe(48))\")")
        cfg["SECRET_KEY"] = key
        if cfg["ADMIN_ENABLED"] and admin_path == "/admin":
            raise ConfigError("Production: set ADMIN_PATH to a private, hard-to-guess path (not /admin)")
        if not cfg["SITE_URL"].startswith("https://"):
            raise ConfigError("Production: SITE_URL must be your https:// address")
    else:
        cfg["SECRET_KEY"] = os.environ.get("SECRET_KEY") or _secret_key(instance_dir)
    return cfg
