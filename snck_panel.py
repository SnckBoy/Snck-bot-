#!/usr/bin/env python3
from __future__ import annotations
import os,secrets,sqlite3,hashlib,html
from pathlib import Path
from functools import wraps
from flask import Flask,request,redirect,url_for,session,render_template_string,flash
from kvm import kvm_available,tools_ok,state,ip,start,stop,reboot
BASE=Path(__file__).resolve().parent;DB=BASE/'vps.db';USERS=BASE/'panel_users.db'
PORT=int(os.getenv('SNCK_PANEL_PORT','5000'));MASTER_LICENSE='official.snck.fun'
app=Flask(__name__);app.secret_key=os.getenv('SNCK_PANEL_SECRET') or secrets.token_hex(32)
CSS='''<style>:root{--bg:#070811;--card:#101528;--line:#27304e;--text:#f5f7ff;--muted:#8d96b5;--a:#57e6ff;--b:#a970ff;--ok:#57e39b;--bad:#ff667f}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0%,#211b48,#070811 45%);color:var(--text);font:15px Inter,system-ui,Arial}.wrap{max-width:1200px;margin:auto;padding:20px}.nav{display:flex;justify-content:space-between;gap:18px;align-items:center;padding:15px 18px;background:#0c1120ed;border:1px solid var(--line);border-radius:18px;position:sticky;top:12px;z-index:3}.brand{font-weight:950;letter-spacing:.12em}.brand span{color:var(--a)}a{color:var(--a);text-decoration:none}.links{display:flex;gap:14px;flex-wrap:wrap}.hero{margin:30px 0}.title{font-size:32px;font-weight:900}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:15px;margin-top:18px}.card{background:linear-gradient(145deg,#12172a,#0b1020);border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:0 18px 55px #0007}.value{font-size:26px;font-weight:900;margin-top:7px}.ok{color:var(--ok)}.bad{color:var(--bad)}button{border:0;border-radius:11px;padding:11px 16px;background:linear-gradient(100deg,var(--a),var(--b));color:#05060c;font-weight:850;cursor:pointer}.secondary{background:#171d31;color:var(--text);border:1px solid var(--line)}input,select{width:100%;padding:12px;border-radius:11px;border:1px solid var(--line);background:#070a14;color:var(--text);margin:6px 0 13px}.actions{display:flex;gap:9px;flex-wrap:wrap}.flash{padding:12px;border:1px solid var(--line);border-radius:12px;background:#12182a;margin:12px 0}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:11px;border-bottom:1px solid var(--line)}.login{max-width:440px;margin:10vh auto}@media(max-width:700px){.wrap{padding:12px}.nav{position:static}.title{font-size:26px}}</style>'''
LAY='''<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>{{title}} · Snck</title>'''+CSS+'''</head><body><div class=wrap><div class=nav><div class=brand>SNCK <span>KVM PANEL</span></div>{% if session.get('role') %}<div class=links>{% if session.get('role')=='admin' %}<a href="/admin">Dashboard</a><a href="/vps">VPS</a><a href="/nodes">Nodes</a>{% else %}<a href="/">My VPS</a>{% endif %}<a href="/logout">Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>'''
def conn(p=DB):c=sqlite3.connect(p,timeout=30);c.row_factory=sqlite3.Row;return c
def init():
 with conn() as c:
  c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)');c.execute('CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,uri TEXT NOT NULL DEFAULT \'\',storage TEXT NOT NULL DEFAULT \'/var/lib/libvirt/images\')');c.execute('CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,node_id INTEGER NOT NULL,name TEXT UNIQUE NOT NULL,ram INTEGER NOT NULL,cpu INTEGER NOT NULL,disk INTEGER NOT NULL,status TEXT NOT NULL DEFAULT \'stopped\',ip TEXT DEFAULT \'\',created_at TEXT NOT NULL,root_password TEXT)')
  c.execute('INSERT OR IGNORE INTO settings VALUES(\'license\',?)',(MASTER_LICENSE,));c.execute('INSERT OR IGNORE INTO settings VALUES(\'license_active\',\'0\')');c.execute('INSERT OR IGNORE INTO settings VALUES(\'admin_user\',\'admin\')');c.execute('INSERT OR IGNORE INTO settings VALUES(\'admin_pass\',\'\')');c.execute('INSERT OR IGNORE INTO nodes(name,uri,storage) SELECT \'Local KVM Node\',\'\',\'/var/lib/libvirt/images\' WHERE NOT EXISTS(SELECT 1 FROM nodes)');c.commit()
 with conn(USERS) as c:c.execute('CREATE TABLE IF NOT EXISTS panel_users(discord_id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,password_once TEXT,created_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1)');c.commit()
def setting(k):
 with conn() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return r['value'] if r else ''
def set_setting(k,v):
 with conn() as c:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,v));c.commit()
def admin(f):
 @wraps(f)
 def w(*a,**kw):
  if setting('license_active')!='1':return redirect(url_for('license'))
  if session.get('role')!='admin':return redirect(url_for('login'))
  return f(*a,**kw)
 return w
def init_user(f):
 @wraps(f)
 def w(*a,**kw):
  if setting('license_active')!='1':return redirect(url_for('license'))
  if session.get('role')!='user':return redirect(url_for('login'))
  return f(*a,**kw)
 return w
@app.route('/license',methods=['GET','POST'])
def license():
 init()
 if request.method=='POST':
  # One fixed master license. It is not editable from the panel.
  if secrets.compare_digest(request.form.get('license','').strip(),MASTER_LICENSE):set_setting('license_active','1');return redirect(url_for('setup'))
  flash('Invalid Snck license.')
 return render_template_string(LAY,title='License',body='<div class=login><div class=card><div class=title>Snck License</div><p class=muted>Enter the license issued by Snck.</p><form method=post><input name=license placeholder="official.snck.fun" required><button>Activate License</button></form></div></div>')
@app.route('/setup',methods=['GET','POST'])
def setup():
 init()
 if setting('license_active')!='1':return redirect(url_for('license'))
 if setting('admin_pass'):return redirect(url_for('login'))
 if request.method=='POST':
  p=request.form.get('password','');u=request.form.get('username','admin').strip() or 'admin'
  if len(p)<8:flash('Password must be at least 8 characters.')
  else:set_setting('admin_user',u);set_setting('admin_pass',hashlib.sha256(p.encode()).hexdigest());return redirect(url_for('login'))
 return render_template_string(LAY,title='Admin Setup',body='<div class=login><div class=card><div class=title>Create Admin</div><form method=post><input name=username value=admin required><input type=password name=password minlength=8 placeholder="Minimum 8 characters" required><button>Create Admin</button></form></div></div>')
@app.route('/login',methods=['GET','POST'])
def login():
 init()
 if setting('license_active')!='1':return redirect(url_for('license'))
 if request.method=='POST':
  u=request.form.get('username','');p=request.form.get('password','');h=hashlib.sha256(p.encode()).hexdigest()
  if u==setting('admin_user') and secrets.compare_digest(h,setting('admin_pass')):session['role']='admin';session['uid']='admin';return redirect(url_for('admin_dashboard'))
  with conn(USERS) as c:r=c.execute('SELECT * FROM panel_users WHERE username=? AND active=1',(u,)).fetchone()
  if r and secrets.compare_digest(h,r['password_hash']):session['role']='user';session['uid']=r['discord_id'];return redirect(url_for('index'))
  flash('Invalid credentials.')
 return render_template_string(LAY,title='Login',body='<div class=login><div class=card><div class=title>Snck KVM Panel</div><p class=muted>Customers receive panel credentials through the connected Discord bot.</p><form method=post><input name=username placeholder="Username" required><input type=password name=password placeholder="Password" required><button>Sign in</button></form></div></div>')
@app.route('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.route('/')
@init_user
def index():
 with conn() as c:rows=c.execute('SELECT * FROM vps WHERE user_id=? ORDER BY id DESC',(str(session['uid']),)).fetchall()
 cards=''
 for r in rows:
  n=conn().execute('SELECT * FROM nodes WHERE id=?',(r['node_id'],)).fetchone();uri=n['uri'] if n else '';st=state(r['name'],uri);addr=ip(r['name'],uri)
  cards+=f'<div class=card><div class=muted>VPS</div><div class=value>{html.escape(r["name"])}</div><p>Status: <span class={"ok" if st=="running" else "bad"}>{st.upper()}</span></p><p class=muted>IPv4: {addr or "Detecting..."}</p><p class=muted>CPU {r["cpu"]} · RAM {r["ram"]} MB · Disk {r["disk"]} GB</p><div class=actions><form method=post action=/vps/{r["id"]}/start><button>Start</button></form><form method=post action=/vps/{r["id"]}/stop><button class=secondary>Stop</button></form><form method=post action=/vps/{r["id"]}/restart><button class=secondary>Restart</button></form></div></div>'
 return render_template_string(LAY,title='My VPS',body=f'<div class=hero><div class=title>My VPS</div><p class=muted>Discord-linked VPS access</p></div><div class=grid>{cards or "<div class=card>No VPS assigned yet.</div>"}</div>')
@app.route('/admin')
@admin
def admin_dashboard():
 with conn() as c:n=c.execute('SELECT COUNT(*) x FROM nodes').fetchone()['x'];v=c.execute('SELECT COUNT(*) x FROM vps').fetchone()['x'];o=c.execute("SELECT COUNT(*) x FROM vps WHERE status='running'").fetchone()['x']
 return render_template_string(LAY,title='Dashboard',body=f'<div class=hero><div class=title>Command Center</div><p class=muted>Snck KVM virtualization control</p></div><div class=grid><div class=card>Nodes<div class=value>{n}</div></div><div class=card>VPS<div class=value>{v}</div></div><div class=card>Online<div class=value ok>{o}</div></div><div class=card>KVM<div class=value>{"ENABLED" if kvm_available() else "UNAVAILABLE"}</div></div><div class=card>QEMU / libvirt<div class=value>{"READY" if tools_ok() else "MISSING"}</div></div></div>')
@app.route('/vps')
@admin
def vps():
 with conn() as c:rows=c.execute('SELECT * FROM vps ORDER BY id DESC').fetchall()
 trs=''.join(f'<tr><td>{html.escape(r["name"])}</td><td>{html.escape(r["user_id"])}</td><td>{r["cpu"]}</td><td>{r["ram"]} MB</td><td>{r["disk"]} GB</td><td>{html.escape(r["status"])}</td></tr>' for r in rows)
 return render_template_string(LAY,title='VPS',body=f'<div class=hero><div class=title>VPS Instances</div><a href=/vps/create><button>Deploy New VPS</button></a></div><div class=card><table class=table><tr><th>Name</th><th>Owner</th><th>CPU</th><th>RAM</th><th>Disk</th><th>Status</th></tr>{trs or "<tr><td colspan=6>No VPS.</td></tr>"}</table></div>')
@app.route('/vps/create',methods=['GET','POST'])
@admin
def create_vps():
 with conn() as c:nodes=c.execute('SELECT * FROM nodes').fetchall()
 if request.method=='POST':
  try:
   uid=request.form['user_id'].strip();name=request.form['name'].strip();nid=int(request.form['node_id']);ram=int(request.form['ram']);cpu=int(request.form['cpu']);disk=int(request.form['disk']);n=conn().execute('SELECT * FROM nodes WHERE id=?',(nid,)).fetchone();pw=secrets.token_urlsafe(12);vm_create=name,ram,cpu,disk,pw
   from kvm import create as real_create;real_create(name,ram,cpu,disk,pw,storage=n['storage'],uri=n['uri']);real_start= start;real_start(name,n['uri'])
   with conn() as c:c.execute('INSERT INTO vps(user_id,node_id,name,ram,cpu,disk,status,created_at,root_password) VALUES(?,?,?,?,?,?,?,?,?)',(uid,nid,name,ram,cpu,disk,'running',__import__('datetime').datetime.utcnow().isoformat(),pw));c.commit()
   flash('VPS created and assigned to the Discord user. The connected bot will see the same vps.db record.');return redirect(url_for('vps'))
  except Exception as e:flash('Deployment failed: '+str(e)[:500])
 opts=''.join(f'<option value={n["id"]}>{html.escape(n["name"])}</option>' for n in nodes)
 body=f'<div class=hero><div class=title>Deploy KVM VPS</div></div><div class=card><form method=post><label>Discord User ID</label><input name=user_id required><label>VPS Name</label><input name=name required><label>Node</label><select name=node_id>{opts}</select><label>CPU</label><input type=number name=cpu value=2 min=1><label>RAM MB</label><input type=number name=ram value=2048 min=512><label>Disk GB</label><input type=number name=disk value=20 min=5><button>Deploy VPS</button></form></div>'
 return render_template_string(LAY,title='Deploy VPS',body=body)
@app.route('/vps/<int:vid>/<action>',methods=['POST'])
@init_user
def user_action(vid,action):
 with conn() as c:r=c.execute('SELECT * FROM vps WHERE id=? AND user_id=?',(vid,str(session['uid']))).fetchone();n=c.execute('SELECT * FROM nodes WHERE id=?',(r['node_id'],)).fetchone() if r else None
 if not r:flash('VPS not found or access denied.');return redirect(url_for('index'))
 try:
  {'start':start,'stop':stop,'restart':reboot}[action](r['name'],n['uri'] if n else '');flash(f'{action.title()} requested.')
 except Exception as e:flash('Operation failed: '+str(e)[:300])
 return redirect(url_for('index'))
@app.route('/nodes')
@admin
def nodes():
 with conn() as c:rows=c.execute('SELECT * FROM nodes').fetchall()
 body='<div class=hero><div class=title>KVM Nodes</div></div><div class=grid>'+''.join(f'<div class=card><div class=value>{html.escape(r["name"])}</div><p>URI: {html.escape(r["uri"] or "local")}</p><p>KVM: {"ENABLED" if kvm_available() else "UNAVAILABLE"}</p></div>' for r in rows)+'</div>';return render_template_string(LAY,title='Nodes',body=body)
@app.route('/health')
def health():init();return {'panel':'online','license':'active' if setting('license_active')=='1' else 'required','kvm':kvm_available(),'libvirt':tools_ok()}
if __name__=='__main__':init();app.run(host='0.0.0.0',port=PORT,debug=False)
