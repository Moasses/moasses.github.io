"""Security building blocks - deliberately written with the Python standard
library only, so there are almost no third-party packages that could be
compromised (supply-chain attacks are a major real-world risk).

* Passwords: scrypt (memory-hard KDF, RFC 7914) with a random salt per hash.
* Two-factor auth: TOTP (RFC 6238, compatible with Google Authenticator,
  Aegis, 1Password …) with replay protection.
* CSRF: per-session random token, compared in constant time, plus an
  Origin/Referer check.
* Brute-force protection: persistent per-IP and per-account rate limits
  (SQLite, shared by all server worker processes).
* Audit log: every admin action is written to an append-only log.
* HTTP security headers: strict CSP with Trusted Types, HSTS, no framing,
  no MIME sniffing, no referrer leaks, all browser features disabled.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import struct
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

# ======================================================== password hashing

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 15, 8, 1, 64
SCRYPT_MAXMEM = 128 * 1024 * 1024
MIN_PASSWORD_LEN = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                        p=SCRYPT_P, dklen=SCRYPT_LEN, maxmem=SCRYPT_MAXMEM)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = encoded.split("$")
        if algo != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r),
                            p=int(p), dklen=len(expected), maxmem=SCRYPT_MAXMEM)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


# A real hash of a random password: used when the username is wrong so that a
# failed login takes exactly as long either way (no username enumeration).
_DUMMY_HASH: str | None = None


def dummy_verify(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _DUMMY_HASH)


def password_problems(password: str, username: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LEN:
        problems.append(f"at least {MIN_PASSWORD_LEN} characters")
    if len(password) > 256:
        problems.append("at most 256 characters")
    if len(set(password)) < 6:
        problems.append("more variety of characters")
    if username and username.lower() in password.lower():
        problems.append("must not contain the username")
    if password.lower() in {"password1234", "123456789012", "qwertyuiopas", "adminadmin12"}:
        problems.append("is a well-known password")
    return problems


# ======================================================================= TOTP

TOTP_STEP, TOTP_DIGITS = 30, 6


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** TOTP_DIGITS
    return str(code).zfill(TOTP_DIGITS)


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(secret_b32, int((at or time.time()) // TOTP_STEP))


def verify_totp(secret_b32: str, code: str, last_counter: int, at: float | None = None) -> int | None:
    """Return the matched time-step counter, or None.

    Accepts the previous/current/next 30-second window (clock drift) but never
    a counter that was already used - a stolen code cannot be replayed.
    """
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != TOTP_DIGITS:
        return None
    now = int((at or time.time()) // TOTP_STEP)
    for counter in (now - 1, now, now + 1):
        if counter > last_counter and hmac.compare_digest(_hotp(secret_b32, counter), code):
            return counter
    return None


def totp_uri(secret_b32: str, account: str, issuer: str) -> str:
    return "otpauth://totp/{}:{}?secret={}&issuer={}&digits=6&period=30".format(
        quote(issuer), quote(account), secret_b32, quote(issuer))


# ============================================================ admin account

class AdminAccount:
    """The single admin account, stored in instance/admin.json (never in git)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".admin-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def create(self, username: str, password: str, totp_secret: str) -> None:
        self.save({
            "username": username,
            "password": hash_password(password),
            "totp_secret": totp_secret,
            "totp_last_counter": 0,
            "session_epoch": secrets.token_hex(8),
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    def update(self, **changes: Any) -> None:
        data = self.load()
        data.update(changes)
        self.save(data)

    def bump_epoch(self) -> None:
        """Invalidate every existing admin session (logout everywhere)."""
        self.update(session_epoch=secrets.token_hex(8))


# ============================================================ rate limiting

class RateLimiter:
    """Sliding-window counters in SQLite, safe across processes."""

    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        with closing(self._conn()) as c:
            c.execute("CREATE TABLE IF NOT EXISTS hits (k TEXT NOT NULL, ts REAL NOT NULL)")
            c.execute("CREATE INDEX IF NOT EXISTS hits_k ON hits (k, ts)")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def count(self, key: str, window: int) -> int:
        with closing(self._conn()) as c:
            return c.execute("SELECT COUNT(*) FROM hits WHERE k=? AND ts>?",
                             (key, time.time() - window)).fetchone()[0]

    def hit(self, key: str) -> None:
        now = time.time()
        with closing(self._conn()) as c:
            c.execute("INSERT INTO hits (k, ts) VALUES (?, ?)", (key, now))
            c.execute("DELETE FROM hits WHERE ts < ?", (now - 86400,))

    def blocked(self, key: str, limit: int, window: int) -> bool:
        return self.count(key, window) >= limit

    def clear(self, key: str) -> None:
        with closing(self._conn()) as c:
            c.execute("DELETE FROM hits WHERE k=?", (key,))


# ================================================================ audit log

class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def write(self, action: str, ip: str, detail: str = "", ok: bool = True) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "ip": ip, "action": action, "ok": ok, "detail": detail[:300]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def tail(self, n: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for ln in reversed(lines):
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out


# ===================================================================== CSRF

CSRF_FIELD = "csrf_token"


def csrf_token(session: Any) -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok


def csrf_valid(session: Any, submitted: str | None) -> bool:
    expected = session.get("_csrf")
    return bool(expected and submitted) and hmac.compare_digest(str(expected), str(submitted))


def same_origin(request: Any) -> bool:
    """The request must come from our own pages (defence in depth for CSRF)."""
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return False
    parts = urlsplit(source)
    return parts.netloc == request.host and parts.scheme in ("http", "https")


# ================================================================== headers

PUBLIC_CSP = "; ".join((
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'none'",
    "manifest-src 'self'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "require-trusted-types-for 'script'",
    "trusted-types 'none'",
))

ADMIN_CSP = "; ".join((
    "default-src 'none'",
    "script-src 'none'",            # the admin panel runs no JavaScript at all
    "style-src 'self'",
    "img-src 'self'",
    "font-src 'self'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
))

UPLOAD_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"

PERMISSIONS_POLICY = ", ".join(f"{f}=()" for f in (
    "accelerometer", "autoplay", "camera", "clipboard-read", "clipboard-write", "display-capture",
    "encrypted-media", "fullscreen", "geolocation", "gyroscope", "hid", "idle-detection",
    "magnetometer", "microphone", "midi", "payment", "picture-in-picture",
    "publickey-credentials-get", "screen-wake-lock", "serial", "usb", "xr-spatial-tracking",
    "interest-cohort", "browsing-topics"))


def apply_security_headers(response: Any, *, kind: str, https: bool) -> Any:
    h = response.headers
    if kind == "upload":
        h["Content-Security-Policy"] = UPLOAD_CSP
    elif kind == "pdf":
        pass  # browsers' built-in PDF viewers break under a sandbox CSP; PDFs are admin-uploaded only
    elif kind == "admin":
        h["Content-Security-Policy"] = ADMIN_CSP + ("; upgrade-insecure-requests" if https else "")
    else:
        h["Content-Security-Policy"] = PUBLIC_CSP + ("; upgrade-insecure-requests" if https else "")
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    # admin: "same-origin" keeps URLs private but still lets the browser send the Origin
    # header that the CSRF check relies on ("no-referrer" would turn it into "null")
    h["Referrer-Policy"] = "same-origin" if kind == "admin" else "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = PERMISSIONS_POLICY
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    h["Cross-Origin-Resource-Policy"] = "same-origin"
    h["Cross-Origin-Embedder-Policy"] = "require-corp"
    h["X-Permitted-Cross-Domain-Policies"] = "none"
    h["Origin-Agent-Cluster"] = "?1"
    if https:
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if kind == "admin":
        h["Cache-Control"] = "no-store"
        h["X-Robots-Tag"] = "noindex, nofollow"
    h.pop("Server", None)
    return response
