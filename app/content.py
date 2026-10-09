"""Loading, validating and saving content.json.

Security notes
--------------
- Content is plain data. Templates auto-escape every value, so text typed in the
  admin panel can never become HTML or JavaScript on the page.
- Links are validated against an allow-list of schemes (no `javascript:`,
  `data:`, protocol-relative `//evil.com`, …).
- Media references can only point at files that really exist in the static
  image folder or the uploads folder - never at arbitrary paths.
- Writes are atomic (temp file + rename) and every save keeps a timestamped
  backup, so a bad edit can always be rolled back from the admin panel.
"""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
import tempfile
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .schema import ALL, BY_KEY, Collection, Field

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
UPLOAD_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}   # no SVG uploads (XSS risk)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}$")
ID_RE = re.compile(r"^[a-f0-9]{8}$")
UPLOAD_NAME_RE = re.compile(r"^[a-f0-9]{16}\.(png|jpg|jpeg|webp|pdf)$")
STATIC_IMG_RE = re.compile(r"^img/[A-Za-z0-9_\-/]{1,120}\.(png|jpg|jpeg|webp|svg|gif)$")
HISTORY_RE = re.compile(r"^content-\d{8}-\d{6}-[a-f0-9]{6}\.json$")
MAX_HISTORY = 50


class ValidationError(ValueError):
    """Raised with a message that is safe to show to the admin."""


# ---------------------------------------------------------------- primitives

def _clean(value: Any, max_len: int, multiline: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise ValidationError("Expected text.")
    s = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    # keep ZWNJ/ZWJ (needed for Persian/Kurdish), drop all other control and
    # format characters (incl. bidi overrides) that could disguise content
    allowed = "‌‍" + ("\n\t" if multiline else "")
    s = "".join(ch for ch in s if ch in allowed or (unicodedata.category(ch)[0] != "C"))
    s = s.strip()
    if not multiline:
        s = " ".join(s.split())
    if len(s) > max_len:
        raise ValidationError(f"Too long (max {max_len} characters).")
    return s


def clean_url(value: Any) -> str:
    s = _clean(value, 500)
    if not s:
        return ""
    if any(c in s for c in ' \\<>"\'`'):
        raise ValidationError("Links may not contain spaces, quotes or backslashes.")
    if s.startswith("#"):
        if not re.fullmatch(r"#[A-Za-z0-9\-_]{1,60}", s):
            raise ValidationError("Invalid #anchor link.")
        return s
    if s.startswith("/"):
        if s.startswith("//"):
            raise ValidationError("Protocol-relative links (//…) are not allowed.")
        if not re.fullmatch(r"/[A-Za-z0-9\-_./#?=&%]*", s) or ".." in s:
            raise ValidationError("Invalid site link.")
        return s
    parts = urlsplit(s)
    scheme = parts.scheme.lower()
    if scheme in ("http", "https"):
        if not parts.netloc or "@" in parts.netloc:
            raise ValidationError("Link must look like https://example.com/…")
        return s
    if scheme == "mailto":
        if not EMAIL_RE.match(parts.path):
            raise ValidationError("Invalid mailto: link.")
        return s
    raise ValidationError("Only https://, http://, mailto: and site links (/…) are allowed.")


def clean_email(value: Any) -> str:
    s = _clean(value, 254)
    if s and not EMAIL_RE.match(s):
        raise ValidationError("Invalid email address.")
    return s


def clean_slug(value: Any, max_len: int) -> str:
    s = _clean(value, max_len).lower()
    if not SLUG_RE.match(s):
        raise ValidationError("Use lower-case letters, digits and single dashes only (e.g. my-project).")
    return s


def slugify(text: str, max_len: int = 60) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:max_len].rstrip("-")) or "item"


# ----------------------------------------------------------------- the store

class ContentStore:
    def __init__(self, content_dir: Path, static_dir: Path):
        self.dir = Path(content_dir)
        self.file = self.dir / "content.json"
        self.portrait_file = self.dir / "portrait.json"
        self.uploads = self.dir / "uploads"
        self.history = self.dir / "history"
        self.static_dir = Path(static_dir)
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._mtime: float = -1.0
        self._portrait: Any = None
        self._portrait_mtime: float = -1.0
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)

    # ---- reading ---------------------------------------------------------
    def get(self) -> dict[str, Any]:
        """Validated content, re-read automatically when the file changes."""
        mtime = self.file.stat().st_mtime
        with self._lock:
            if self._cache is None or mtime != self._mtime:
                raw = json.loads(self.file.read_text(encoding="utf-8"))
                self._cache = self.validate_document(raw)
                self._mtime = mtime
            return self._cache

    def get_copy(self) -> dict[str, Any]:
        return copy.deepcopy(self.get())

    def portrait(self) -> Any:
        if not self.portrait_file.exists():
            return None
        mtime = self.portrait_file.stat().st_mtime
        if self._portrait is None or mtime != self._portrait_mtime:
            self._portrait = json.loads(self.portrait_file.read_text(encoding="utf-8"))
            self._portrait_mtime = mtime
        return self._portrait

    # ---- writing ---------------------------------------------------------
    def save(self, doc: dict[str, Any]) -> None:
        clean = self.validate_document(doc)
        data = json.dumps(clean, indent=2, ensure_ascii=False) + "\n"
        with self._lock:
            if self.file.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                backup = self.history / f"content-{stamp}-{secrets.token_hex(3)}.json"
                backup.write_bytes(self.file.read_bytes())
                self._prune_history()
            fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".content-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.file)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            self._cache = None

    def _prune_history(self) -> None:
        files = sorted(self.list_history(), reverse=True)
        for name in files[MAX_HISTORY:]:
            (self.history / name).unlink(missing_ok=True)

    def list_history(self) -> list[str]:
        return sorted((p.name for p in self.history.iterdir() if HISTORY_RE.match(p.name)), reverse=True)

    def restore(self, name: str) -> None:
        if not HISTORY_RE.match(name):
            raise ValidationError("Unknown backup.")
        path = self.history / name
        if not path.is_file():
            raise ValidationError("Unknown backup.")
        self.save(json.loads(path.read_text(encoding="utf-8")))

    # ---- media -----------------------------------------------------------
    def static_images(self) -> list[str]:
        root = self.static_dir / "img"
        out = []
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                rel = p.relative_to(self.static_dir).as_posix()
                if STATIC_IMG_RE.match(rel) and "favicon" not in rel:
                    out.append(rel)
        return out

    def uploaded(self, kinds: set[str] | None = None) -> list[str]:
        out = []
        for p in sorted(self.uploads.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file() and UPLOAD_NAME_RE.match(p.name):
                if kinds is None or p.suffix.lower() in kinds:
                    out.append(p.name)
        return out

    def media_choices(self) -> list[str]:
        return ["static:" + s for s in self.static_images()] + [
            "uploads:" + u for u in self.uploaded(UPLOAD_IMAGE_EXTS)]

    def file_choices(self) -> list[str]:
        return ["uploads:" + u for u in self.uploaded({".pdf"})]

    def media_in_use(self) -> set[str]:
        doc = self.get()
        used = {doc["profile"].get("cv_file", "")}
        used |= {p.get("image", "") for p in doc["projects"]}
        return {u.split(":", 1)[1] for u in used if u.startswith("uploads:")}

    # ---- validation ------------------------------------------------------
    def validate_value(self, f: Field, value: Any) -> Any:
        k = f.kind
        if k == "bool":
            return bool(value)
        if k == "int":
            try:
                n = int(value)
            except (TypeError, ValueError):
                raise ValidationError("Must be a whole number.") from None
            if not -9999 <= n <= 9999:
                raise ValidationError("Number out of range.")
            return n
        if k == "url":
            return clean_url(value)
        if k == "email":
            return clean_email(value)
        if k == "slug":
            return clean_slug(value, f.max_len)
        if k == "select":
            v = _clean(value, 40)
            if v not in {c for c, _ in f.choices}:
                raise ValidationError("Choose one of the options.")
            return v
        if k == "textarea":
            return _clean(value, f.max_len, multiline=True)
        if k == "lines":
            items = value if isinstance(value, list) else []
            out = [_clean(x, f.max_len) for x in items]
            out = [x for x in out if x]
            if len(out) > f.max_items:
                raise ValidationError(f"At most {f.max_items} lines.")
            return out
        if k == "stats":
            items = value if isinstance(value, list) else []
            if len(items) > f.max_items:
                raise ValidationError(f"At most {f.max_items} lines.")
            out = []
            for it in items:
                if not isinstance(it, dict):
                    raise ValidationError("Invalid number line.")
                row = {"value": _clean(it.get("value"), 12), "label": _clean(it.get("label"), 60),
                       "note": _clean(it.get("note"), 100)}
                if row["value"]:
                    out.append(row)
            return out
        if k == "groups":
            items = value if isinstance(value, list) else []
            if len(items) > f.max_items:
                raise ValidationError(f"At most {f.max_items} lines.")
            out = []
            for it in items:
                if not isinstance(it, dict) or not isinstance(it.get("items", []), list):
                    raise ValidationError("Invalid list line.")
                row = {"head": _clean(it.get("head"), 40),
                       "items": [x for x in (_clean(v, 60) for v in it.get("items", [])[:10]) if x]}
                if row["head"] or row["items"]:
                    out.append(row)
            return out
        if k == "media":
            v = _clean(value, 200)
            if v and v not in self.media_choices():
                raise ValidationError("Choose an image from the list.")
            return v
        if k == "file":
            v = _clean(value, 200)
            if v and v not in self.file_choices():
                raise ValidationError("Choose a PDF from the list.")
            return v
        return _clean(value, f.max_len)

    def validate_item(self, coll: Collection, item: Any, errors_prefix: str = "") -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValidationError(f"{errors_prefix}{coll.label}: invalid entry.")
        out: dict[str, Any] = {}
        errors = []
        for f in coll.fields:
            try:
                v = self.validate_value(f, item.get(f.name))
                if f.required and v in ("", [], None):
                    raise ValidationError("Required.")
                out[f.name] = v
            except ValidationError as e:
                errors.append(f"{f.label}: {e}")
        if errors:
            raise ValidationError(errors_prefix + "; ".join(errors))
        if not coll.single:
            iid = item.get("id")
            out["id"] = iid if isinstance(iid, str) and ID_RE.match(iid) else secrets.token_hex(4)
        return out

    def validate_document(self, doc: Any) -> dict[str, Any]:
        if not isinstance(doc, dict):
            raise ValidationError("content.json must contain an object.")
        out: dict[str, Any] = {"version": 1}
        for coll in ALL:
            raw = doc.get(coll.key, {} if coll.single else [])
            if coll.single:
                out[coll.key] = self.validate_item(coll, raw, f"{coll.label}: ")
            else:
                if not isinstance(raw, list):
                    raise ValidationError(f"{coll.label} must be a list.")
                if len(raw) > 200:
                    raise ValidationError(f"Too many {coll.label}.")
                items = [self.validate_item(coll, it, f"{coll.label} #{n + 1}: ") for n, it in enumerate(raw)]
                ids = [it["id"] for it in items]
                if len(set(ids)) != len(ids):
                    for it in items:
                        it["id"] = secrets.token_hex(4)
                out[coll.key] = items
        for key in ("sections", "projects"):
            slugs = [it["slug"] for it in out[key]]
            dup = {s for s in slugs if slugs.count(s) > 1}
            if dup:
                raise ValidationError(f"{BY_KEY[key].label}: duplicate URL name '{sorted(dup)[0]}'.")
        return out


# ------------------------------------------------------------ form <-> data

def form_to_item(coll: Collection, form: Any) -> dict[str, Any]:
    """Parse submitted admin form fields into Python values (validated later)."""
    item: dict[str, Any] = {}
    for f in coll.fields:
        raw = form.get(f.name, "")
        if f.kind == "bool":
            item[f.name] = raw == "on"
        elif f.kind == "lines":
            item[f.name] = [ln for ln in str(raw).splitlines() if ln.strip()]
        elif f.kind == "stats":
            rows = []
            for ln in str(raw).splitlines():
                if not ln.strip():
                    continue
                parts = [p.strip() for p in ln.split("|")] + ["", ""]
                rows.append({"value": parts[0], "label": parts[1], "note": "|".join(parts[2:]).strip("| ")})
            item[f.name] = rows
        elif f.kind == "groups":
            rows = []
            for ln in str(raw).splitlines():
                if not ln.strip():
                    continue
                head, _, rest = ln.partition(":")
                if not rest:
                    head, rest = "", head
                rows.append({"head": head.strip(), "items": [x.strip() for x in rest.split(",") if x.strip()]})
            item[f.name] = rows
        else:
            item[f.name] = raw
    return item


def item_to_form(coll: Collection, item: dict[str, Any]) -> dict[str, Any]:
    """Turn stored values back into the strings shown in the form."""
    out: dict[str, Any] = {}
    for f in coll.fields:
        v = item.get(f.name)
        if f.kind == "lines":
            out[f.name] = "\n".join(v or [])
        elif f.kind == "stats":
            out[f.name] = "\n".join(f"{s['value']} | {s['label']} | {s['note']}".rstrip(" |") for s in (v or []))
        elif f.kind == "groups":
            out[f.name] = "\n".join(
                (f"{g['head']}: " if g["head"] else "") + ", ".join(g["items"]) for g in (v or []))
        else:
            out[f.name] = v
    return out
