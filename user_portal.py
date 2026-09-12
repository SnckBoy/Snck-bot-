#!/usr/bin/env python3
"""Snck customer VPS portal. Shares ownership with the Discord bot via vps.db."""
from __future__ import annotations
import hashlib, os, secrets, sqlite3, subprocess
from pathlib import Path
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from kvm import state, ip, start, stop, reboot, delete

APP=Path(__file__).resolve().parent
USERS=APP/'panel_users.db'; VPSDB=APP/'vps.db'
PORT=int(os.getenv('SNCK_USER_PORTAL_PORT','5001'))
app=Flask(__name__); app.secret_key=os.getenv('SNCK_PANEL_SECRET') or secrets.token_hex(32)

def db():
 c=sqlite3.connect(USERS,timeout=20); c.row_factory=sqlite3.Row; return c

def init():
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS panel_users(discord_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, password_once TEXT, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)''')
  c.execute('''CREATE TABLE IF NOT EXISTS panel_vps(vps_id INTEGER PRIMARY KEY, discord_id TEXT NOT NULL, updated_at TEXT NOT NULL)''')
  c.commit()

def user():
 return session.get('user')

def auth(f):
 @wraps(f)
 def w(*a,**kw):
  if not user(): return redirect(url_for('login'))
  return f(*a,**kw)
 return w

def get_owned():
 init(); did=str(user()['discord_id'])
 if not VPSDB.exists(): return []
 with sqlite3.connect(VPSDB) as c:
  c.row_factory=sqlite3.Row
  rows=c.execute('SELECT * FROM vps WHERE user_id=? ORDER BY id DESC',(did,)).fetchall()
 return rows

CSS='''<style>:root{--bg:#070811;--card:#111629;--line:#252d4a;--text:#f5f7ff;--muted:#8992b0;--a:#57e6ff;--b:#a970ff;--ok:#57e39b;--bad:#ff667f}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0%,#211b48,#070811 45%);color:var(--text);font:15px Inter,system-ui,Arial}.wrap{max-width:1100px;margin:auto;padding:20px}.nav{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:15px 18px;background:#0c1120ee;border:1px solid var(--line);border-radius:18px}.brand{font-weight:900;letter-spacing:.12em}.brand span{color:var(--a)}a{color:var(--a);text-decoration:none}.links{display:flex;gap:14px}.hero{margin:30px 0}.title{font-size:32px;font-weight:900}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px}.card{background:linear-gradient(145deg,#12172a,#0b1020);border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:0 18px 55px #0007}.value{font-size:25px;font-weight:900;margin-top:7px}.ok{color:var(--ok)}.bad{color:var(--bad)}button{border:0;border-radius:11px;padding:10px 15px;background:linear-gradient(100deg,var(--a),var(--b));color:#05060c;font-weight:850;cursor:pointer}.danger{background:linear-gradient(100deg,#ff667f,#a970ff)}.secondary{background:#171d31;color:var(--text);border:1px solid var(--line)}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}input{width:100%;padding:12px;border-radius:11px;border:1px solid var(--line);background:#070a14;color:var(--text);margin:7px 0 14px}.login{max-width:440px;margin:10vh auto}.flash{padding:12px;border:1px solid var(--line);border-radius:12px;background:#12182a;margin:12px 0}@media(max-width:650px){.wrap{padding:12px}.links{flex-wrap:wrap}.title{font-size:26px}}</style>'''
LAY='''<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>{{title}} · Snck</title>'''+CSS+'''</head><body><div class=wrap><div class=nav><div class=brand>SNCK <span>VPS PORTAL</span></div>{% if session.get('user') %}<div class=links><a href="/">VPS</a><a href="/logout">Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>'''

def page(title,body): return render_template_string(LAY,title=title,body=body)

@app.route('/login',methods=['GET','POST'])
def login():
 init()
 if request.method=='POST':
  u=request.form.get('username','').strip(); p=request.form.get('password','')
  with db() as c: r=c.execute('SELECT * FROM panel_users WHERE username=? AND active=1',(u,)).fetchone()
  if r and secrets.compare_digest(r['password_hash'],hashlib.sha256(p.encode()).hexdigest()): session['user']={'discord_id':r['discord_id'],'username':r['username']}; return redirect(url_for('index'))
  flash('Invalid panel credentials.')
 body='''<div class=login><div class=card><div class=title>Snck VPS Portal</div><p class=muted>Sign in to manage VPS assigned to your Discord account.</p><form method=post><label>Username</label><input name=username required><label>Password</label><input type=password name=password required><button>Sign in</button></form><p class=muted>Need access? Use <b>!panel</b> in the connected Discord server.</p></div></div>'''
 return page('Login',body)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
@auth
def index():
 rows=get_owned(); cards=''
 for r in rows:
  name=r['container_name']; st=state(name, str(r['node_id']) if False else '')
  # bot's vps.db is the ownership source; node URI is not stored in this schema, so
  # use the local libvirt connection for the customer portal. Remote-node operations remain bot-managed.
  addr=ip(name,'')
  cards+=f'''<div class=card><div class=muted>VPS</div><div class=value>{name}</div><p>Status: <span class={'ok' if st=='running' else 'bad'}>{st.upper()}</span></p><p class=muted>IPv4: {addr or 'Detecting...'}</p><p class=muted>CPU {r['cpu']} · RAM {r['ram']} · Disk {r['storage']}</p><div class=actions><form method=post action="/vps/{r['id']}/start"><button>Start</button></form><form method=post action="/vps/{r['id']}/stop"><button class=secondary>Stop</button></form><form method=post action="/vps/{r['id']}/restart"><button class=secondary>Restart</button></form></div></div>'''
 body=f'''<div class=hero><div class=title>My VPS</div><p class=muted>Only VPS assigned to your Discord account are shown here.</p></div><div class=grid>{cards or '<div class=card><div class=value>No VPS assigned</div><p class=muted>Your VPS will appear here after it is created for your Discord account.</p></div>'}</div>'''
 return page('My VPS',body)

def owned(vps_id):
 did=str(user()['discord_id'])
 with sqlite3.connect(VPSDB) as c:
  c.row_factory=sqlite3.Row; r=c.execute('SELECT * FROM vps WHERE id=? AND user_id=?',(vps_id,did)).fetchone()
 return r

@app.post('/vps/<int:vps_id>/<action>')
@auth
def action(vps_id,action):
 r=owned(vps_id)
 if not r: flash('VPS not found or access denied.'); return redirect(url_for('index'))
 name=r['container_name']
 try:
  if action=='start': start(name,'')
  elif action=='stop': stop(name,'')
  elif action=='restart': reboot(name,'')
  else: raise ValueError('Unsupported action')
  flash(f'{action.title()} requested for {name}.')
 except Exception as e: flash(f'Operation failed: {str(e)[:300]}')
 return redirect(url_for('index'))

if __name__=='__main__':
 init(); app.run(host='0.0.0.0',port=PORT,debug=False)
