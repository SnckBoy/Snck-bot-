#!/usr/bin/env python3
import os, secrets, sqlite3, subprocess, sys
from functools import wraps
from pathlib import Path
from flask import Flask, request, redirect, url_for, session, render_template_string, flash

APP_DIR = Path(__file__).resolve().parent
DB = APP_DIR / "panel.db"
ENV = APP_DIR / ".env"
app = Flask(__name__)
app.secret_key = os.environ.get("SNCK_PANEL_SECRET", secrets.token_hex(32))
CSS = """<style>:root{--bg:#080912;--card:#111426;--line:#252a44;--text:#f4f6ff;--muted:#8f96b2;--a:#55e6ff;--b:#a66cff;--ok:#54e39b;--bad:#ff667f}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0%,#171633 0,#080912 38%);color:var(--text);font-family:Inter,system-ui,Arial,sans-serif}.wrap{max-width:1100px;margin:auto;padding:28px}.nav{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border:1px solid var(--line);background:#0d1020d9;border-radius:18px;backdrop-filter:blur(18px)}.brand{font-weight:800;letter-spacing:.12em}.brand span{color:var(--a)}a{color:var(--a);text-decoration:none}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-top:20px}.card{background:linear-gradient(145deg,#14182b,#0e1120);border:1px solid var(--line);border-radius:20px;padding:22px;box-shadow:0 16px 50px #0005}.title{font-size:30px;font-weight:800;margin:30px 0 8px}.muted{color:var(--muted)}.value{font-size:25px;font-weight:800;margin-top:8px}.status{color:var(--ok);font-weight:700}label{display:block;color:var(--muted);margin:14px 0 7px}input{width:100%;padding:13px 14px;border-radius:12px;border:1px solid var(--line);background:#080b16;color:var(--text);outline:none}input:focus{border-color:var(--a)}button{border:0;border-radius:12px;padding:13px 18px;background:linear-gradient(100deg,var(--a),var(--b));color:#05060c;font-weight:800;cursor:pointer;margin-top:18px}.flash{padding:12px;border-radius:12px;background:#151a30;margin:12px 0}.login{max-width:470px;margin:10vh auto}.small{font-size:13px}.actions{display:flex;gap:10px;flex-wrap:wrap}.actions button{margin:0}</style>"""
LAYOUT="""<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>{{title}} · Snck</title>"""+CSS+"""</head><body><div class=wrap><div class=nav><div class=brand>SNCK <span>KVM PANEL</span></div>{% if session.get('admin') %}<div><a href='/'>Dashboard</a> &nbsp; <a href='/bot'>Discord Bot</a> &nbsp; <a href='/logout'>Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>"""
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 c=db(); c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
 if c.execute("SELECT 1 FROM settings WHERE key='license'").fetchone() is None: c.execute('INSERT INTO settings(key,value) VALUES(?,?)',('license','SNCK-'+secrets.token_hex(4).upper()+'-'+secrets.token_hex(4).upper()+'-'+secrets.token_hex(4).upper()))
 for k,v in [('admin_user','admin'),('admin_pass',''),('license_active','0')]:
  if c.execute('SELECT 1 FROM settings WHERE key=?',(k,)).fetchone() is None: c.execute('INSERT INTO settings(key,value) VALUES(?,?)',(k,v))
 c.commit(); c.close()
def setting(k):
 c=db(); r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone(); c.close(); return r['value'] if r else ''
def set_setting(k,v):
 c=db(); c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v)); c.commit(); c.close()
def env_values():
 vals={}
 if ENV.exists():
  for line in ENV.read_text().splitlines():
   if '=' in line and not line.lstrip().startswith('#'):
    k,v=line.split('=',1); vals[k]=v.strip().strip('"').strip("'")
 return vals
def write_env(values):
 old=env_values(); old.update(values); ENV.write_text('\n'.join(f'{k}={v}' for k,v in old.items())+'\n'); os.chmod(ENV,0o600)
def bot_running():
 try: return bool(subprocess.run(['pgrep','-f',str(APP_DIR/'launcher.py')],capture_output=True,text=True).stdout.strip())
 except Exception: return False
def auth(f):
 @wraps(f)
 def w(*a,**kw):
  if setting('license_active')!='1': return redirect(url_for('license'))
  if not session.get('admin'): return redirect(url_for('login'))
  return f(*a,**kw)
 return w
@app.route('/license',methods=['GET','POST'])
def license():
 init_db()
 if request.method=='POST' and secrets.compare_digest(request.form.get('license','').strip(),setting('license')): set_setting('license_active','1'); return redirect(url_for('setup'))
 if request.method=='POST': flash('License key is invalid.')
 body=f'''<div class=login><div class=card><div class=title>Activate Snck License</div><p class=muted>Enter the license generated for this panel installation.</p><form method=post><label>License Key</label><input name=license placeholder="SNCK-XXXX-XXXX-XXXX" required><button>Activate License</button></form><p class=small muted>Installation license: <b>{setting('license')}</b></p></div></div>'''
 return render_template_string(LAYOUT,title='License',body=body)
@app.route('/setup',methods=['GET','POST'])
def setup():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if setting('admin_pass'): return redirect(url_for('login'))
 if request.method=='POST':
  u=request.form.get('username','admin').strip() or 'admin'; p=request.form.get('password','')
  if len(p)<8: flash('Administrator password must be at least 8 characters.')
  else: set_setting('admin_user',u); set_setting('admin_pass',p); return redirect(url_for('login'))
 body='''<div class=login><div class=card><div class=title>Create Administrator</div><p class=muted>Your panel administrator account is created once during first setup.</p><form method=post><label>Username</label><input name=username value=admin required><label>Password</label><input type=password name=password minlength=8 required><button>Create Admin Account</button></form></div></div>'''
 return render_template_string(LAYOUT,title='Admin Setup',body=body)
@app.route('/login',methods=['GET','POST'])
def login():
 init_db()
 if setting('license_active')!='1': return redirect(url_for('license'))
 if not setting('admin_pass'): return redirect(url_for('setup'))
 if request.method=='POST':
  if secrets.compare_digest(request.form.get('username',''),setting('admin_user')) and secrets.compare_digest(request.form.get('password',''),setting('admin_pass')): session['admin']=True; return redirect(url_for('index'))
  flash('Invalid administrator credentials.')
 body='''<div class=login><div class=card><div class=title>Administrator Login</div><p class=muted>SNCK KVM Panel</p><form method=post><label>Username</label><input name=username required><label>Password</label><input type=password name=password required><button>Sign in</button></form></div></div>'''
 return render_template_string(LAYOUT,title='Login',body=body)
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
@app.route('/')
@auth
def index():
 kvm='ENABLED' if Path('/dev/kvm').exists() else 'UNAVAILABLE'; bot='ONLINE' if bot_running() else 'OFFLINE'
 body=f'''<div class=title>Dashboard</div><p class=muted>SNCK KVM virtualization and Discord VPS deployment control.</p><div class=grid><div class=card><div class=muted>Panel</div><div class=value><span class=status>ONLINE</span></div></div><div class=card><div class=muted>License</div><div class=value>ACTIVE</div></div><div class=card><div class=muted>KVM</div><div class=value>{kvm}</div></div><div class=card><div class=muted>Discord Bot</div><div class=value>{bot}</div></div></div><div class=card style="margin-top:20px"><h2>Discord VPS Deploy Bot</h2><p class=muted>Create and configure the bot from this panel. VPS/KVM orchestration can be connected through the node backend.</p><div class=actions><a href="/bot"><button>Configure Discord Bot</button></a></div></div>'''
 return render_template_string(LAYOUT,title='Dashboard',body=body)
@app.route('/bot',methods=['GET','POST'])
@auth
def bot():
 if request.method=='POST':
  token=request.form.get('token','').strip()
  if not token: flash('Bot token cannot be empty.'); return redirect(url_for('bot'))
  write_env({'DISCORD_TOKEN':token,'BOT_NAME':request.form.get('name','Snck Deploy').strip() or 'Snck Deploy','PREFIX':request.form.get('prefix','!').strip() or '!'})
  subprocess.run(['pkill','-f',str(APP_DIR/'launcher.py')],capture_output=True)
  log=open(APP_DIR/'bot-panel.log','a'); subprocess.Popen([str(APP_DIR/'venv/bin/python'),str(APP_DIR/'launcher.py')],cwd=APP_DIR,stdout=log,stderr=log,start_new_session=True)
  flash('Discord bot configuration saved.'); return redirect(url_for('bot'))
 vals=env_values(); body=f'''<div class=title>Discord VPS Deploy Bot</div><p class=muted>Configure your bot without putting its token into the installer command.</p><div class=card><form method=post><label>Bot Name</label><input name=name value="{vals.get('BOT_NAME','Snck Deploy')}"><label>Command Prefix</label><input name=prefix value="{vals.get('PREFIX','!')}"><label>Discord Bot Token</label><input type=password name=token placeholder="Discord bot token" required><button>Save & Start Bot</button></form></div>'''
 return render_template_string(LAYOUT,title='Discord Bot',body=body)

def bootstrap():
 init_db()
 # Generate an administrator password for first login and print only to the terminal.
 if not setting('admin_pass'):
  password=secrets.token_urlsafe(12); set_setting('admin_pass',password); set_setting('admin_user','admin')
 else: password='(existing password preserved)'
 print('SNCK_LICENSE='+setting('license')); print('SNCK_ADMIN_USER='+setting('admin_user')); print('SNCK_ADMIN_PASSWORD='+password)
if __name__=='__main__':
 if '--bootstrap' in sys.argv: bootstrap(); raise SystemExit(0)
 init_db(); app.run(host='0.0.0.0',port=int(os.environ.get('SNCK_PANEL_PORT','5000')))
