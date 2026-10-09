"""Build the static version of the site (for GitHub Pages or any static host).

The exact same Flask app and templates render every public page once; the
HTML is written to disk together with the static assets. The admin panel is
not part of the build at all, so the static site has no server-side attack
surface whatsoever.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import create_app
from .content import UPLOAD_NAME_RE


def build_static(out_dir: Path, base_path: str = "", cname: str = "") -> list[str]:
    base_path = "/" + base_path.strip("/") if base_path.strip("/") else ""
    app = create_app("export")
    store = app.extensions["content"]
    c = store.get()

    pages = ["/", "/publications/", "/robots.txt", "/sitemap.xml", "/.well-known/security.txt"]
    pages += [f"/projects/{p['slug']}/" for p in c["projects"]]
    if c["legal"]["show_imprint"]:
        pages += ["/imprint/", "/privacy/"]

    out = Path(out_dir).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    client = app.test_client()
    base_url = f"http://localhost{base_path}/"
    written = []
    for path in pages:
        resp = client.get(path, base_url=base_url)
        if resp.status_code != 200:
            raise RuntimeError(f"{path} returned HTTP {resp.status_code}")
        target = out / path.lstrip("/")
        if path.endswith("/"):
            target = target / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resp.data)
        written.append(path)

    resp = client.get("/__not-found__/", base_url=base_url)
    (out / "404.html").write_bytes(resp.data)

    shutil.copytree(app.static_folder, out / "static",  # type: ignore[arg-type]
                    ignore=shutil.ignore_patterns("admin.css"))
    (out / "uploads").mkdir()
    for f in store.uploads.iterdir():
        if f.is_file() and UPLOAD_NAME_RE.match(f.name):
            shutil.copy2(f, out / "uploads" / f.name)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    if cname:
        (out / "CNAME").write_text(cname.strip() + "\n", encoding="utf-8")
    return written
