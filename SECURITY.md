## Architecture & attack surface

| Version | What runs on the internet | Server-side code exposed |
|---|---|---|
| **GitHub Pages** | plain HTML/CSS/JS files built by Flask in CI | **none** (no admin, no database, no forms) |
| **.eu server** | Caddy → gunicorn → Flask | public pages + admin panel behind 2FA |

There is **no database server** (content is one validated JSON file) and **no
user-supplied HTML** anywhere, which rules out SQL injection and stored XSS by design.

## Controls

**Input & output**
- Every field typed in the admin panel is validated against one schema (`app/schema.py`): type, length, allowed characters.
- Links: only `https://`, `http://`, `mailto:` and site-relative `/…`. `javascript:`, `data:`, `//evil.com` etc. are rejected.
- Control and bidi-override characters are stripped (no disguised text).
- Jinja2 auto-escaping on every template; no `|safe` on content.
- Writes are atomic and every change keeps a timestamped backup (restorable in the admin panel).

**Browser hardening (HTTP headers)**
- Strict Content-Security-Policy: `default-src 'none'`, scripts and styles only from the site itself, **no inline scripts/styles**, **Trusted Types enforced**, `frame-ancestors 'none'`, `base-uri 'none'`, `object-src 'none'`.
- The admin panel runs **zero JavaScript** (`script-src 'none'`).
- HSTS (2 years), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, strict `Referrer-Policy`, `Permissions-Policy` disabling camera/mic/geolocation/…, COOP/CORP/COEP isolation.
- Visitors receive **no cookies**, no analytics, no third-party requests (fonts are self-hosted) → GDPR-friendly, nothing to steal.

**Authentication (admin)**
- Admin account can only be created from the server command line (`manage.py create-admin`) — there is no sign-up page.
- Passwords hashed with **scrypt** (memory-hard, random salt), minimum 12 characters.
- **Mandatory TOTP two-factor authentication**, codes cannot be replayed.
- Same response and timing for wrong username vs. wrong password (no user enumeration).
- Brute-force limits: 5 failures / 15 min per IP, 20 / hour in total (SQLite-backed, shared across workers).
- Secret admin URL (`ADMIN_PATH`) and optional IP allow-list (others get a 404).

**Sessions & CSRF**
- Cookie only for the admin: `__Host-` prefix, `Secure`, `HttpOnly`, `SameSite=Strict`.
- 30-minute idle timeout, 8-hour absolute limit, new session after login (no session fixation).
- Logout and password change **revoke all sessions server-side** (session epoch) — a stolen cookie stops working.
- CSRF token on every form (constant-time compare) **plus** Origin/Referer check.

**Uploads**
- Only PNG/JPG/WEBP images and PDF. **SVG is refused** (it can contain JavaScript).
- Images are fully decoded and re-encoded (removes EXIF/GPS and hidden payloads), size and pixel limits (decompression-bomb guard).
- Random file names; served from a strict whitelist route with `CSP: sandbox` and `nosniff`.

**Infrastructure (.eu server)**
- Caddy: automatic TLS certificates, HTTP/2+3, request size limit, scanner probes answered at the edge.
- App container: non-root user, **read-only filesystem**, all Linux capabilities dropped, `no-new-privileges`, memory/PID limits, code files not writable.
- App container sits on an **internal Docker network with no internet access** (blocks data exfiltration / SSRF).
- Production refuses to start with a weak `SECRET_KEY`, the default `/admin` path or a non-HTTPS URL. The Werkzeug debugger is never enabled.

**Supply chain & CI**
- Only 3 direct runtime libraries (Flask, Pillow, gunicorn); security primitives (scrypt, TOTP, CSRF, rate limiting) use the Python standard library.
- Pinned versions + Dependabot; `pip-audit`, Bandit and CodeQL run on every push; 40+ automated security tests (`tests/`).

## Your part (operations)

- Use a long, unique passphrase and keep the 2FA key backed up (Aegis/1Password export).
- Keep the server patched (`unattended-upgrades`), SSH with keys only, firewall on 22/80/443.
- Merge Dependabot pull requests; rebuild the container (`docker compose up -d --build`) monthly.
- Back up the `site-data` volume (content + uploads).
