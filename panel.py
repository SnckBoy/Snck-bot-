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

CSS = """
<style>
:root{--bg:#080912;--card:#111426;--line:#252a44;--text:#f4f6ff;--muted:#8f96b2;--a:#55e6ff;--b:#a66cff;--ok:#54e39b;--bad:#ff667f}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0%,#171633 0,#080912 38%);color:var(--text);font-family:Inter,system-ui,Arial,sans-serif}.wrap{max-width:1100px;margin:auto;padding:28px}.nav{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border:1px solid var(--line);background:#0d1020d9;border-radius:18px;backdrop-filter:blur(18px)}.brand{font-weight:800;letter-spacing:.12em}.brand span{color:var(--a)}a{color:var(--a);text-decoration:none}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-top:20px}.card{background:linear-gradient(145deg,#14182b,#0e1120);border:1px solid var(--line);border-radius:20px;padding:22px;box-shadow:0 16px 50px #0005}.title{font-size:30px;font-weight:800;margin:30px 0 8px}.muted{color:var(--muted)}.value{font-size:25px;font-weight:800;margin-top:8px}.status{color:var(--ok);font-weight:700}.danger{color:var(--bad)}label{display:block;color:var(--muted);margin:14px 0 7px}input{width:100%;padding:13px 14px;border-radius:12px;border:1px solid var(--line);background:#080b16;color:var(--text);outline:none}input:focus{border-color:var(--a)}button{border:0;border-radius:12px;padding:13px 18px;background:linear-gradient(100deg,var(--a),var(--b));color:#05060c;font-weight:800;cursor:pointer;margin-top:18px}.flash{padding:12px;border-radius:12px;background:#151a30;margin:12px 0}.login{max-width:470px;margin:10vh auto}.small{font-size:13px}.actions{display:flex;gap:10px;flex-wrap:wrap}.actions button{margin:0}.table{width:100%;border-collapse:collapse}.table td{padding:12px;border-bottom:1px solid var(--line)}
</style>"""

LAYOUT = """<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>{{title}} · Snck</title>"""+CSS+"""</head><body><div class=wrap><div class=nav><div class=brand>SNCK <span>KVM PANEL</span></div>{% if session.get('admin') %}<div><a href='/'>Dashboard</a> &nbsp; <a href='/bot'>Discord Bot</a> &nbsp; <a href='/logout'>Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>"""


def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db(); c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)'); c.commit()
    if c.execute("SELECT 1 FROM settings WHERE key='license'").fetchone() is None:
        lic='SNCK-'+secrets.token_hex(4).upper()+'-'+secrets.token_hex(4).upper()+'-'+secrets.token_hex(4).upper()
        c.execute('INSERT INTO settings(key,value) VALUES(?,?)',('license',lic))
    if c.execute("SELECT 1 FROM settings WHERE key='admin_user'").fetchone() is None:
        c.execute('INSERT INTO settings(key,value) VALUES(?,?)',('admin_user','admin'))
    if c.execute("SELECT 1 FROM settings WHERE key='admin_pass'").fetchone() is None:
        c.execute('INSERT INTO settings(key,value) VALUES(?,?)',('admin_pass',''))
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
    old=env_values(); old.update(values)
    ENV.write_text('\n'.join(f'{k}={v}' for k,v in old.items())+'\n'); os.chmod(ENV,0o600)

def bot_running():
    try:
        out=subprocess.run(['pgrep','-f',str(APP_DIR/'launcher.py')],capture_output=True,text=True)
        return bool(out.stdout.strip())
    except Exception: return False

def auth(f):
    @wraps(f)
    def w(*a,**kw):
        if not session.get('admin'): return redirect(url_for('login'))
        if not setting('license_active')=='1': return redirect(url_for('license'))
        return f(*a,**kw)
    return w

@app.route('/login',methods=['GET','POST'])
def login():
    init_db()
    if request.method=='POST':
        if request.form.get('username')==setting('admin_user') and request.form.get('password')==setting('admin_pass') and setting('admin_pass'):
            session['admin']=True; return redirect(url_for('index'))
        flash('Invalid administrator credentials.')
    body='''<div class=login><div class=card><div class=title>Administrator Login</div><p class=muted>SNCK KVM Panel</p><form method=post><label>Username</label><input name=username autocomplete=username required><label>Password</label><input type=password name=password autocomplete=current-password required><button>Sign in</button></form></div></div>'''
    return render_template_string(LAYOUT,title='Login',body=body)

@app.route('/license',methods=['GET','POST'])
def license():
    init_db()
    if request.method=='POST':
        if secrets.compare_digest(request.form.get('license','').strip(),setting('license')):
            set_setting('license_active','1'); flash('Snck license activated.'); return redirect(url_for('setup'))
        flash('License key is invalid.')
    body=f'''<div class=login><div class=card><div class=title>Activate Snck License</div><p class=muted>Enter the license issued for this installation.</p><form method=post><label>License Key</label><input name=license placeholder="SNCK-XXXX-XXXX-XXXX" required><button>Activate License</button></form><p class=small muted>Installation license: <b>{setting('license')}</b></p></div></div>'''
    return render_template_string(LAYOUT,title='License',body=body)

@app.route('/setup',methods=['GET','POST'])
def setup():
    init_db()
    if setting('license_active')=='1' and setting('admin_pass'): return redirect(url_for('login'))
    if request.method=='POST':
        u=request.form.get('username','admin').strip(); p=request.form.get('password','')
        if len(p)<8: flash('Administrator password must be at least 8 characters.')
        else:
            set_setting('admin_user',u or 'admin'); set_setting('admin_pass',p); flash('Administrator account created.'); return redirect(url_for('login'))
    body='''<div class=login><div class=card><div class=title>First-time Setup</div><p class=muted>Create the administrator account for this panel.</p><form method=post><label>Admin Username</label><input name=username value=admin required><label>Admin Password</label><input type=password name=password minlength=8 required><button>Create Admin</button></form></div></div>'''
    return render_template_string(LAYOUT,title='Setup',body=body)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
@auth
def index():
    body='''<div class=title>Dashboard</div><p class=muted>Premium KVM virtualization and Discord VPS deployment control.</p><div class=grid><div class=card><div class=muted>Panel</div><div class=value><span class=status>ONLINE</span></div></div><div class=card><div class=muted>License</div><div class=value>ACTIVE</div></div><div class=card><div class=muted>KVM</div><div class=value>''' + ('ENABLED' if Path('/dev/kvm').exists() else 'UNAVAILABLE') + '''</div></div><div class=card><div class=muted>Discord Bot</div><div class=value>''' + ('ONLINE' if bot_running() else 'OFFLINE') + '''</div></div></div><div class=card style="margin-top:20px"><h2>VPS Deployment</h2><p class=muted>Node and VM orchestration controls are available here as the backend is configured.</p><div class=actions><a href="/bot"><button>Configure Discord Bot</button></a></div></div>'''
    return render_template_string(LAYOUT,title='Dashboard',body=body)

@app.route('/bot',methods=['GET','POST'])
@auth
def bot():
    if request.method=='POST':
        token=request.form.get('token','').strip()
        if not token: flash('Bot token cannot be empty.'); return redirect(url_for('bot'))
        write_env({'DISCORD_TOKEN':token,'BOT_NAME':request.form.get('name','Snck Deploy').strip() or 'Snck Deploy','PREFIX':request.form.get('prefix','!').strip() or '!'})
        try:
            subprocess.run(['pkill','-f',str(APP_DIR/'launcher.py')],capture_output=True)
        except Exception: pass
        log=open(APP_DIR/'bot-panel.log','a')
        subprocess.Popen([str(APP_DIR/'venv/bin/python'),str(APP_DIR/'launcher.py')],cwd=APP_DIR,stdout=log,stderr=log,start_new_session=True)
        flash('Discord bot configuration saved and launch requested.')
        return redirect(url_for('bot'))
    vals=env_values(); body=f'''<div class=title>Discord VPS Deploy Bot</div><p class=muted>Configure the bot from the panel instead of entering the token in the installer.</p><div class=card><form method=post><label>Bot Name</label><input name=name value="{vals.get('BOT_NAME','Snck Deploy')}"><label>Command Prefix</label><input name=prefix value="{vals.get('PREFIX','!')}"><label>Discord Bot Token</label><input type=password name=token placeholder="Paste token here" required><button>Save & Start Bot</button></form></div>'''
    return render_template_string(LAYOUT,title='Discord Bot',body=body)

if __name__=='__main__':
    init_db(); app.run(host='0.0.0.0',port=int(os.environ.get('SNCK_PANEL_PORT','5000')))
