#!/usr/bin/env python3
"""Discord-to-Snck customer account bridge.

Creates one panel account per Discord user and keeps the account's VPS ownership
linked to the bot's vps.db. Credentials are delivered only by DM.
"""
from __future__ import annotations
import hashlib, secrets, sqlite3, os
from datetime import datetime
from pathlib import Path
from discord.ext import commands
import discord

BASE=Path(__file__).resolve().parent; DB=BASE/'panel_users.db'; VPSDB=BASE/'vps.db'
PORTAL_URL=os.getenv('SNCK_PANEL_URL','http://127.0.0.1:5001')

def init():
 with sqlite3.connect(DB) as c:
  c.execute('CREATE TABLE IF NOT EXISTS panel_users(discord_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, password_once TEXT, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
  c.execute('CREATE TABLE IF NOT EXISTS panel_vps(vps_id INTEGER PRIMARY KEY, discord_id TEXT NOT NULL, updated_at TEXT NOT NULL)')

def sync():
 init()
 if not VPSDB.exists(): return
 with sqlite3.connect(VPSDB) as src: rows=src.execute('SELECT id,user_id FROM vps').fetchall()
 with sqlite3.connect(DB) as c:
  for vid,did in rows: c.execute('INSERT OR REPLACE INTO panel_vps VALUES(?,?,?)',(vid,str(did),datetime.utcnow().isoformat()))
  c.commit()

def provision(discord_id, display_name):
 init(); did=str(discord_id)
 with sqlite3.connect(DB) as c:
  c.row_factory=sqlite3.Row; row=c.execute('SELECT username,password_once FROM panel_users WHERE discord_id=?',(did,)).fetchone()
  if row: return row['username'],row['password_once'],False
  base=''.join(x for x in display_name.lower().replace(' ','-') if x.isalnum() or x=='-')[:20] or 'snck-user'
  if c.execute('SELECT 1 FROM panel_users WHERE username=?',(base,)).fetchone(): base=f'{base}-{secrets.token_hex(2)}'
  pw=secrets.token_urlsafe(12)
  c.execute('INSERT INTO panel_users VALUES(?,?,?,?,?,1)',(did,base,hashlib.sha256(pw.encode()).hexdigest(),pw,datetime.utcnow().isoformat()))
  c.commit(); return base,pw,True

class Bridge(commands.Cog):
 def __init__(self,bot): self.bot=bot; init()
 @commands.command(name='panel')
 async def panel(self,ctx):
  sync(); username,password,new=provision(ctx.author.id,ctx.author.name)
  msg=f'Snck Customer Panel\nPanel: {PORTAL_URL}\nUsername: `{username}`\nPassword: `{password}`\n\nYour panel account is linked to your Discord account and only your assigned VPS will be visible.'
  try:
   await ctx.author.send(msg); await ctx.reply('Your Snck panel login has been sent to your DMs.',delete_after=15)
  except discord.Forbidden: await ctx.reply('Enable DMs from this server and run !panel again.',delete_after=20)
 @commands.Cog.listener()
 async def on_ready(self): sync()

async def setup(bot): await bot.add_cog(Bridge(bot))
