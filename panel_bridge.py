#!/usr/bin/env python3
"""Snck bridge: shared VPS ownership and panel accounts.
The bot and web portal share vps.db; this module never stores Discord bot tokens.
"""
from __future__ import annotations
import hashlib, secrets, sqlite3
from pathlib import Path
from datetime import datetime
import os
from discord.ext import commands
import discord

BASE = Path(__file__).resolve().parent
DB = BASE / "vps.db"
USERS = BASE / "panel_users.db"
PORTAL_URL = os.getenv("SNCK_PANEL_URL", "http://127.0.0.1:5001")

def conn():
    c=sqlite3.connect(USERS, timeout=20)
    c.row_factory=sqlite3.Row
    return c

def init():
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS panel_users(
            discord_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_once TEXT,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS panel_vps(
            vps_id INTEGER PRIMARY KEY,
            discord_id TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        c.commit()

def hashpw(p): return hashlib.sha256(p.encode()).hexdigest()

def provision(discord_id, username=None):
    init(); did=str(discord_id)
    with conn() as c:
        row=c.execute('SELECT username,password_once FROM panel_users WHERE discord_id=?',(did,)).fetchone()
        if row: return row['username'], row['password_once'], False
        base=(username or f'snck-{did[-8:]}').lower().replace(' ','-')
        base=''.join(ch for ch in base if ch.isalnum() or ch=='-')[:24] or f'snck-{did[-8:]}'
        if c.execute('SELECT 1 FROM panel_users WHERE username=?',(base,)).fetchone(): base=f'{base}-{secrets.token_hex(2)}'
        password=secrets.token_urlsafe(12)
        c.execute('INSERT INTO panel_users VALUES(?,?,?,?,?,1)',(did,base,hashpw(password),password,datetime.utcnow().isoformat()))
        c.commit()
        return username,password,True

def sync_vps():
    init()
    if not DB.exists(): return 0
    with sqlite3.connect(DB) as src:
        rows=src.execute('SELECT id,user_id FROM vps').fetchall()
    with conn() as c:
        for vps_id,user_id in rows:
            c.execute('INSERT OR REPLACE INTO panel_vps(vps_id,discord_id,updated_at) VALUES(?,?,?)',(vps_id,str(user_id),datetime.utcnow().isoformat()))
        c.commit()
    return len(rows)

class SnckPanelBridge(commands.Cog):
    def __init__(self, bot): self.bot=bot; init()
    @commands.command(name='panel')
    async def panel_access(self, ctx):
        username,password,new=provision(ctx.author.id, ctx.author.name)
        sync_vps()
        text=(f'Your Snck panel account is ready.\nPanel: {PORTAL_URL}\nUsername: `{username}`\nPassword: `{password}`\n\nKeep these credentials private.' if new else f'Your Snck panel account already exists.\nPanel: {PORTAL_URL}\nUsername: `{username}`\nPassword: `{password}`')
        try:
            await ctx.author.send(text)
            await ctx.reply('Panel access details were sent to your DMs.', delete_after=15)
        except discord.Forbidden:
            await ctx.reply('I could not DM you. Enable DMs from this server and run the command again.', delete_after=20)
    @commands.Cog.listener()
    async def on_ready(self): sync_vps()

async def setup(bot): await bot.add_cog(SnckPanelBridge(bot))
