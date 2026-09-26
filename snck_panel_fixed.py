#!/usr/bin/env python3
from __future__ import annotations
import hmac, os, secrets, sqlite3, re
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, flash, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
try:
    from kvm import create as kvm_create, delete as kvm_delete, reboot as kvm_reboot, start as kvm_start, stop as kvm_stop, kvm_available, tools_ok
except Exception:
    kvm_create=kvm_delete=kvm_reboot=kvm_start=kvm_stop=None
    def kvm_available(): return False
    def tools_ok(): return False
BASE=Path(__file__).resolve().parent
DB=BASE/'snck_panel.db'; PORT=int(os.getenv('SNCK_PANEL_PORT','5000')); CODESPACE=os.getenv('SNCK_CODESPACE')=='1'; LICENSE_KEY=os.getenv('SNCK_LICENSE_KEY','official.snck.fun')
app=Flask(__name__); app.secret_key=os.getenv('SNCK_PANEL_SECRET') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('SNCK_COOKIE_SECURE','0')=='1',MAX_CONTENT_LENGTH=64*1024)
CSS='''<style>body{margin:0;background:#f7f3f9;color:#272331;font:15px system-ui,sans-serif}.wrap{max-width:1200px;margin:auto;padding:20px}.nav{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:14px 18px;background:#fff;border:1px solid #e6dff0;border-radius:18px;position:sticky;top:12px}.brand{font-weight:900;letter-spacing:.1em}.brand span{color:#8b5cf6}.links{display:flex;gap:6px;flex-wrap:wrap}.links a{padding:8px 10px;border-radius:10px;color:#272331;text-decoration:none}.links a:hover{background:#eee4ff}.hero{margin:30px 0 20px}.title{font-size:31px;font-weight:900}.muted{color:#6b6574}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:16px 0}.card{background:#fff;border:1px solid #e6dff0;border-radius:18px;padding:20px;box-shadow:0 8px 28px #0001}.value{font-size:25px;font-weight:900;margin-top:8px}.ok{color:#16a34a}.bad{color:#dc2626}label{display:block;margin:12px 0 6px;font-weight:650;color:#6b6574}input{width:100%;padding:11px 12px;border:1px solid #e6dff0;border-radius:11px;box-sizing:border-box;margin-bottom:6px}button{border:0;border-radius:11px;padding:10px 14px;background:linear-gradient(100deg,#8b5cf6,#6d28d9);color:#fff;font-weight:800;cursor:pointer}.secondary{background:#eee4ff;color:#392a54}.danger{background:#fee2e2;color:#991b1b}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.flash{padding:12px 14px;border:1px solid #e6dff0;background:#f3e8ff;border-radius:12px;margin:12px 0}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:11px;border-bottom:1px solid #e6dff0}.login{max-width:460px;margin:8vh auto}.pill{display:inline-block;padding:4px 8px;border:1px solid #e6dff0;border-radius:999px;background:#f3e8ff}@media(max-width:700px){.wrap{padding:12px}.nav{position:static}.table{display:block;overflow:auto;white-space:nowrap}}</style>'''
LAYOUT='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}} · Snck</title>'''+CSS+'''</head><body><div class="wrap"><div class="nav"><div class="brand">SNCK <span>KVM PANEL</span></div>{% if session.get('role') %}<div class="links"><a href="/">Dashboard</a><a href="/vps">VPS</a>{% if session.get('role')=='admin' %}<a href="/nodes">Nodes</a><a href="/bot">Bot</a>{% endif %}<a href="/logout">Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>'''
def db():
 c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON'); return c
def init_db():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  c.execute("CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,location TEXT NOT NULL DEFAULT 'Local',url TEXT NOT NULL DEFAULT '',is_local INTEGER NOT NULL DEFAULT 1,storage TEXT NOT NULL DEFAULT '/var/lib/libvirt/images')")
  c.execute("CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL DEFAULT 'admin',node_id INTEGER NOT NULL DEFAULT 1,container_name TEXT UNIQUE NOT NULL,ram TEXT NOT NULL,cpu TEXT NOT NULL,storage TEXT NOT NULL,config TEXT NOT NULL,os_version TEXT NOT NULL DEFAULT 'ubuntu:24.04',status TEXT NOT NULL DEFAULT 'stopped',created_at TEXT NOT NULL,mock INTEGER NOT NULL DEFAULT 0,FOREIGN KEY(node_id) REFERENCES nodes(id))")
  c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('admin_user','admin')"); c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('admin_pass_hash','')"); c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('license_active','0')")
  if not c.execute('SELECT 1 FROM nodes LIMIT 1').fetchone(): c.execute("INSERT INTO nodes(name,location,url,is_local,storage) VALUES(?,?,?,?,?)",('Local KVM Node','Local','',1,'/var/lib/libvirt/images'))
  c.commit()
def setting(k,d=''):
 with db() as c:
  r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone(); return r['value'] if r else d
def set_setting(k,v):
 with db() as c: c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v)); c.commit()
def csrf():
 if '_csrf' not in session: session['_csrf']=secrets.token_urlsafe(32)
 return session['_csrf']
@app.context_processor
def helpers(): return {'csrf_token':csrf}
@app.before_request
def csrf_guard():
 if request.method=='POST' and request.endpoint not in {'license','setup','login'}:
  if not session.get('_csrf') or not hmac.compare_digest(request.form.get('_csrf',''),session['_csrf']): return 'CSRF validation failed',400
def admin_required(f):
 @wraps(f)
 def w(*a,**kw):
  init_db()
  if setting('license_active')!='1': return redirect(url_for('license'))
  if session.get('role')!='admin': return redirect(url_for('login'))
  return f(*a,**kw)
 return w
def login_required(f):
 @wraps(f)
 def w(*a,**kw):
  init_db()
  if setting('license_active')!='1': return redirect(url_for('license'))
  if session.get('role') not in {'admin','user'}: return redirect(url_for('login'))
  return f(*a,**kw)
 return w
@app.route('/license',methods=['GET','POST'])
def license():
 init_db()
 if request.method=='POST':
  if hmac.compare_digest(request.form.get('license','').strip(),LICENSE_KEY): set_setting('license_active','1'); return redirect(url_for('setup'))
  flash('License key is invalid.')
 return render_template_string(LAYOUT,title='License',body='<div class="login"><div class="card"><div class="title">Activate Snck</div><p class="muted">Enter the Snck license to unlock the panel.</p><form method="post"><label>License</label><input name="license" required><button>Activate License</button></form></div></div>')
@app.route('/setup',methods=['GET','POST'])
def setup():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if setting('admin_pass_hash'): return redirect(url_for('login'))
 if request.method=='POST':
  u=request.form.get('username','admin').strip() or 'admin'; p=request.form.get('password','')
  if len(u)<3 or len(u)>64: flash('Username must be 3-64 characters.')
  elif len(p)<10: flash('Password must be at least 10 characters.')
  else: set_setting('admin_user',u); set_setting('admin_pass_hash',generate_password_hash(p,method='scrypt')); return redirect(url_for('login'))
 return render_template_string(LAYOUT,title='Setup',body='<div class="login"><div class="card"><div class="title">Create Administrator</div><p class="muted">Password storage uses a password-specific KDF.</p><form method="post"><label>Username</label><input name="username" value="admin" minlength="3" maxlength="64" required><label>Password</label><input type="password" name="password" minlength="10" required><button>Create Admin Account</button></form></div></div>')
@app.route('/login',methods=['GET','POST'])
def login():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if not setting('admin_pass_hash'): return redirect(url_for('setup'))
 if request.method=='POST':
  if hmac.compare_digest(request.form.get('username',''),setting('admin_user')) and check_password_hash(setting('admin_pass_hash'),request.form.get('password','')):
   session.clear(); session['role']='admin'; session['uid']='admin'; session['_csrf']=secrets.token_urlsafe(32); return redirect(url_for('index'))
  flash('Invalid credentials.')
 return render_template_string(LAYOUT,title='Login',body='<div class="login"><div class="card"><div class="title">Snck KVM Panel</div><form method="post"><label>Username</label><input name="username" required><label>Password</label><input type="password" name="password" required><button>Sign in</button></form></div></div>')
@app.get('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
@app.get('/health')
def health(): return {'status':'ok','panel':'snck','codespace':CODESPACE,'kvm':bool(kvm_available()),'tools':bool(tools_ok())}
def rows():
 with db() as c: return c.execute("SELECT v.*,n.name node_name FROM vps v LEFT JOIN nodes n ON n.id=v.node_id WHERE v.status!='deleted' ORDER BY v.id DESC").fetchall()
@app.get('/')
@login_required
def index():
 with db() as c: n=c.execute('SELECT COUNT(*) x FROM nodes').fetchone()['x']
 body=f'<div class="hero"><div class="title">Command Center</div><p class="muted">Snck KVM panel — {"Codespace test mode" if CODESPACE else "host mode"}.</p></div><div class="grid"><div class="card"><div class="muted">Nodes</div><div class="value">{n}</div></div><div class="card"><div class="muted">VPS</div><div class="value">{len(rows())}</div></div><div class="card"><div class="muted">KVM</div><div class="value {'ok' if kvm_available() else 'bad'}">{"READY" if kvm_available() else "TEST/MISSING"}</div></div></div><div class="card"><h2>VPS Management</h2><p class="muted">Codespaces use mock mode when KVM is unavailable.</p><a href="/vps"><button>Manage VPS</button></a> <a href="/vps/create"><button class="secondary">Create VPS</button></a></div>'
 return render_template_string(LAYOUT,title='Dashboard',body=body)
@app.get('/vps')
@login_required
def vps_list():
 trs=[]
 for r in rows():
  trs.append(f'<tr><td>{r["container_name"]}</td><td>{r["node_name"] or "-"}</td><td>{r["ram"]} / {r["cpu"]} CPU / {r["storage"]}</td><td><span class="pill">{r["status"]}</span></td><td><form method="post" action="/vps/{r["id"]}/start" style="display:inline"><input type="hidden" name="_csrf" value="{csrf()}"><button>Start</button></form> <form method="post" action="/vps/{r["id"]}/stop" style="display:inline"><input type="hidden" name="_csrf" value="{csrf()}"><button class="secondary">Stop</button></form> <form method="post" action="/vps/{r["id"]}/reboot" style="display:inline"><input type="hidden" name="_csrf" value="{csrf()}"><button class="secondary">Reboot</button></form> <form method="post" action="/vps/{r["id"]}/delete" style="display:inline"><input type="hidden" name="_csrf" value="{csrf()}"><button class="danger">Delete</button></form></td></tr>')
 body='<div class="hero"><div class="title">VPS</div><p class="muted">Manage virtual machines and test instances.</p></div><a href="/vps/create"><button>Create VPS</button></a><div class="card"><table class="table"><tr><th>Name</th><th>Node</th><th>Resources</th><th>Status</th><th>Actions</th></tr>'+(''.join(trs) or '<tr><td colspan="5">No VPS yet.</td></tr>')+'</table></div>'
 return render_template_string(LAYOUT,title='VPS',body=body)
@app.route('/vps/create',methods=['GET','POST'])
@admin_required
def vps_create():
 if request.method=='POST':
  try:
   name=request.form.get('name','').strip(); password=request.form.get('password','').strip(); ram=int(request.form.get('ram','1024')); cpu=int(request.form.get('cpu','1')); disk=int(request.form.get('disk','10'))
   if not name or not password: raise ValueError('Name and password are required')
   if not re.fullmatch(r'[A-Za-z0-9_.-]{1,63}',name): raise ValueError('Invalid VPS name')
   if not (512<=ram<=1048576 and 1<=cpu<=128 and 5<=disk<=16384): raise ValueError('Resource limits are invalid')
   mock=int(CODESPACE or not kvm_available() or not tools_ok())
   if not mock: kvm_create(name,ram,cpu,disk,password); kvm_start(name)
   with db() as c:
    nid=c.execute('SELECT id FROM nodes ORDER BY id LIMIT 1').fetchone()['id']; c.execute('INSERT INTO vps(user_id,node_id,container_name,ram,cpu,storage,config,status,created_at,mock) VALUES(?,?,?,?,?,?,?,?,?,?)',('admin',nid,name,f'{ram}MB',cpu,f'{disk}GB',f'{ram}MB RAM / {cpu} CPU / {disk}GB Disk','running',datetime.now(timezone.utc).isoformat(),mock)); c.commit()
   flash(f'VPS {name} created successfully.')
  except sqlite3.IntegrityError: flash('A VPS with that name already exists.')
  except Exception as exc: flash(f'VPS creation failed: {str(exc)[:300]}')
  return redirect(url_for('vps_list'))
 body='<div class="hero"><div class="title">Create VPS</div><p class="muted">Codespaces automatically use mock mode.</p></div><div class="card"><form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"><label>Name</label><input name="name" pattern="[A-Za-z0-9_.-]{1,63}" maxlength="63" required><label>RAM (MB)</label><input name="ram" type="number" min="512" max="1048576" value="1024" required><label>CPU</label><input name="cpu" type="number" min="1" max="128" value="1" required><label>Disk (GB)</label><input name="disk" type="number" min="5" max="16384" value="10" required><label>Temporary root password</label><input name="password" type="password" minlength="12" required><button>Create VPS</button></form></div>'
 return render_template_string(LAYOUT,title='Create VPS',body=body)
def do_action(vps_id,op):
 with db() as c: r=c.execute("SELECT * FROM vps WHERE id=? AND status!='deleted'",(vps_id,)).fetchone()
 if not r: flash('VPS not found.'); return redirect(url_for('vps_list'))
 try:
  if not r['mock'] and not CODESPACE: {'start':kvm_start,'stop':kvm_stop,'reboot':kvm_reboot}[op](r['container_name'])
  status={'start':'running','stop':'stopped','reboot':'running'}[op]
  with db() as c: c.execute('UPDATE vps SET status=? WHERE id=?',(status,vps_id)); c.commit()
  flash(f'{r["container_name"]}: {status}')
 except Exception as exc: flash(f'{op.title()} failed: {str(exc)[:300]}')
 return redirect(url_for('vps_list'))
@app.post('/vps/<int:vps_id>/start')
@admin_required
def vps_start(vps_id): return do_action(vps_id,'start')
@app.post('/vps/<int:vps_id>/stop')
@admin_required
def vps_stop(vps_id): return do_action(vps_id,'stop')
@app.post('/vps/<int:vps_id>/reboot')
@admin_required
def vps_reboot(vps_id): return do_action(vps_id,'reboot')
@app.post('/vps/<int:vps_id>/delete')
@admin_required
def vps_delete(vps_id):
 with db() as c: r=c.execute("SELECT * FROM vps WHERE id=? AND status!='deleted'",(vps_id,)).fetchone()
 if not r: flash('VPS not found.'); return redirect(url_for('vps_list'))
 try:
  if not r['mock'] and not CODESPACE and kvm_delete: kvm_delete(r['container_name'])
  with db() as c: c.execute("UPDATE vps SET status='deleted' WHERE id=?",(vps_id,)); c.commit()
  flash(f'{r["container_name"]} deleted.')
 except Exception as exc: flash(f'Delete failed: {str(exc)[:300]}')
 return redirect(url_for('vps_list'))
@app.route('/nodes',methods=['GET','POST'])
@admin_required
def nodes():
 if request.method=='POST':
  try:
   name=request.form.get('name','').strip(); location=request.form.get('location','Remote').strip() or 'Remote'; uri=request.form.get('url','').strip(); storage=request.form.get('storage','/var/lib/libvirt/images').strip() or '/var/lib/libvirt/images'
   if not name: raise ValueError('Node name is required')
   with db() as c: c.execute('INSERT INTO nodes(name,location,url,is_local,storage) VALUES(?,?,?,?,?)',(name,location,uri,int(not bool(uri)),storage)); c.commit()
   flash('Node added.')
  except Exception as exc: flash(f'Node creation failed: {str(exc)[:250]}')
  return redirect(url_for('nodes'))
 with db() as c: rs=c.execute('SELECT * FROM nodes ORDER BY id').fetchall()
 body='<div class="hero"><div class="title">Nodes</div><p class="muted">Remote metadata is supported; deployment still requires node-local KVM storage.</p></div><div class="card"><form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"><label>Name</label><input name="name" required><label>Location</label><input name="location" value="Remote"><label>Libvirt URI</label><input name="url" placeholder="qemu+ssh://..."><label>Storage</label><input name="storage" value="/var/lib/libvirt/images"><button>Add Node</button></form></div><div class="card"><table class="table"><tr><th>ID</th><th>Name</th><th>Location</th><th>Type</th><th>URI</th></tr>'+''.join(f"<tr><td>{r['id']}</td><td>{r['name']}</td><td>{r['location']}</td><td>{'Local' if r['is_local'] else 'Remote'}</td><td>{r['url'] or '-'}</td></tr>" for r in rs)+'</table></div>'
 return render_template_string(LAYOUT,title='Nodes',body=body)
@app.get('/bot')
@admin_required
def bot():
 configured=bool(os.getenv('DISCORD_TOKEN','').strip()); body=f'<div class="hero"><div class="title">Discord Bot</div><p class="muted">Integration status.</p></div><div class="card"><div class="value {"ok" if configured else "bad"}">{"CONFIGURED" if configured else "NOT CONFIGURED"}</div><p class="muted">Set DISCORD_TOKEN as a secret/environment variable.</p></div>'
 return render_template_string(LAYOUT,title='Bot',body=body)
init_db()
if __name__=='__main__': app.run(host=os.getenv('SNCK_PANEL_HOST','0.0.0.0'),port=PORT,debug=False)
