#!/usr/bin/env python3
"""Snck Bot launcher.

Validates the Discord token, discovers the application owner, and then starts
bot.py. This keeps installation token-only while preserving an owner-only admin
identity without storing a manually entered Discord user ID.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://discord.com/api/v10/oauth2/applications/@me"


def fetch_application(token: str) -> dict:
    request = Request(
        API_URL,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "SnckBot/1.0",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(
                "Discord rejected the bot token. Reset the token in the Developer Portal and run the installer again."
            ) from exc
        raise RuntimeError(f"Discord API returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Discord: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Could not validate the Discord application: {exc}") from exc
    return payload


def owner_id(application: dict) -> str | None:
    owner = application.get("owner") or {}
    if owner.get("id"):
        return str(owner["id"])

    team = application.get("team") or {}
    if team.get("owner_user_id"):
        return str(team["owner_user_id"])

    for member in team.get("members") or []:
        user = member.get("user") or {}
        if user.get("id") and member.get("membership_state") == 2:
            return str(user["id"])
    return None


def seed_admin(admin_id: str) -> None:
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vps.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id TEXT PRIMARY KEY)")
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
        conn.commit()


def main() -> int:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print("[Snck] DISCORD_TOKEN is missing.", file=sys.stderr)
        return 1

    try:
        application = fetch_application(token)
        admin = owner_id(application)
        if not admin:
            print("[Snck] Could not determine the Discord application owner.", file=sys.stderr)
            print(
                "[Snck] Set MAIN_ADMIN_ID manually in .env if the application is managed by an unsupported team setup.",
                file=sys.stderr,
            )
            return 1

        os.environ["MAIN_ADMIN_ID"] = admin
        seed_admin(admin)
        print(f"[Snck] Discord application verified: {application.get('name', 'Unknown')}")
        print(f"[Snck] Application owner detected and registered as main admin: {admin}")
    except RuntimeError as exc:
        print(f"[Snck] {exc}", file=sys.stderr)
        return 1

    bot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
    import runpy
    runpy.run_path(bot_path, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
