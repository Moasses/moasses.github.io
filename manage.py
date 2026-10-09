#!/usr/bin/env python3
"""One entry point for everything:

    python manage.py run              start the site + admin on http://127.0.0.1:5000
    python manage.py create-admin     create your admin login (password + 2FA)
    python manage.py reset-2fa        new phone? replace the 2FA key
    python manage.py check            validate content/content.json
    python manage.py build            build the static site into ./build (GitHub Pages)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="local development server")
    run.add_argument("--port", type=int, default=5000)
    build = sub.add_parser("build", help="build the static site")
    build.add_argument("--out", default="build")
    build.add_argument("--base-path", default=os.environ.get("BASE_PATH", ""),
                       help="for GitHub *project* pages, e.g. /my-repo (not needed for username.github.io)")
    build.add_argument("--cname", default=os.environ.get("CUSTOM_DOMAIN", ""),
                       help="custom domain for GitHub Pages, e.g. moasses.eu")
    for name in ("create-admin", "reset-2fa", "check"):
        sub.add_parser(name)
    args = parser.parse_args()

    if args.cmd == "build":
        from app.freeze import build_static
        pages = build_static(Path(args.out), args.base_path, args.cname)
        print(f"Built {len(pages)} pages into {args.out}/")
        return

    from app import create_app
    app = create_app()
    if args.cmd == "run":
        if app.config["APP_ENV"] == "production":
            sys.exit("Use gunicorn in production (see deploy/).")
        print(f" * Site:  http://127.0.0.1:{args.port}/")
        print(f" * Admin: http://127.0.0.1:{args.port}{app.config['ADMIN_PATH']}/")
        # bound to localhost only; the interactive debugger stays OFF (it allows code execution)
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=True)
        return
    with app.app_context():
        app.cli.commands[args.cmd].main(args=[], prog_name=f"manage.py {args.cmd}", standalone_mode=True)


if __name__ == "__main__":
    main()
