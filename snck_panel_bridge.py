#!/usr/bin/env python3
"""Snck Discord <-> KVM panel bridge.

The panel and bot use the same vps.db ownership field (user_id). A Discord
user receives one panel account keyed by Discord ID. No bot token is stored
by this bridge.
"""
from __future__ import annotations
import hashlib
import secrets
import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

BASE = Path(__file__).resolve().parent
VPS_DB = BASE / "vps.db"
USERS_DB = BASE / "panel_users.db"
PORTAL_URL = os.getenv("SNCK_PANEL_URL", "http://127.0.0.1:5000").rstrip("/")


def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    c = sqlite3.connect(USERS_DB, timeout=20)
    c.row_factory = sqlite3.Row
    return c


def init():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS panel_users(
            discord_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_once TEXT,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS panel_vps(
            vps_id INTEGER PRIMARY KEY,
            discord_id TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        c.commit()


def hashpw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def provision(discord_id: int, display_name: str | None = None):
    """Create exactly one panel account per Discord user.

    For a new account, return the one-time password. Existing accounts never
    expose their password again; the customer must use their existing
    credentials or an administrator can reset them.
    """
    init()
    did = str(discord_id)
    with db() as c:
        row = c.execute(
            "SELECT username FROM panel_users WHERE discord_id=? AND active=1",
            (did,),
        ).fetchone()
        if row:
            return row["username"], None, False

        base = (display_name or f"snck-{did[-8:]}").lower().replace(" ", "-")
        base = "".join(ch for ch in base if ch.isalnum() or ch == "-")[:24]
        base = base or f"snck-{did[-8:]}"
        if c.execute("SELECT 1 FROM panel_users WHERE username=?", (base,)).fetchone():
            base = f"{base}-{secrets.token_hex(2)}"

        password = secrets.token_urlsafe(12)
        c.execute(
            "INSERT INTO panel_users(discord_id,username,password_hash,password_once,created_at,active) VALUES(?,?,?,?,?,1)",
            (did, base, hashpw(password), password, now()),
        )
        c.commit()
        return base, password, True


def sync_vps():
    """Mirror ownership into panel_vps without changing the bot's source DB."""
    init()
    if not VPS_DB.exists():
        return 0
    with sqlite3.connect(VPS_DB) as src:
        src.row_factory = sqlite3.Row
        try:
            rows = src.execute("SELECT id,user_id FROM vps WHERE user_id IS NOT NULL").fetchall()
        except sqlite3.Error:
            return 0
    with db() as c:
        for row in rows:
            c.execute(
                "INSERT OR REPLACE INTO panel_vps(vps_id,discord_id,updated_at) VALUES(?,?,?)",
                (int(row["id"]), str(row["user_id"]), now()),
            )
        c.commit()
    return len(rows)


class SnckPanelBridge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init()

    @commands.command(name="panel")
    async def panel_access(self, ctx: commands.Context):
        """Create/link the Discord user's customer panel account."""
        username, password, created = provision(ctx.author.id, ctx.author.name)
        count = sync_vps()
        if created:
            text = (
                "Your Snck panel account has been created.\n"
                f"Panel: {PORTAL_URL}\n"
                f"Username: `{username}`\n"
                f"Password: `{password}`\n\n"
                "Your VPS access is linked to this Discord account."
            )
        else:
            text = (
                "Your Snck panel account is already linked to this Discord account.\n"
                f"Panel: {PORTAL_URL}\n"
                f"Username: `{username}`\n\n"
                "Use your existing panel password. If you lost it, contact an administrator."
            )
        try:
            await ctx.author.send(text)
            await ctx.reply(f"Panel access details were sent to your DMs. Synced {count} VPS record(s).", delete_after=15)
        except discord.Forbidden:
            await ctx.reply("I could not DM you. Enable DMs from this server and run the command again.", delete_after=20)

    @commands.command(name="myvps", aliases=("vps",))
    async def my_vps(self, ctx: commands.Context):
        """Show VPS records owned by the Discord user."""
        sync_vps()
        if not VPS_DB.exists():
            await ctx.reply("No VPS records are available.", delete_after=15)
            return
        with sqlite3.connect(VPS_DB) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT id,container_name,status,ip,ram,cpu,storage FROM vps WHERE user_id=? ORDER BY id DESC",
                (str(ctx.author.id),),
            ).fetchall()
        if not rows:
            await ctx.reply("No VPS is currently assigned to your Discord account.", delete_after=15)
            return
        lines = ["**SNCK VPS**"]
        for r in rows[:10]:
            lines.append(f"`{r['container_name']}` — {str(r['status']).upper()} — {r['ip'] or 'IP pending'}")
        await ctx.reply("\n".join(lines), delete_after=30)

    @commands.Cog.listener()
    async def on_ready(self):
        sync_vps()


async def setup(bot):
    await bot.add_cog(SnckPanelBridge(bot))
