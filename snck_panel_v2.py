#!/usr/bin/env python3
from __future__ import annotations
import os, sqlite3, hashlib, secrets, html, subprocess, time
from pathlib import Path
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from kvm import kvm_available, tools_ok, state, ip, start, stop, reboot, create as kvm_create, delete as kvm_delete

BASE=Path(__file__).resolve().parent
DB=BASE/'vps.db'
USERS=BASE/'panel_users.db'
PORT=int(os.getenv('SNCK_PANEL_PORT','5000'))
MASTER_LICENSE='official.snck.fun'
app=Flask(__name__)
app.secret_key=os.getenv('SNCK_PANEL_SECRET') or secrets.token_hex(32)

CSS='''<style>
:root{--card:#ffffff;--ring:#a78bfa;--input:#e9d8fd;--muted:#f3e8ff;--accent:#f3e5f5;--border:#e9d8fd;--radius:1.5rem;--chart-1:#a78bfa;--chart-2:#8b5cf6;--chart-3:#7c3aed;--chart-4:#6d28d9;--chart-5:#5b21b6;--popover:#ffffff;--primary:#a78bfa;--sidebar:#e9d8fd;--font-mono:IBM Plex Mono,monospace;--font-sans:Open Sans,sans-serif;--secondary:#e9d8fd;--background:#f7f3f9;--foreground:#374151;--destructive:#fca5a5;--shadow-blur:16px;--shadow-opacity:.08;--sidebar-ring:#a78bfa;--shadow-offset-y:8px;--sidebar-accent:#f3e5f5;--sidebar-border:#e9d8fd;--card-foreground:#374151;--sidebar-primary:#a78bfa;--muted-foreground:#6b7280;--accent-foreground:#374151;--popover-foreground:#374151;--primary-foreground:#ffffff;--sidebar-foreground:#374151;--secondary-foreground:#4b5563;--destructive-foreground:#ffffff}
.dark{--card:#2d2535;--ring:#c0aafd;--input:#3f324a;--muted:#20182b;--accent:#4a3d5a;--border:#3f324a;--popover:#2d2535;--primary:#c0aafd;--sidebar:#3f324a;--secondary:#3f324a;--background:#1c1917;--foreground:#e0e7ff;--destructive:#fca5a5;--sidebar-ring:#c0aafd;--sidebar-accent:#4a3d5a;--sidebar-border:#3f324a;--card-foreground:#e0e7ff;--sidebar-primary:#c0aafd;--muted-foreground:#9ca3af;--accent-foreground:#d1d5db;--popover-foreground:#e0e7ff;--primary-foreground:#1c1917;--sidebar-foreground:#e0e7ff;--secondary-foreground:#d1d5db;--destructive-foreground:#1c1917}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 8% 0%,#eee4ff 0,#f7f3f9 38%,#fff 100%);color:var(--foreground);font:15px var(--font-sans),system-ui,Arial,sans-serif;min-height:100vh}.wrap{max-width:1240px;margin:auto;padding:24px}.nav{display:flex;gap:18px;justify-content:space-between;align-items:center;padding:16px 20px;border:1px solid var(--border);background:rgba(255,255,255,.84);border-radius:var(--radius);backdrop-filter:blur(18px);position:sticky;top:14px;z-index:5;box-shadow:0 8px 16px rgba(0,0,0,.08)}.brand{font-weight:900;letter-spacing:.12em}.brand span{color:var(--primary)}a{color:#7c3aed;text-decoration:none}.links{display:flex;gap:7px;flex-wrap:wrap}.links a{padding:9px 12px;border-radius:12px;color:var(--secondary-foreground)}.links a:hover{background:var(--accent);color:#6d28d9}.hero{margin:30px 0 22px}.title{font-size:32px;font-weight:900;margin:0 0 7px;letter-spacing:-.025em}.muted{color:var(--muted-foreground)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}.card{background:rgba(255,255,255,.9);border:1px solid var(--border);border-radius:var(--radius);padding:21px;box-shadow:0 8px 16px rgba(0,0,0,.08);transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease}.card:hover{transform:translateY(-2px);border-color:var(--ring);box-shadow:0 12px 28px rgba(124,58,237,.1)}.value{font-size:25px;font-weight:900;margin-top:8px}.ok{color:#16a34a}.bad{color:#dc2626}.warn{color:#b45309}label{display:block;color:var(--muted-foreground);margin:12px 0 6px;font-weight:650}input,select{width:100%;padding:12px 13px;border-radius:12px;border:1px solid var(--input);background:#fff;color:var(--foreground);outline:0;margin-bottom:8px}input:focus,select:focus{border-color:var(--ring);box-shadow:0 0 0 3px rgba(167,139,250,.18)}button{border:0;border-radius:12px;padding:11px 16px;background:linear-gradient(100deg,var(--primary),#8b5cf6);color:#fff;font-weight:850;cursor:pointer;box-shadow:0 8px 18px rgba(139,92,246,.18);transition:transform .15s ease,box-shadow .15s ease}button:hover{transform:translateY(-1px);box-shadow:0 11px 24px rgba(139,92,246,.24)}.secondary{background:var(--secondary);color:var(--foreground);border:1px solid var(--border);box-shadow:none}.danger{background:linear-gradient(100deg,#fca5a5,#c084fc)}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}.flash{padding:13px 15px;border:1px solid var(--border);background:var(--accent);border-radius:14px;margin:12px 0}.table{width:100%;border-collapse:collapse;background:rgba(255,255,255,.5)}.table th,.table td{text-align:left;padding:13px;border-bottom:1px solid var(--border)}.table th{color:var(--muted-foreground);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:var(--muted);border:1px solid var(--border);font-size:12px}.login{max-width:470px;margin:9vh auto}.code{font-family:var(--font-mono);background:var(--background);border:1px solid var(--border);padding:13px;border-radius:14px;overflow:auto}.stat{min-height:120px}.small{font-size:12px}.pill{display:inline-block;padding:5px 10px;border-radius:999px;background:var(--muted);border:1px solid var(--border)}
@media(max-width:700px){.wrap{padding:12px}.nav{position:static}.title{font-size:26px}.table{font-size:13px;display:block;overflow:auto}.links{gap:4px}.links a{padding:8px 9px}}
</style>'''
LAYOUT='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#a78bfa"><title>{{title}} · Snck</title>'''+CSS+'''</head><body><div class="wrap"><div class="nav"><div class="brand">SNCK <span>KVM PANEL</span></div>{% if session.get('role') %}<div class="links">{% if session.get('role')=='admin' %}<a href="/">Dashboard</a><a href="/vps">VPS</a><a href="/nodes">Nodes</a><a href="/bot">Discord Bot</a><a href="/license-info">License</a>{% else %}<a href="/">My VPS</a>{% endif %}<a href="/logout">Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>'''

def db(path=DB):
 c=sqlite3.connect(path,timeout=30);c.row_factory=sqlite3.Row;return c

def init_db():
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)''')
  c.execute('''CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,location TEXT,url TEXT,is_local INTEGER DEFAULT 1,storage TEXT NOT NULL DEFAULT '/var/lib/libvirt/images')''')
  c.execute('''CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,node_id INTEGER NOT NULL DEFAULT 1,container_name TEXT UNIQUE NOT NULL,ram TEXT NOT NULL,cpu TEXT NOT NULL,storage TEXT NOT NULL,config TEXT NOT NULL,os_version TEXT DEFAULT 'ubuntu:24.04',status TEXT DEFAULT 'stopped',suspended INTEGER DEFAULT 0,whitelisted INTEGER DEFAULT 0,created_at TEXT NOT NULL,shared_with TEXT DEFAULT '[]',expiration_date TEXT DEFAULT NULL,root_password TEXT DEFAULT NULL)''')
  if not c.execute("SELECT 1 FROM settings WHERE key='license'").fetchone(): c.execute('INSERT INTO settings VALUES(?,?)',( 'license',MASTER_LICENSE))
  for k,v in [('license_active','0'),('admin_user','admin'),('admin_pass','')]: c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(k,v))
  if not c.execute('SELECT 1 FROM nodes').fetchone(): c.execute("INSERT INTO nodes(name,location,url,is_local,storage) VALUES('Local KVM Node','Local','',1,'/var/lib/libvirt/images')")
 with db(USERS) as c:
  c.execute('''CREATE TABLE IF NOT EXISTS panel_users(discord_id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,password_once TEXT,created_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1)''')

def setting(k,default=''):
 with db() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return r['value'] if r else default

def set_setting(k,v):
 with db() as c:c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))

def user_for(discord_id):
 with db(USERS) as c:return c.execute('SELECT * FROM panel_users WHERE discord_id=? AND active=1',(str(discord_id),)).fetchone()

def admin_required(f):
 @wraps(f)
 def w(*a,**kw):
  init_db()
  if setting('license_active')!='1': return redirect(url_for('license'))
  if session.get('role')!='admin': return redirect(url_for('login'))
  return f(*a,**kw)
 return w

def user_required(f):
 @wraps(f)
 def w(*a,**kw):
  init_db()
  if setting('license_active')!='1': return redirect(url_for('license'))
  if session.get('role')!='user': return redirect(url_for('login'))
  return f(*a,**kw)
 return w

@app.route('/license',methods=['GET','POST'])
def license():
 init_db()
 if request.method=='POST':
  # The master license is fixed in code and cannot be edited from the panel.
  if secrets.compare_digest(request.form.get('license','').strip(),MASTER_LICENSE): set_setting('license_active','1'); return redirect(url_for('setup'))
  flash('License key is invalid.')
 body='''<div class="login"><div class="card"><div class="title">Activate Snck</div><p class="muted">Enter the Snck license to unlock this panel.</p><form method="post"><label>License</label><input name="license" placeholder="official.snck.fun" autocomplete="off" required><button>Activate License</button></form></div></div>'''
 return render_template_string(LAYOUT,title='License',body=body)

@app.route('/setup',methods=['GET','POST'])
def setup():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if setting('admin_pass'): return redirect(url_for('login'))
 if request.method=='POST':
  u=request.form.get('username','admin').strip() or 'admin';p=request.form.get('password','')
  if len(p)<8: flash('Password must be at least 8 characters.')
  else: set_setting('admin_user',u);set_setting('admin_pass',hashlib.sha256(p.encode()).hexdigest());return redirect(url_for('login'))
 body='''<div class="login"><div class="card"><div class="title">Create Administrator</div><p class="muted">Create the first Snck panel administrator.</p><form method="post"><label>Username</label><input name="username" value="admin" required><label>Password</label><input type="password" name="password" minlength="8" required><button>Create Admin Account</button></form></div></div>'''
 return render_template_string(LAYOUT,title='Admin Setup',body=body)

@app.route('/login',methods=['GET','POST'])
def login():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if request.method=='POST':
  u=request.form.get('username','');p=request.form.get('password','');h=hashlib.sha256(p.encode()).hexdigest()
  if u==setting('admin_user') and secrets.compare_digest(h,setting('admin_pass')): session.clear();session['role']='admin';session['uid']='admin';return redirect(url_for('index'))
  r=user_for(u)
  if r and secrets.compare_digest(h,r['password_hash']): session.clear();session['role']='user';session['uid']=r['discord_id'];session['username']=r['username'];return redirect(url_for('index'))
  flash('Invalid credentials.')
 body='''<div class="login"><div class="card"><div class="title">Snck KVM Panel</div><p class="muted">Sign in with your panel account. Discord-linked customers receive access through the connected bot.</p><form method="post"><label>Username</label><input name="username" required><label>Password</label><input type="password" name="password" required><button>Sign in</button></form></div></div>'''
 return render_template_string(LAYOUT,title='Login',body=body)

@app.route('/logout')
def logout(): session.clear();return redirect(url_for('login'))

@app.route('/')
def index():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if session.get('role')=='admin':
  with db() as c:
   nodes=c.execute('SELECT COUNT(*) n FROM nodes').fetchone()['n'];vps=c.execute('SELECT COUNT(*) n FROM vps WHERE status!=\'deleted\'').fetchone()['n'];online=c.execute("SELECT COUNT(*) n FROM vps WHERE status='running'").fetchone()['n']
  kvm='ENABLED' if kvm_available() else 'UNAVAILABLE';tool='READY' if tools_ok() else 'MISSING'
  body=f'''<div class="hero"><div class="title">Command Center</div><p class="muted">Premium KVM virtualization and Discord VPS deployment.</p></div><div class="grid"><div class="card stat"><div class="muted">KVM Nodes</div><div class="value">{nodes}</div></div><div class="card stat"><div class="muted">Total VPS</div><div class="value">{vps}</div></div><div class="card stat"><div class="muted">Online VPS</div><div class="value ok">{online}</div></div><div class="card stat"><div class="muted">KVM</div><div class="value {'ok' if kvm=='ENABLED' else 'bad'}">{kvm}</div></div><div class="card stat"><div class="muted">QEMU / libvirt</div><div class="value">{tool}</div></div></div><div class="grid"><div class="card"><h2>VPS Management</h2><p class="muted">Deploy and control real KVM virtual machines.</p><div class="actions"><a href="/vps"><button>Manage VPS</button></a><a href="/vps/create"><button class="secondary">Deploy VPS</button></a></div></div><div class="card"><h2>Discord Integration</h2><p class="muted">Connect the bot and keep Discord ownership synchronized with the panel.</p><a href="/bot"><button>Configure Bot</button></a></div></div>'''
  return render_template_string(LAYOUT,title='Dashboard',body=body)
 if session.get('role')=='user': return customer_vps()
 return redirect(url_for('login'))

def customer_vps():
 uid=str(session['uid'])
 with db() as c:rows=c.execute('SELECT * FROM vps WHERE user_id=? AND status!=\'deleted\' ORDER BY id DESC',(uid,)).fetchall()
 cards=''
 for r in rows:
  node=db().execute('SELECT * FROM nodes WHERE id=?',(r['node_id'],)).fetchone();uri=node['url'] if node and node['url'] else ''
  st=state(r['container_name'],uri);addr=ip(r['container_name'],uri)
  cards+=f'''<div class="card"><span class="pill">{html.escape(r['os_version'] or 'Ubuntu')}</span><div class="value">{html.escape(r['container_name'])}</div><p>Status: <span class="{'ok' if st=='running' else 'bad'}">{html.escape(st.upper())}</span></p><p class="muted">IPv4: {html.escape(addr or 'Detecting...')}</p><p class="muted">CPU {html.escape(str(r['cpu']))} · RAM {html.escape(str(r['ram']))} · Disk {html.escape(str(r['storage']))}</p><div class="actions"><form method="post" action="/my-vps/{r['id']}/start"><button>Start</button></form><form method="post" action="/my-vps/{r['id']}/stop"><button class="secondary">Stop</button></form><form method="post" action="/my-vps/{r['id']}/restart"><button class="secondary">Restart</button></form></div></div>'''
 body=f'''<div class="hero"><div class="title">My VPS</div><p class="muted">Your Discord-linked VPS instances.</p></div><div class="grid">{cards or '<div class="card"><div class="title">No VPS assigned</div><p class="muted">Your Discord account does not have a VPS yet.</p></div>'}</div>'''
 return render_template_string(LAYOUT,title='My VPS',body=body)

@app.route('/my-vps/<int:vid>/<action>',methods=['POST'])
@user_required
def my_action(vid,action):
 if action not in ('start','stop','restart'): flash('Unsupported VPS action.');return redirect(url_for('index'))
 with db() as c:
  r=c.execute('SELECT * FROM vps WHERE id=? AND user_id=? AND status!=\'deleted\'',(vid,str(session['uid']))).fetchone();n=c.execute('SELECT * FROM nodes WHERE id=?',(r['node_id'],)).fetchone() if r else None
 if not r: flash('VPS not found or access denied.');return redirect(url_for('index'))
 uri=n['url'] if n and n['url'] else ''
 try:
  {'start':start,'stop':stop,'restart':reboot}[action](r['container_name'],uri);flash(action.title()+' requested.')
 except Exception as e: flash('Operation failed: '+str(e)[:300])
 return redirect(url_for('index'))

@app.route('/vps')
@admin_required
def vps():
 with db() as c:rows=c.execute('SELECT * FROM vps WHERE status!=\'deleted\' ORDER BY id DESC').fetchall()
 trs=''.join(f'<tr><td>{html.escape(r["container_name"])}</td><td>{html.escape(r["user_id"])}</td><td>{html.escape(str(r["cpu"]))}</td><td>{html.escape(str(r["ram"]))}</td><td>{html.escape(str(r["storage"]))}</td><td>{html.escape(r["status"])}</td></tr>' for r in rows)
 body=f'''<div class="hero"><div class="title">VPS Instances</div><p class="muted">Create and assign a VPS to a Discord user.</p><a href="/vps/create"><button>Deploy New VPS</button></a></div><div class="card"><table class="table"><tr><th>Name</th><th>Discord User</th><th>CPU</th><th>RAM</th><th>Disk</th><th>Status</th></tr>{trs or '<tr><td colspan="6">No VPS instances.</td></tr>'}</table></div>'''
 return render_template_string(LAYOUT,title='VPS',body=body)

@app.route('/vps/create',methods=['GET','POST'])
@admin_required
def create_vps():
 with db() as c:nodes=c.execute('SELECT * FROM nodes ORDER BY id').fetchall()
 if request.method=='POST':
  try:
   uid=request.form['user_id'].strip();name=request.form['name'].strip();nid=int(request.form['node_id']);ram=int(request.form['ram']);cpu=int(request.form['cpu']);disk=int(request.form['disk']);osver=request.form.get('os_version','ubuntu:24.04');n=db().execute('SELECT * FROM nodes WHERE id=?',(nid,)).fetchone()
   if not uid or not name or not n: raise ValueError('Name, Discord user ID and node are required.')
   pw=secrets.token_urlsafe(12)
   kvm_create(name,ram,cpu,disk,pw,storage=n['storage'],uri=n['url'] or '')
   start(name,n['url'] or '')
   with db() as c:c.execute('INSERT INTO vps(user_id,node_id,container_name,ram,cpu,storage,config,os_version,status,created_at,root_password) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,nid,name,str(ram)+' MB',str(cpu),str(disk)+' GB','kvm',osver,'running',time.strftime('%Y-%m-%dT%H:%M:%SZ'),pw))
   flash('VPS deployed and assigned to Discord user '+uid+'.');return redirect(url_for('vps'))
  except Exception as e:flash('Deployment failed: '+str(e)[:500])
 opts=''.join(f'<option value="{n["id"]}">{html.escape(n["name"])}</option>' for n in nodes)
 body=f'''<div class="hero"><div class="title">Deploy KVM VPS</div><p class="muted">The Discord User ID becomes the VPS owner.</p></div><div class="card"><form method="post"><label>Discord User ID</label><input name="user_id" placeholder="123456789012345678" required><label>VPS Name</label><input name="name" placeholder="snck-vps-01" pattern="[A-Za-z0-9_.-]+" required><label>Node</label><select name="node_id" required>{opts}</select><label>Operating System</label><select name="os_version"><option value="ubuntu:24.04">Ubuntu 24.04 LTS</option></select><label>CPU Cores</label><input type="number" name="cpu" value="2" min="1" max="128" required><label>RAM MB</label><input type="number" name="ram" value="2048" min="512" max="1048576" required><label>Disk GB</label><input type="number" name="disk" value="20" min="5" max="16384" required><button>Deploy VPS</button></form></div>'''
 return render_template_string(LAYOUT,title='Deploy VPS',body=body)

@app.route('/nodes')
@admin_required
def nodes():
 with db() as c:rows=c.execute('SELECT * FROM nodes ORDER BY id').fetchall()
 cards=''.join(f'<div class="card"><div class="value">{html.escape(r["name"])}</div><p class="muted">{html.escape(r["location"] or "Local")}</p><p>Endpoint: <span class="code">{html.escape(r["url"] or "local libvirt")}</span></p><p>KVM: <span class="{"ok" if kvm_available() else "bad"}">{"ENABLED" if kvm_available() else "UNAVAILABLE"}</span></p></div>' for r in rows)
 return render_template_string(LAYOUT,title='Nodes',body='<div class="hero"><div class="title">KVM Nodes</div><p class="muted">Nodes available to the Snck deployment system.</p></div><div class="grid">'+cards+'</div>')

@app.route('/bot',methods=['GET','POST'])
@admin_required
def bot():
 if request.method=='POST':
  token=request.form.get('token','').strip()
  if token:
   env=BASE/'.env';lines=[]
   existing={}
   if env.exists():
    for line in env.read_text().splitlines():
     if '=' in line and not line.lstrip().startswith('#'):
      k,v=line.split('=',1);existing[k]=v
   existing['DISCORD_TOKEN']=token
   existing.setdefault('BOT_NAME','Snck Discord VPS Deploy Bot');existing.setdefault('PREFIX','!')
   env.write_text('\n'.join(f'{k}={v}' for k,v in existing.items())+'\n');os.chmod(env,0o600)
   flash('Discord bot token saved securely. Restart the bot service to apply it.')
  else: flash('Enter a bot token.')
 body='''<div class="hero"><div class="title">Discord Bot</div><p class="muted">Connect the Discord bot to this panel environment.</p></div><div class="card"><form method="post"><label>Discord Bot Token</label><input type="password" name="token" autocomplete="new-password" required><button>Save Bot Token</button></form><p class="muted small">The token is stored in the VPS .env file and is never displayed back in the panel.</p></div>'''
 return render_template_string(LAYOUT,title='Discord Bot',body=body)

@app.route('/license-info')
@admin_required
def license_info():
 body=f'''<div class="hero"><div class="title">Snck License</div><p class="muted">Master license configuration.</p></div><div class="card"><p>License: <span class="pill">{MASTER_LICENSE}</span></p><p>Status: <span class="{'ok' if setting('license_active')=='1' else 'bad'}">{'ACTIVE' if setting('license_active')=='1' else 'INACTIVE'}</span></p><p class="muted">The master license is fixed and cannot be changed by panel users.</p></div>'''
 return render_template_string(LAYOUT,title='License',body=body)

@app.get('/health')
def health():
 init_db();return {'panel':'ok','license':setting('license_active')=='1','kvm':kvm_available(),'tools':tools_ok()},200

if __name__=='__main__':
 init_db();app.run(host='0.0.0.0',port=PORT)
