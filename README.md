# Armin Moasses — personal website

# I share the details in case you are interested to see the engineeing work behind...


[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![CodeQL](../../actions/workflows/codeql.yml/badge.svg)](../../actions/workflows/codeql.yml)
[![Pages](../../actions/workflows/pages.yml/badge.svg)](../../actions/workflows/pages.yml)

A personal portfolio built with Python & Flask:
"binary portrait", sections for DevOps, research and development experience, project
pages with architecture diagrams, publications — and an admin panel (password + 2FA)
to add, edit and remove every piece of content without touching code.

**One codebase, two deployments**

| | Version 1 — GitHub Pages | Version 2 — own domain (.eu/.com/.net) |
|---|---|---|
| How | GitHub Actions runs Flask and freezes every page to static HTML | Flask on gunicorn behind Caddy (auto-HTTPS) in Docker |
| Edit content | admin panel on your laptop → commit `content/content.json` | admin panel directly on the live site |
| Attack surface | none (static files) | hardened app, see [SECURITY.md](SECURITY.md) |
| Cost | free | domain + small VPS |

```
app/
  __init__.py      application factory, security headers, error pages
  config.py        environment-based config; refuses insecure production settings
  schema.py        ONE description of all editable content (drives validation + admin forms)
  content.py       load / validate / atomic save / backups of content.json
  security.py      scrypt passwords, TOTP 2FA, CSRF, rate limiting, audit log, CSP
  admin.py         admin panel (login, 2FA, CRUD, media, history, export/import)
  public.py        public pages, sitemap, robots.txt, security.txt
  uploads.py       safe image/PDF upload (re-encoding, size limits, no SVG)
  freeze.py        static site builder for GitHub Pages
  templates/ static/
content/
  content.json     ← all your text (from CV)
  portrait.json    ← generated 0/1 portrait
  uploads/         ← images & CV PDF uploaded in the admin panel
tests/             40+ unit & security tests (python -m unittest)
deploy/            Docker Compose, Caddyfile, server guide
.github/workflows/ CI, CodeQL, GitHub Pages deployment
```

---

## 1. Local Run (localhost)

Requires **Python 3.12+** ([python.org](https://www.python.org/downloads/) — on Windows tick *"Add Python to PATH"*).

**Windows:** double-click `run-local.bat`  **macOS/Linux:** `./run-local.sh`

The first run creates a virtual environment, installs the 3 dependencies, downloads the
font and asks you to create your admin login:

1. choose a username and a passphrase (12+ characters),
2. open an authenticator app on your phone (Aegis, Google/Microsoft Authenticator, 1Password),
   choose **"Enter a setup key"** and type the key shown in the terminal,
3. type the 6-digit code to confirm.

Then open:

- Site: <http://127.0.0.1:5000>
- Admin: <http://127.0.0.1:5000/admin>

Manual equivalent:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   |   source .venv/bin/activate  (macOS/Linux)
pip install -r requirements.txt
python tools/fetch_fonts.py
python manage.py create-admin
python manage.py run
```

## 2. Edit your content (the admin panel)

Sign in at `/admin` (password + 2FA code). Everything on the site is editable:

| Menu | What it controls |
|---|---|
| **Profile** | name, the three role lines, intro, email/phone, LinkedIn/GitHub/Scholar, CV PDF, Google title/description |
| **Home page sections** | the blue cards: title, text, big headline words, numbers, which experience/projects/skills/education appear in each |
| **Experience** | jobs and training; the *category* decides which section shows it |
| **Projects** | each project gets its own page: architecture image, description, results, tech tags, link |
| **Layer diagram** | the Code / Pipeline / Cloud columns |
| **Skills, Education, Certifications, Languages, Publications** | lists, add / edit / delete / reorder (↑ ↓) |
| **Imprint & privacy** | Impressum and Datenschutzerklärung (fill in your postal address before going live) |
| **Media & CV** | upload architecture diagrams (PNG/JPG/WEBP) and your CV (PDF) |
| **History / undo** | every save keeps a backup — restore any earlier version in one click |
| **Password**, **Audit log** | change password; see every sign-in and change |

Multi-line fields use simple formats shown under each field, e.g. numbers:
`9 | stage Jenkins pipeline | Git → infrastructure → deploy`.

> Prefer a text editor? `content/content.json` can also be edited directly; run
> `python manage.py check` afterwards to validate it.

**Architecture diagrams:** draw them in [draw.io](https://app.diagrams.net) or Excalidraw, export as
**PNG** (transparent background, light lines look best on the navy cards), upload under *Media*,
then pick the image in the project. SVG uploads are blocked on purpose (security).

**New photo for the 0/1 portrait:** make a PNG with a transparent background (e.g. remove.bg), then
```bash
pip install -r requirements-tools.txt
python tools/make_portrait.py my-photo.png
```

## 3. Version 1 — publish free on GitHub Pages

1. Create a GitHub repository (e.g. `moasses.github.io` for the address `https://moasses.github.io`,
   or any name → `https://moasses.github.io/<name>`).
2. Push this project:
   ```bash
   git init && git add . && git commit -m "Personal website (Flask)"
   git branch -M main
   git remote add origin https://github.com/moasses/moasses.github.io.git
   git push -u origin main
   ```
3. Repository → **Settings → Pages → Source: GitHub Actions**.
4. The *Deploy to GitHub Pages* workflow runs the tests, builds the site with Flask and publishes it.

**Updating:** edit in your local admin panel → `git add content && git commit -m "Update content" && git push`.

**Custom domain on GitHub Pages:** add repository variable `CUSTOM_DOMAIN` (Settings → Secrets and
variables → Actions → Variables), point your domain's DNS at GitHub Pages
([guide](https://docs.github.com/pages/configuring-a-custom-domain-for-your-github-pages-site)) and tick *Enforce HTTPS*.

Build locally to preview exactly what GitHub publishes: `python manage.py build` → `build/`
(serve it with `python -m http.server -d build`).

## 4. Version 2 — your own domain with the live admin panel

See **[deploy/SERVER.md](deploy/SERVER.md)** — a step-by-step guide: EU VPS, server hardening,
`docker compose up -d --build`, automatic HTTPS. Works the same for `.eu`, `.com` or `.net`.

## 5. Development

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t . -v   # tests
bandit -r app -ll                               # static security analysis
pip-audit -r requirements.txt                   # known-vulnerability scan
```

Security design: **[SECURITY.md](SECURITY.md)**.

## License

Code: MIT (see `LICENSE`). Content (texts, portrait, CV) © Armin Moasses — all rights reserved.
