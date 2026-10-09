"""Content schema.

Every piece of editable content is described here once. The same description is
used to validate content.json on load, to validate every admin form on save, and
to generate the admin forms. Add a field here and it appears in the admin panel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- field kinds -----------------------------------------------------------
# text      single line
# textarea  multi line (paragraphs separated by a blank line)
# url       http(s) / mailto / site-relative link, validated
# email     email address
# bool      checkbox
# select    one of `choices`
# lines     list of strings, one per line
# stats     list of {value,label,note}, one per line: "value | label | note"
# groups    list of {head,items}, one per line: "Head: item, item, item"
# slug      lower-case-url-part
# int       whole number
# media     reference to an image (static asset or uploaded file)
# file      reference to an uploaded PDF


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    max_len: int = 300
    help: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    max_items: int = 30


@dataclass(frozen=True)
class Collection:
    key: str
    label: str
    fields: tuple[Field, ...]
    title_field: str
    single: bool = False          # one object instead of a list
    description: str = ""
    subtitle_fields: tuple[str, ...] = field(default_factory=tuple)


EXPERIENCE_CATEGORIES = (
    ("devops", "DevOps / Cloud"),
    ("research", "Research"),
    ("development", "Software development"),
    ("teaching", "Teaching"),
    ("early", "Early career / internships"),
    ("other", "Other"),
)

PUBLICATION_TYPES = (
    ("journal", "Journal article"),
    ("conference", "Conference paper"),
    ("chapter", "Book chapter"),
    ("thesis", "Thesis"),
    ("patent", "Patent"),
    ("talk", "Talk"),
    ("article", "Article / blog post"),
)

ICONS = (("code", "Code"), ("pipeline", "Pipeline"), ("cloud", "Cloud"), ("none", "No icon"))

PROFILE = Collection(
    key="profile", label="Profile", single=True, title_field="first_name",
    description="Your name, intro, contact details and SEO text.",
    fields=(
        Field("first_name", "First name", required=True, max_len=40),
        Field("last_name", "Last name", required=True, max_len=40),
        Field("roles", "Role lines under your name", "lines", max_len=40, max_items=4,
              help="One per line, e.g. 'A DevOps Engineer,'"),
        Field("tagline", "Short tagline", max_len=120),
        Field("location", "Location", max_len=120),
        Field("intro", "Intro paragraph (italic, top of page)", "textarea", max_len=1500),
        Field("email", "Email", "email", max_len=120),
        Field("phone", "Phone", max_len=40),
        Field("show_phone", "Show phone number publicly", "bool",
              help="Off by default: public numbers attract spam."),
        Field("linkedin", "LinkedIn URL", "url"),
        Field("github", "GitHub URL", "url"),
        Field("scholar", "Google Scholar URL", "url"),
        Field("cv_file", "CV (PDF)", "file", help="Upload the PDF in Media first."),
        Field("site_title", "Browser tab / Google title", max_len=120),
        Field("meta_description", "Google description", "textarea", max_len=300),
        Field("footer", "Footer text", max_len=160, help="{year} is replaced by the current year."),
    ),
)

LEGAL = Collection(
    key="legal", label="Imprint & privacy", single=True, title_field="imprint",
    description="Impressum and privacy policy (recommended for a site hosted in the EU).",
    fields=(
        Field("show_imprint", "Show imprint & privacy links in the footer", "bool"),
        Field("imprint", "Imprint (Impressum)", "textarea", max_len=3000),
        Field("privacy", "Privacy policy", "textarea", max_len=8000),
    ),
)

SECTIONS = Collection(
    key="sections", label="Home page sections", title_field="title",
    description="The blue cards on the home page, in order.",
    subtitle_fields=("slug",),
    fields=(
        Field("title", "Gold title", required=True, max_len=60),
        Field("slug", "Anchor (for menu links)", "slug", required=True, max_len=40,
              help="Used as #anchor, e.g. 'devops'"),
        Field("text", "Text", "textarea", max_len=3000),
        Field("headline", "Big headline words", "lines", max_len=40, max_items=10,
              help="Shown as  A / B / C"),
        Field("stats", "Numbers", "stats", max_items=6,
              help="One per line:  value | label | small note"),
        Field("categories", "Show experience of these categories", "lines", max_len=20, max_items=6,
              help="One per line: " + ", ".join(k for k, _ in EXPERIENCE_CATEGORIES)),
        Field("show_layers", "Show the Code / Pipeline / Cloud layer diagram", "bool"),
        Field("layers_footer", "Text under the layer diagram", max_len=120),
        Field("show_skills", "Show skills", "bool"),
        Field("show_projects", "Show projects", "bool"),
        Field("show_education", "Show education, certifications & languages", "bool"),
        Field("button_label", "Button label", max_len=40),
        Field("button_url", "Button link", "url"),
    ),
)

EXPERIENCE = Collection(
    key="experience", label="Experience", title_field="title",
    subtitle_fields=("org", "start", "end"),
    fields=(
        Field("title", "Role", required=True, max_len=120),
        Field("org", "Organisation", required=True, max_len=120),
        Field("location", "Location", max_len=80),
        Field("start", "Start", max_len=20, help="e.g. Apr 2023"),
        Field("end", "End", max_len=20, help="e.g. Sep 2025 or Present"),
        Field("category", "Category (which section it appears in)", "select",
              required=True, choices=EXPERIENCE_CATEGORIES),
        Field("bullets", "Bullet points", "lines", max_len=400, max_items=12),
    ),
)

LAYERS = Collection(
    key="layers", label="Layer diagram", title_field="title",
    description="The three columns of the Code / Pipeline / Cloud diagram.",
    fields=(
        Field("pre", "Small text above", max_len=20),
        Field("title", "Title", required=True, max_len=20),
        Field("post", "Small text below", max_len=20),
        Field("icon", "Icon", "select", choices=ICONS),
        Field("groups", "Lists", "groups", max_items=4,
              help="One per line:  Heading: item, item, item"),
    ),
)

SKILLS = Collection(
    key="skills", label="Skills", title_field="group",
    fields=(
        Field("group", "Group", required=True, max_len=60),
        Field("items", "Skills", "lines", max_len=120, max_items=15),
    ),
)

PROJECTS = Collection(
    key="projects", label="Projects", title_field="title",
    subtitle_fields=("year", "context"),
    description="Each project gets its own page with the architecture diagram.",
    fields=(
        Field("title", "Title", required=True, max_len=100),
        Field("slug", "URL name", "slug", required=True, max_len=60,
              help="Page address: /projects/<this>/"),
        Field("year", "Year", max_len=20),
        Field("context", "Context", max_len=100, help="e.g. 'Research at TU Berlin'"),
        Field("image", "Architecture image", "media"),
        Field("summary", "Summary (card)", "textarea", max_len=400),
        Field("details", "Full description (project page)", "textarea", max_len=6000),
        Field("results", "Results", "lines", max_len=160, max_items=8),
        Field("tags", "Tech stack tags", "lines", max_len=40, max_items=15),
        Field("link", "Link (GitHub, demo …)", "url"),
    ),
)

EDUCATION = Collection(
    key="education", label="Education", title_field="degree",
    subtitle_fields=("school", "end"),
    fields=(
        Field("degree", "Degree / programme", required=True, max_len=140),
        Field("school", "School", required=True, max_len=120),
        Field("location", "Location", max_len=80),
        Field("start", "Start", max_len=20),
        Field("end", "End", max_len=20),
        Field("notes", "Notes", "lines", max_len=300, max_items=6),
    ),
)

CERTIFICATIONS = Collection(
    key="certifications", label="Certifications", title_field="title",
    subtitle_fields=("issuer", "date"),
    fields=(
        Field("title", "Title", required=True, max_len=140),
        Field("issuer", "Issuer", max_len=120),
        Field("date", "Date", max_len=30),
        Field("url", "Credential link", "url"),
    ),
)

LANGUAGES = Collection(
    key="languages", label="Languages", title_field="name",
    subtitle_fields=("level",),
    fields=(
        Field("name", "Language", required=True, max_len=40),
        Field("level", "Level", max_len=60),
    ),
)

PUBLICATIONS = Collection(
    key="publications", label="Publications", title_field="title",
    subtitle_fields=("year", "type"),
    fields=(
        Field("title", "Title", required=True, max_len=300),
        Field("year", "Year", "int", required=True),
        Field("type", "Type", "select", required=True, choices=PUBLICATION_TYPES),
        Field("authors", "Authors", max_len=300),
        Field("venue", "Venue", max_len=300),
        Field("url", "Link (DOI, PDF …)", "url"),
        Field("award", "Award", max_len=120),
    ),
)

ALL: tuple[Collection, ...] = (
    PROFILE, SECTIONS, EXPERIENCE, PROJECTS, LAYERS, SKILLS,
    EDUCATION, CERTIFICATIONS, LANGUAGES, PUBLICATIONS, LEGAL,
)
BY_KEY: dict[str, Collection] = {c.key: c for c in ALL}


def empty_item(coll: Collection) -> dict[str, Any]:
    """A blank object with the right type for every field."""
    out: dict[str, Any] = {}
    for f in coll.fields:
        if f.kind in ("lines", "stats", "groups"):
            out[f.name] = []
        elif f.kind == "bool":
            out[f.name] = False
        elif f.kind == "int":
            out[f.name] = 0
        elif f.kind == "select":
            out[f.name] = f.choices[0][0] if f.choices else ""
        else:
            out[f.name] = ""
    return out
