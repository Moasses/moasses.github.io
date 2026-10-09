"""Command-line tasks (also available as `flask --app wsgi <command>`)."""
from __future__ import annotations

import getpass
import sys

import click
from flask import Flask

from .security import (AdminAccount, new_totp_secret, password_problems, totp_uri, verify_totp)


def _enroll_totp(username: str, issuer: str) -> str:
    secret = new_totp_secret()
    grouped = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    click.echo("\nTwo-factor authentication (required)")
    click.echo("1. Open an authenticator app (Aegis, Google Authenticator, Microsoft Authenticator, 1Password …)")
    click.echo("2. Add an account → 'Enter a setup key' (type: time-based):")
    click.echo(f"     Account: {username}\n     Key:     {grouped}")
    click.echo(f"   (or paste this link into a password manager: {totp_uri(secret, username, issuer)})")
    for _ in range(3):
        code = click.prompt("3. Enter the 6-digit code the app shows now")
        if verify_totp(secret, code, 0) is not None:
            click.echo("   ✔ Code correct.")
            return secret
        click.echo("   ✘ Wrong code - check the key and your phone's clock, then try again.")
    click.echo("Aborted: 2FA could not be confirmed.", err=True)
    sys.exit(1)


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    def create_admin() -> None:
        """Create (or replace) the admin account: username, password and 2FA."""
        acct = AdminAccount(app.config["INSTANCE_DIR"] / "admin.json")
        if acct.exists() and not click.confirm("An admin account exists. Replace it?", default=False):
            return
        username = click.prompt("Username", default="armin").strip()[:100]
        while True:
            pw = getpass.getpass("Password (min 12 characters, a passphrase is best): ")
            problems = password_problems(pw, username)
            if problems:
                click.echo("  Password needs: " + "; ".join(problems))
                continue
            if getpass.getpass("Repeat password: ") != pw:
                click.echo("  Passwords do not match.")
                continue
            break
        name = app.extensions["content"].get()["profile"]["first_name"]
        secret = _enroll_totp(username, f"{name} website")
        acct.create(username, pw, secret)
        click.echo(f"\nAdmin account created. Sign in at {app.config['ADMIN_PATH']}/login")

    @app.cli.command("reset-2fa")
    def reset_2fa() -> None:
        """Replace the 2FA key (e.g. new phone). Signs out all sessions."""
        acct = AdminAccount(app.config["INSTANCE_DIR"] / "admin.json")
        if not acct.exists():
            click.echo("No admin account yet - run create-admin.")
            return
        data = acct.load()
        secret = _enroll_totp(data["username"], f"{app.extensions['content'].get()['profile']['first_name']} website")
        acct.update(totp_secret=secret, totp_last_counter=0)
        acct.bump_epoch()
        click.echo("2FA key replaced. All sessions were signed out.")

    @app.cli.command("check")
    def check() -> None:
        """Validate content/content.json."""
        c = app.extensions["content"].get()
        click.echo(f"content.json OK: {len(c['sections'])} sections, {len(c['projects'])} projects, "
                   f"{len(c['experience'])} experience entries, {len(c['publications'])} publications.")
