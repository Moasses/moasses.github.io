"""Admin panel: login with password + 2FA, then add / edit / remove all content.

Defence layers (all requests to the admin blueprint):
  1. optional IP allow-list (everyone else gets a plain 404)
  2. secret URL prefix (ADMIN_PATH) - keeps bots and scanners away
  3. password (scrypt) + TOTP 2FA, rate-limited per IP and per account
  4. short-lived, HttpOnly, SameSite=Strict, Secure session cookie that is
     revoked server-side on logout / password change (session epoch)
  5. CSRF token + Origin check on every POST
  6. every input validated against the schema; output auto-escaped
  7. audit log of every action
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import time
from typing import Any

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, session, url_for)

from .content import ContentStore, ValidationError, form_to_item, item_to_form, slugify
from .schema import ALL, BY_KEY, Collection, empty_item
from .security import (CSRF_FIELD, AdminAccount, AuditLog, RateLimiter, csrf_token, csrf_valid,
                       dummy_verify, hash_password, password_problems, same_origin, verify_password, verify_totp)
from .uploads import save_upload

bp = Blueprint("admin", __name__, template_folder="templates")

PUBLIC_ENDPOINTS = {"admin.login", "admin.login_2fa"}
PRE_AUTH_SECONDS = 300


# ------------------------------------------------------------------ helpers

def init_admin(app) -> None:  # type: ignore[no-untyped-def]
    inst = app.config["INSTANCE_DIR"]
    inst.mkdir(parents=True, exist_ok=True)
    app.extensions["admin_account"] = AdminAccount(inst / "admin.json")
    app.extensions["rate_limiter"] = RateLimiter(inst / "security.db")
    app.extensions["audit"] = AuditLog(inst / "audit.log")

    @app.context_processor
    def admin_ctx() -> dict[str, Any]:
        if request.blueprints and request.blueprints[0] == "admin":
            return {"csrf_token": csrf_token(session), "csrf_field": CSRF_FIELD, "collections": ALL}
        return {}


def account() -> AdminAccount:
    return current_app.extensions["admin_account"]


def limiter() -> RateLimiter:
    return current_app.extensions["rate_limiter"]


def audit(action: str, detail: str = "", ok: bool = True) -> None:
    current_app.extensions["audit"].write(action, client_ip(), detail, ok)


def store() -> ContentStore:
    return current_app.extensions["content"]


def client_ip() -> str:
    return request.remote_addr or "unknown"


def coll_or_404(key: str) -> Collection:
    coll = BY_KEY.get(key)
    if coll is None:
        abort(404)
    return coll


# ------------------------------------------------------------ request guard

@bp.before_request
def guard():  # type: ignore[no-untyped-def]
    allowed = current_app.config["ADMIN_ALLOWED_IPS"]
    if allowed:
        try:
            ip = ipaddress.ip_address(client_ip())
        except ValueError:
            abort(404)
        if not any(ip in net for net in allowed):
            abort(404)

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not csrf_valid(session, request.form.get(CSRF_FIELD)) or not same_origin(request):
            audit("csrf_rejected", request.path, ok=False)
            abort(400)

    if request.endpoint in PUBLIC_ENDPOINTS:
        return None

    s = session.get("admin")
    now = time.time()
    if not s or not account().exists():
        return redirect(url_for("admin.login"))
    acct = account().load()
    idle = current_app.config["ADMIN_IDLE_TIMEOUT"]
    absolute = current_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()
    if (s.get("epoch") != acct["session_epoch"] or now - s.get("seen", 0) > idle
            or now - s.get("iat", 0) > absolute):
        session.clear()
        flash("Your session has ended. Please sign in again.")
        return redirect(url_for("admin.login"))
    s["seen"] = now
    session["admin"] = s
    return None


# -------------------------------------------------------------------- login

@bp.route("/login", methods=["GET", "POST"])
def login():  # type: ignore[no-untyped-def]
    if not account().exists():
        return render_template("admin/setup.html")
    ip_limit, ip_window = current_app.config["LOGIN_IP_LIMIT"]
    ac_limit, ac_window = current_app.config["LOGIN_ACCOUNT_LIMIT"]
    ip_key = f"login-ip:{client_ip()}"

    if request.method == "POST":
        if limiter().blocked(ip_key, ip_limit, ip_window) or limiter().blocked("login-account", ac_limit, ac_window):
            audit("login_blocked", "rate limit", ok=False)
            abort(429)
        username = request.form.get("username", "")[:100]
        password = request.form.get("password", "")[:256]
        acct = account().load()
        if hmac.compare_digest(username.encode(), acct["username"].encode()):
            ok = verify_password(password, acct["password"])
        else:
            dummy_verify(password)
            ok = False
        if not ok:
            limiter().hit(ip_key)
            limiter().hit("login-account")
            audit("login_failed", f"user={username[:40]!r}", ok=False)
            flash("Invalid username or password.")
            return render_template("admin/login.html"), 401
        session.clear()
        session["pre"] = {"t": time.time(), "epoch": acct["session_epoch"]}
        return redirect(url_for("admin.login_2fa"))
    return render_template("admin/login.html")


@bp.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():  # type: ignore[no-untyped-def]
    pre = session.get("pre")
    if not pre or time.time() - pre.get("t", 0) > PRE_AUTH_SECONDS or not account().exists():
        session.clear()
        return redirect(url_for("admin.login"))
    ip_limit, ip_window = current_app.config["LOGIN_IP_LIMIT"]
    key = f"totp-ip:{client_ip()}"
    if request.method == "POST":
        if limiter().blocked(key, ip_limit, ip_window):
            audit("2fa_blocked", "rate limit", ok=False)
            session.clear()
            abort(429)
        acct = account().load()
        counter = verify_totp(acct["totp_secret"], request.form.get("code", "")[:12],
                              int(acct.get("totp_last_counter", 0)))
        if counter is None or pre.get("epoch") != acct["session_epoch"]:
            limiter().hit(key)
            audit("2fa_failed", ok=False)
            flash("Invalid code. Use the current 6-digit code from your authenticator app.")
            return render_template("admin/totp.html"), 401
        account().update(totp_last_counter=counter, last_login=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                         last_login_ip=client_ip())
        limiter().clear(key)
        limiter().clear(f"login-ip:{client_ip()}")
        session.clear()                                 # new session (prevents session fixation)
        now = time.time()
        session["admin"] = {"u": acct["username"], "epoch": acct["session_epoch"], "iat": now, "seen": now}
        session.permanent = True
        audit("login_ok")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/totp.html")


@bp.post("/logout")
def logout():  # type: ignore[no-untyped-def]
    account().bump_epoch()                              # revokes this and any stolen cookie
    audit("logout")
    session.clear()
    flash("Signed out.")
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------- dashboard

@bp.get("/")
def dashboard():  # type: ignore[no-untyped-def]
    c = store().get()
    counts = {coll.key: (None if coll.single else len(c[coll.key])) for coll in ALL}
    acct = account().load()
    return render_template("admin/dashboard.html", counts=counts, acct=acct,
                           history=len(store().list_history()), media=len(store().uploaded()))


# -------------------------------------------------------------- collections

@bp.get("/c/<key>")
def collection(key: str):  # type: ignore[no-untyped-def]
    coll = coll_or_404(key)
    if coll.single:
        return redirect(url_for("admin.edit", key=key))
    return render_template("admin/list.html", coll=coll, items=store().get()[key])


def _form_context(coll: Collection) -> dict[str, Any]:
    return {"media_choices": store().media_choices(), "file_choices": store().file_choices()}


def _apply_defaults(coll: Collection, item: dict[str, Any]) -> None:
    for f in coll.fields:
        if f.kind == "slug" and not str(item.get(f.name, "")).strip():
            item[f.name] = slugify(str(item.get(coll.title_field, "")), f.max_len)


@bp.route("/c/<key>/new", methods=["GET", "POST"])
def new(key: str):  # type: ignore[no-untyped-def]
    coll = coll_or_404(key)
    if coll.single:
        abort(404)
    if request.method == "POST":
        item = form_to_item(coll, request.form)
        _apply_defaults(coll, item)
        doc = store().get_copy()
        try:
            clean = store().validate_item(coll, item)
            doc[key].append(clean)
            store().save(doc)
        except ValidationError as e:
            flash(str(e))
            return render_template("admin/form.html", coll=coll, values=request.form, is_new=True,
                                   **_form_context(coll)), 422
        audit("create", f"{key}:{clean['id']}")
        flash(f"Added “{clean[coll.title_field]}”.")
        return redirect(url_for("admin.collection", key=key))
    return render_template("admin/form.html", coll=coll, values=item_to_form(coll, empty_item(coll)),
                           is_new=True, **_form_context(coll))


@bp.route("/c/<key>/edit", methods=["GET", "POST"], defaults={"item_id": None})
@bp.route("/c/<key>/<item_id>", methods=["GET", "POST"])
def edit(key: str, item_id: str | None):  # type: ignore[no-untyped-def]
    coll = coll_or_404(key)
    doc = store().get_copy()
    if coll.single:
        if item_id is not None:
            abort(404)
        current = doc[key]
    else:
        current = next((it for it in doc[key] if it["id"] == item_id), None)
        if current is None:
            abort(404)

    if request.method == "POST":
        item = form_to_item(coll, request.form)
        _apply_defaults(coll, item)
        try:
            if coll.single:
                doc[key] = store().validate_item(coll, item)
            else:
                item["id"] = item_id
                clean = store().validate_item(coll, item)
                doc[key] = [clean if it["id"] == item_id else it for it in doc[key]]
            store().save(doc)
        except ValidationError as e:
            flash(str(e))
            return render_template("admin/form.html", coll=coll, values=request.form, is_new=False,
                                   item_id=item_id, **_form_context(coll)), 422
        audit("update", f"{key}:{item_id or ''}")
        flash("Saved.")
        if coll.single:
            return redirect(url_for("admin.edit", key=key))
        return redirect(url_for("admin.collection", key=key))
    return render_template("admin/form.html", coll=coll, values=item_to_form(coll, current), is_new=False,
                           item_id=item_id, **_form_context(coll))


@bp.route("/c/<key>/<item_id>/delete", methods=["GET", "POST"])
def delete(key: str, item_id: str):  # type: ignore[no-untyped-def]
    coll = coll_or_404(key)
    if coll.single:
        abort(404)
    doc = store().get_copy()
    current = next((it for it in doc[key] if it["id"] == item_id), None)
    if current is None:
        abort(404)
    if request.method == "POST":
        doc[key] = [it for it in doc[key] if it["id"] != item_id]
        try:
            store().save(doc)
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("admin.collection", key=key))
        audit("delete", f"{key}:{item_id}")
        flash(f"Deleted “{current[coll.title_field]}”. (You can undo this under History.)")
        return redirect(url_for("admin.collection", key=key))
    return render_template("admin/confirm.html", coll=coll, item=current, item_id=item_id)


@bp.post("/c/<key>/<item_id>/move")
def move(key: str, item_id: str):  # type: ignore[no-untyped-def]
    coll = coll_or_404(key)
    if coll.single:
        abort(404)
    doc = store().get_copy()
    items = doc[key]
    idx = next((n for n, it in enumerate(items) if it["id"] == item_id), None)
    if idx is None:
        abort(404)
    step = -1 if request.form.get("dir") == "up" else 1
    j = idx + step
    if 0 <= j < len(items):
        items[idx], items[j] = items[j], items[idx]
        store().save(doc)
        audit("move", f"{key}:{item_id}")
    return redirect(url_for("admin.collection", key=key))


# -------------------------------------------------------------------- media

@bp.get("/media")
def media():  # type: ignore[no-untyped-def]
    return render_template("admin/media.html", uploads=store().uploaded(), static=store().static_images(),
                           in_use=store().media_in_use())


@bp.post("/media/upload")
def media_upload():  # type: ignore[no-untyped-def]
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a file first.")
        return redirect(url_for("admin.media"))
    try:
        name = save_upload(f, store().uploads)
    except ValidationError as e:
        audit("upload_rejected", str(e), ok=False)
        flash(str(e))
        return redirect(url_for("admin.media"))
    audit("upload", name)
    flash(f"Uploaded as {name}. You can now choose it in a project or in your profile.")
    return redirect(url_for("admin.media"))


@bp.post("/media/<name>/delete")
def media_delete(name: str):  # type: ignore[no-untyped-def]
    if name not in store().uploaded():
        abort(404)
    if name in store().media_in_use():
        flash("This file is still used. Remove it from the project/profile first.")
        return redirect(url_for("admin.media"))
    (store().uploads / name).unlink(missing_ok=True)
    audit("media_delete", name)
    flash("File deleted.")
    return redirect(url_for("admin.media"))


# ------------------------------------------------------------------ history

@bp.get("/history")
def history():  # type: ignore[no-untyped-def]
    return render_template("admin/history.html", items=store().list_history())


@bp.post("/history/<name>/restore")
def history_restore(name: str):  # type: ignore[no-untyped-def]
    try:
        store().restore(name)
    except (ValidationError, json.JSONDecodeError):
        flash("That backup could not be restored.")
        return redirect(url_for("admin.history"))
    audit("restore", name)
    flash("Backup restored. (The previous state was saved as a new backup.)")
    return redirect(url_for("admin.dashboard"))


@bp.get("/export")
def export():  # type: ignore[no-untyped-def]
    audit("export")
    data = json.dumps(store().get(), indent=2, ensure_ascii=False) + "\n"
    return Response(data, mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=content.json"})


@bp.post("/import")
def import_content():  # type: ignore[no-untyped-def]
    f = request.files.get("file")
    try:
        if not f:
            raise ValidationError("Choose a content.json file.")
        raw = f.stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValidationError("File too large.")
        store().save(json.loads(raw.decode("utf-8")))
    except (ValidationError, UnicodeDecodeError, json.JSONDecodeError) as e:
        audit("import_rejected", str(e)[:200], ok=False)
        flash(f"Import failed: {e}")
        return redirect(url_for("admin.dashboard"))
    audit("import")
    flash("Content imported. (The previous state was saved under History.)")
    return redirect(url_for("admin.dashboard"))


# ------------------------------------------------------------------ account

@bp.route("/account", methods=["GET", "POST"])
def account_page():  # type: ignore[no-untyped-def]
    if request.method == "POST":
        acct = account().load()
        key = f"pwchange-ip:{client_ip()}"
        if limiter().blocked(key, 5, 900):
            abort(429)
        current = request.form.get("current", "")[:256]
        new_pw = request.form.get("new", "")[:300]
        counter = verify_totp(acct["totp_secret"], request.form.get("code", "")[:12],
                              int(acct.get("totp_last_counter", 0)))
        if not verify_password(current, acct["password"]) or counter is None:
            limiter().hit(key)
            audit("password_change_failed", ok=False)
            flash("Current password or 2FA code is wrong.")
            return render_template("admin/account.html", acct=acct), 401
        problems = password_problems(new_pw, acct["username"])
        if new_pw != request.form.get("confirm", ""):
            problems.append("both new passwords must match")
        if problems:
            flash("New password needs: " + "; ".join(problems) + ".")
            return render_template("admin/account.html", acct=acct), 422
        account().update(password=hash_password(new_pw), totp_last_counter=counter)
        account().bump_epoch()
        audit("password_changed")
        session.clear()
        flash("Password changed. Please sign in again.")
        return redirect(url_for("admin.login"))
    return render_template("admin/account.html", acct=account().load())


@bp.get("/audit")
def audit_page():  # type: ignore[no-untyped-def]
    return render_template("admin/audit.html", entries=current_app.extensions["audit"].tail(300))
