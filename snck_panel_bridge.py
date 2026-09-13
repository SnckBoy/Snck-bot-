#!/usr/bin/env python3
"""Snck Discord to web-panel account bridge.

The panel and bot share vps.db. Discord ID is the VPS owner key. This cog
only owns panel-account provisioning; VPS commands remain registered by bot.py
so there is never a duplicate myvps/vps command registration.
"""
from __future__ import annotations
import hashlib, secrets, sqlite3, os
from datetime import datetime, timezone
from pathlib import Path
import discord
from discord.ext import commands
BASE=Path(__file__).resolve().parent
VPS_DB=BASE/'vps.db'
USERS_DB=BASE/'panel_users.db'
PORTAL_URL=os.getenv('SNCK_PANEL_URL','http://127.0.0.1:5000').rstrip('/')
def now(): return datetime.now(timezone.utc).isoformat()
def db():
 c=sqlite3.connect(USERS_DB,timeout=20); c.row_factory=sqlite3.Row; return c
def init():
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS panel_users(discord_id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,password_once TEXT,created_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1)''')
  c.execute('''CREATE TABLE IF NOT EXISTS panel_vps(vps_id INTEGER PRIMARY KEY,discord_id TEXT NOT NULL,updated_at TEXT NOT NULL)'''); c.commit()
def hashpw(p): return hashlib.sha256(p.encode('utf-8')).hexdigest()
def provision(discord_id,display_name=None):
 init(); did=str(discord_id)
 with db() as c:
  row=c.execute('SELECT username FROM panel_users WHERE discord_id=? AND active=1',(did,)).fetchone()
  if row: return row['username'],None,False
  base=(display_name or f'snck-{did[-8:]}').lower().replace(' ','-')
  base=''.join(ch for ch in base if ch.isalnum() or ch=='-')[:24] or f'snck-{did[-8:]}'
  if c.execute('SELECT 1 FROM panel_users WHERE username=?',(base,)).fetchone(): base=f'{base}-{secrets.token_hex(2)}'
  password=secrets.token_urlsafe(12)
  c.execute('INSERT INTO panel_users(discord_id,username,password_hash,password_once,created_at,active) VALUES(?,?,?,?,?,1)',(did,base,hashpw(password),password,now())); c.commit()
  return base,password,True
def sync_vps():
 init()
 if not VPS_DB.exists(): return 0
 with sqlite3.connect(VPS_DB) as src:
  src.row_factory=sqlite3.Row
  try: rows=src.execute('SELECT id,user_id FROM vps WHERE user_id IS NOT NULL').fetchall()
  except sqlite3.Error: return 0
 with db() as c:
  for row in rows: c.execute('INSERT OR REPLACE INTO panel_vps(vps_id,discord_id,updated_at) VALUES(?,?,?)',(int(row['id']),str(row['user_id']),now()))
  c.commit()
 return len(rows)
class SnckPanelBridge(commands.Cog):
 def __init__(self,bot): self.bot=bot; init()
 @commands.command(name='panel')
 async def panel_access(self,ctx):
  username,password,created=provision(ctx.author.id,ctx.author.name); count=sync_vps()
  if created: text=f'Your Snck panel account has been created.\nPanel: {PORTAL_URL}\nUsername: `{username}`\nPassword: `{password}`\n\nYour VPS access is linked to this Discord account.'
  else: text=f'Your Snck panel account is already linked to this Discord account.\nPanel: {PORTAL_URL}\nUsername: `{username}`\n\nUse your existing panel password.'
  try: await ctx.author.send(text); await ctx.reply(f'Panel access details were sent to your DMs. Synced {count} VPS record(s).',delete_after=15)
  except discord.Forbidden: await ctx.reply('I could not DM you. Enable DMs from this server and run the command again.',delete_after=20)
 @commands.Cog.listener()
 async def on_ready(self): sync_vps()
async def setup(bot): await bot.add_cog(SnckPanelBridge(bot))
