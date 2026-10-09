"""Public pages."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, Response, abort, current_app, render_template, send_from_directory, url_for

from .content import UPLOAD_NAME_RE, ContentStore
from .schema import PUBLICATION_TYPES

bp = Blueprint("public", __name__)


def store() -> ContentStore:
    return current_app.extensions["content"]


@bp.get("/")
def index():  # type: ignore[no-untyped-def]
    c = store().get()
    by_cat: dict[str, list] = {}
    for e in c["experience"]:
        by_cat.setdefault(e["category"], []).append(e)
    return render_template("index.html", experience_by_cat=by_cat, portrait=store().portrait())


@bp.get("/publications/")
def publications():  # type: ignore[no-untyped-def]
    c = store().get()
    items = sorted(c["publications"], key=lambda p: -p["year"])
    labels = dict(PUBLICATION_TYPES)
    counts: dict[str, int] = {}
    for p in items:
        counts[p["type"]] = counts.get(p["type"], 0) + 1
    years: list[tuple[int, list]] = []
    for p in items:
        if not years or years[-1][0] != p["year"]:
            years.append((p["year"], []))
        years[-1][1].append(p)
    return render_template("publications.html", years=years, counts=counts, labels=labels,
                           total=len(items), portrait=store().portrait())


@bp.get("/projects/<slug>/")
def project(slug: str):  # type: ignore[no-untyped-def]
    c = store().get()
    projects = c["projects"]
    for n, p in enumerate(projects):
        if p["slug"] == slug:
            prev_p = projects[n - 1] if n > 0 else None
            next_p = projects[n + 1] if n + 1 < len(projects) else None
            return render_template("project.html", p=p, prev_p=prev_p, next_p=next_p,
                                   portrait=store().portrait())
    abort(404)


@bp.get("/imprint/")
def imprint():  # type: ignore[no-untyped-def]
    if not store().get()["legal"]["show_imprint"]:
        abort(404)
    return render_template("legal.html", title="Imprint", key="imprint", portrait=store().portrait())


@bp.get("/privacy/")
def privacy():  # type: ignore[no-untyped-def]
    if not store().get()["legal"]["show_imprint"]:
        abort(404)
    return render_template("legal.html", title="Privacy", key="privacy", portrait=store().portrait())


@bp.get("/uploads/<name>")
def upload(name: str):  # type: ignore[no-untyped-def]
    # strict whitelist: only names the upload code itself generated
    if not UPLOAD_NAME_RE.match(name):
        abort(404)
    resp = send_from_directory(store().uploads, name, max_age=86400)
    resp.headers["Content-Disposition"] = "inline"
    return resp


@bp.get("/robots.txt")
def robots():  # type: ignore[no-untyped-def]
    lines = ["User-agent: *", "Allow: /"]
    site = current_app.config["SITE_URL"]
    if site:
        lines.append(f"Sitemap: {site}{url_for('public.sitemap')}")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():  # type: ignore[no-untyped-def]
    site = current_app.config["SITE_URL"]
    c = store().get()
    paths = [url_for("public.index"), url_for("public.publications")]
    paths += [url_for("public.project", slug=p["slug"]) for p in c["projects"]]
    return Response(render_template("sitemap.xml", site=site, paths=paths), mimetype="application/xml")


@bp.get("/.well-known/security.txt")
def security_txt():  # type: ignore[no-untyped-def]
    c = store().get()
    expires = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1, month=1, day=1)
    body = (f"Contact: mailto:{c['profile']['email']}\n"
            f"Expires: {expires.strftime('%Y-%m-%dT00:00:00Z')}\n"
            "Preferred-Languages: en, de\n")
    return Response(body, mimetype="text/plain")


@bp.get("/healthz")
def healthz():  # type: ignore[no-untyped-def]
    store().get()
    return Response("ok\n", mimetype="text/plain")
