#!/usr/bin/env python3
"""Download the Kode Mono font (SIL Open Font License) into app/static/fonts/.

The site serves the font itself instead of loading it from Google Fonts:
no visitor data goes to a third party (important under GDPR - German courts
have fined sites for embedding Google Fonts) and the CSP can stay 'self'-only.
Run once:  python tools/fetch_fonts.py
"""
import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/kodemono/"
FILES = {"KodeMono%5Bwght%5D.ttf": "KodeMono.ttf", "OFL.txt": "OFL.txt"}
OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "fonts"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for remote, local in FILES.items():
        url = BASE + remote
        with urllib.request.urlopen(url, timeout=30) as r:  # nosec B310 - fixed https URL
            data = r.read(5 * 1024 * 1024)
        if local.endswith(".ttf") and not data.startswith(b"\x00\x01\x00\x00"):
            print(f"Unexpected content from {url}", file=sys.stderr)
            return 1
        (OUT / local).write_bytes(data)
        print(f"saved {local} ({len(data) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
