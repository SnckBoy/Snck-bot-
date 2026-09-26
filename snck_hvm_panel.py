#!/usr/bin/env python3
from __future__ import annotations
import hmac, os, re, secrets, shutil
from functools import wraps
from flask import Flask, flash, redirect, render_template_string, request, session, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash
from vps_service import OS_OPTIONS, create_vps, db, delete_vps, get_ips, init_db, next_vps_id, reboot_vps, start_vps, stop_vps, vps_list

PORT=int(os.getenv('SNCK_PANEL_PORT','5000')); HOST=os.getenv('SNCK_PANEL_HOST','0.0.0.0'); LICENSE_KEY=os.getenv('SNCK_LICENSE_KEY','official.snck.fun'); TOKEN=os.getenv('DISCORD_TOKEN','').strip(); GUILD=os.getenv('DISCORD_GUILD_ID','').strip(); CODESPACE=os.getenv('SNCK_CODESPACE')=='1'
app=Flask(__name__); app.secret_key=os.getenv('SNCK_PANEL_SECRET') or secrets.token_hex(32); app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('SNCK_COOKIE_SECURE','0')=='1',MAX_CONTENT_LENGTH=64*1024)
CSS="""<style>*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0%,#211b48,#070811 45%);color:#f5f7ff;font:15px system-ui,Arial}.wrap{max-width:1250px;margin:auto;padding:20px}.nav,.card{background:#101528ee;border:1px solid #27304e;border-radius:18px;box-shadow:0 15px 45px #0006}.nav{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:15px 18px}.brand{font-weight:900;letter-spacing:.12em}.brand span{color:#57e6ff}.links{display:flex;gap:8px;flex-wrap:wrap}.links a{color:#57e6ff;text-decoration:none;padding:8px}.hero{margin:28px 0}.title{font-size:31px;font-weight:900}.muted{color:#8d96b5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:16px 0}.card{padding:20px;margin-bottom:14px}.value{font-size:25px;font-weight:900;margin-top:8px}.ok{color:#57e39b}.bad{color:#ff667f}label{display:block;margin:11px 0 5px;color:#8d96b5}input,select{width:100%;padding:11px;border:1px solid #27304e;border-radius:10px;background:#070a14;color:#fff;margin-bottom:8px}button{border:0;border-radius:10px;padding:10px 14px;background:linear-gradient(100deg,#57e6ff,#a970ff);color:#05060c;font-weight:800;cursor:pointer}.secondary{background:#171d31;color:#fff;border:1px solid #27304e}.danger{background:#7f3044;color:#fff}.actions{display:flex;gap:7px;flex-wrap:wrap}.flash{padding:12px;margin:12px 0;border:1px solid #27304e;border-radius:12px;background:#12182a}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:11px;border-bottom:1px solid #27304e;vertical-align:top}.login{max-width:460px;margin:9vh auto}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#171d31}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}@media(max-width:700px){.wrap{padding:12px}.nav{flex-direction:column;align-items:flex-start}.table{display:block;overflow:auto;white-space:nowrap}}</style>"""
LAYOUT="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{{title}} · Snck</title>"""+CSS+"""</head><body><div class='wrap'><div class='nav'><div class='brand'>SNCK <span>HVM PANEL</span></div>{% if session.get('role') %}<div class='links'><a href='/'>Dashboard</a><a href='/vps'>VPS</a><a href='/vps/create'>Create VPS</a><a href='/logout'>Logout</a></div>{% endif %}</div>{% with ms=get_flashed_messages() %}{% for m in ms %}<div class='flash'>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>"""
def panel_init():
    init_db()
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS panel_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        for k,v in [('license_active','0'),('admin_user','admin'),('admin_pass_hash','')]: c.execute('INSERT OR IGNORE INTO panel_settings(key,value) VALUES(?,?)',(k,v))
def setting(k,d=''):
    with db() as c:r=c.execute('SELECT value FROM panel_settings WHERE key=?',(k,)).fetchone()
    return r['value'] if r else d
def set_setting(k,v):
    with db() as c:c.execute('INSERT INTO panel_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
def csrf():
    if '_csrf' not in session:session['_csrf']=secrets.token_urlsafe(32)
    return session['_csrf']
@app.context_processor
def ctx():return {'csrf_token':csrf}
@app.before_request
def guard():
    if request.method=='POST' and request.endpoint not in {'license','setup','login'}:
        if not session.get('_csrf') or not hmac.compare_digest(request.form.get('_csrf',''),session['_csrf']):return 'CSRF validation failed',400
def auth(fn):
    @wraps(fn)
    def w(*a,**kw):
        panel_init()
        if setting('license_active')!='1':return redirect(url_for('license'))
        if session.get('role')!='admin':return redirect(url_for('login'))
        return fn(*a,**kw)
    return w
def discord_headers():return {'Authorization':f'Bot {TOKEN}','User-Agent':'Snck-HVM-Panel/1.0'}
def owner(identifier):
    import requests
    identifier=identifier.strip()
    if not TOKEN:
        if not identifier.isdigit():raise ValueError('Set DISCORD_TOKEN or enter a numeric Discord user ID.')
        return identifier,identifier
    if identifier.isdigit():
        r=requests.get(f'https://discord.com/api/v10/users/{identifier}',headers=discord_headers(),timeout=8)
        if r.status_code!=200:raise ValueError('Discord user ID was not found.')
        u=r.json();return identifier,u.get('global_name') or u.get('username') or identifier
    if not GUILD:raise ValueError('DISCORD_GUILD_ID is required for username lookup.')
    r=requests.get(f'https://discord.com/api/v10/guilds/{GUILD}/members/search',headers=discord_headers(),params={'query':identifier,'limit':25},timeout=8)
    if r.status_code!=200:raise ValueError(f'Discord member lookup failed: HTTP {r.status_code}')
    for m in r.json():
        u=m.get('user',{});names={u.get('username','').casefold(),u.get('global_name','').casefold()}
        if identifier.casefold() in names:return str(u['id']),u.get('global_name') or u.get('username') or identifier
    raise ValueError('Discord member was not found.')
def creator(v):return str(escape(v.get('owner_name') or v.get('user_id') or 'Unknown'))
@app.get('/health')
def health():panel_init();return {'status':'ok','panel':'snck-hvm','port':PORT,'codespace':CODESPACE,'lxc':bool(shutil.which('lxc'))}
@app.route('/license',methods=['GET','POST'])
def license():
    panel_init()
    if request.method=='POST':
        if hmac.compare_digest(request.form.get('license','').strip(),LICENSE_KEY):set_setting('license_active','1');return redirect(url_for('setup'))
        flash('License key is invalid.')
    return render_template_string(LAYOUT,title='License',body="<div class='login'><div class='card'><div class='title'>Activate Snck</div><form method='post'><input name='license' placeholder='License key' required><button>Activate</button></form></div></div>")
@app.route('/setup',methods=['GET','POST'])
def setup():
    panel_init()
    if setting('license_active')!='1':return redirect(url_for('license'))
    if setting('admin_pass_hash'):return redirect(url_for('login'))
    if request.method=='POST':
        u=request.form.get('username','admin').strip();p=request.form.get('password','')
        if len(u)<3 or len(u)>64:flash('Username must be 3-64 characters.')
        elif len(p)<10:flash('Password must be at least 10 characters.')
        else:set_setting('admin_user',u);set_setting('admin_pass_hash',generate_password_hash(p,method='scrypt'));return redirect(url_for('login'))
    return render_template_string(LAYOUT,title='Setup',body="<div class='login'><div class='card'><div class='title'>Create Administrator</div><form method='post'><input name='username' value='admin' required><input type='password' name='password' minlength='10' placeholder='Password' required><button>Create Admin</button></form></div></div>")
@app.route('/login',methods=['GET','POST'])
def login():
    panel_init()
    if setting('license_active')!='1':return redirect(url_for('license'))
    if not setting('admin_pass_hash'):return redirect(url_for('setup'))
    if request.method=='POST':
        if hmac.compare_digest(request.form.get('username',''),setting('admin_user')) and check_password_hash(setting('admin_pass_hash'),request.form.get('password','')):
            session.clear();session['role']='admin';session['_csrf']=secrets.token_urlsafe(32);return redirect(url_for('dashboard'))
        flash('Invalid credentials.')
    return render_template_string(LAYOUT,title='Login',body="<div class='login'><div class='card'><div class='title'>Snck HVM Panel</div><form method='post'><input name='username' placeholder='Username' required><input type='password' name='password' placeholder='Password' required><button>Sign in</button></form></div></div>")
@app.get('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.get('/')
@auth
def dashboard():
    rows=vps_list();run=sum(r['status']=='running' for r in rows);lxc=bool(shutil.which('lxc'))
    body=f"<div class='hero'><div class='title'>HVM Command Center</div><p class='muted'>Port {PORT} · {'Codespace test mode' if CODESPACE else 'host mode'} · Discord bot connected through shared vps.db.</p></div><div class='grid'><div class='card'>VPS<div class='value'>{len(rows)}</div></div><div class='card'>Running<div class='value ok'>{run}</div></div><div class='card'>Stopped<div class='value'>{len(rows)-run}</div></div><div class='card'>LXC<div class='value {'ok' if lxc else 'bad'}'>{'READY' if lxc else 'TEST MODE'}</div></div></div><div class='card'><a href='/vps/create'><button>Create Ubuntu VPS</button></a> <a href='/vps'><button class='secondary'>Manage VPS</button></a></div>"
    return render_template_string(LAYOUT,title='Dashboard',body=body)
@app.get('/vps')
@auth
def vps_page():
    trs=[]
    for r in vps_list():
        ips=get_ips(int(r['id']));ip=', '.join(ips) if ips else ('Mock/test network' if CODESPACE else 'IP unavailable')
        a=f"<div class='actions'><form method='post' action='/vps/{r['id']}/start'><input type='hidden' name='_csrf' value='{csrf()}'><button>Start</button></form><form method='post' action='/vps/{r['id']}/stop'><input type='hidden' name='_csrf' value='{csrf()}'><button class='secondary'>Stop</button></form><form method='post' action='/vps/{r['id']}/reboot'><input type='hidden' name='_csrf' value='{csrf()}'><button class='secondary'>Reboot</button></form><form method='post' action='/vps/{r['id']}/delete'><input type='hidden' name='_csrf' value='{csrf()}'><button class='danger'>Delete</button></form></div>"
        trs.append(f"<tr><td><b>#{r['id']} {escape(r['container_name'])}</b><br>{escape(r.get('os_version',''))}</td><td>{escape(r['ram'])} / {escape(r['cpu'])} CPU / {escape(r['storage'])}</td><td><span class='pill'>{escape(r['status'])}</span><br>{escape(ip)}</td><td>{creator(r)}<br><span class='mono'>{escape(r['user_id'])}</span></td><td>{a}</td></tr>")
    body="<div class='hero'><div class='title'>VPS</div><p class='muted'>Bot-created and panel-created VPS appear here from the same database.</p><a href='/vps/create'><button>Create VPS</button></a></div><div class='card'><table class='table'><tr><th>VPS</th><th>Resources</th><th>Status / IP</th><th>Discord owner</th><th>Actions</th></tr>"+("".join(trs) or "<tr><td colspan='5'>No VPS.</td></tr>")+"</table></div>"
    return render_template_string(LAYOUT,title='VPS',body=body)
@app.route('/vps/create',methods=['GET','POST'])
@auth
def create():
    if request.method=='POST':
        try:
            oid,oname=owner(request.form.get('discord_identifier',''));name=request.form.get('name','').strip();vid=next_vps_id();base=re.sub(r'[^A-Za-z0-9_.-]+','-',oname.lower()).strip('-')[:24] or 'user';name=name or f'{base}-vps-{vid}'
            result=create_vps(owner_id=oid,owner_name=oname,name=name,ram_gb=int(request.form['ram_gb']),cpu=int(request.form['cpu']),disk_gb=int(request.form['disk_gb']),os_version=request.form['os_version'],node_id=int(request.form.get('node_id','1')),expiry_days=int(request.form.get('expiry_days','30')),mock=CODESPACE)
            ips=get_ips(result['id']);flash(f"VPS #{result['id']} created for {oname} ({oid}).");flash(f"SSH: root@{', '.join(ips) if ips else 'IP pending'} · credentials generated for the owner.");return redirect(url_for('vps_page'))
        except Exception as e:flash(f'Creation failed: {e}')
    opts=''.join(f"<option value='{escape(k)}'>{escape(v)}</option>" for k,v in OS_OPTIONS.items())
    body=f"<div class='hero'><div class='title'>Create Ubuntu / Linux VPS</div><p class='muted'>Username lookup requires DISCORD_TOKEN and DISCORD_GUILD_ID; numeric Discord IDs work with a bot token.</p></div><div class='card'><form method='post'><label>Discord username or user ID</label><input name='discord_identifier' placeholder='username or 123456789012345678' required><label>VPS name (optional)</label><input name='name' placeholder='auto-generated'><div class='grid'><div><label>RAM GB</label><input type='number' name='ram_gb' min='1' max='1024' value='2' required></div><div><label>CPU cores</label><input type='number' name='cpu' min='1' max='128' value='2' required></div><div><label>Disk GB</label><input type='number' name='disk_gb' min='5' max='16384' value='20' required></div><div><label>Expiry days</label><input type='number' name='expiry_days' min='1' max='3650' value='30' required></div></div><label>OS</label><select name='os_version'>{opts}</select><label>Node ID</label><input type='number' name='node_id' min='1' value='1' required><input type='hidden' name='_csrf' value='{csrf()}'><button>Create VPS</button></form></div>"
    return render_template_string(LAYOUT,title='Create VPS',body=body)
def action(v,fn):
    try:fn(v);flash('VPS action completed.')
    except Exception as e:flash(f'VPS action failed: {e}')
    return redirect(url_for('vps_page'))
@app.post('/vps/<int:v>/start')
@auth
def start(v):return action(v,start_vps)
@app.post('/vps/<int:v>/stop')
@auth
def stop(v):return action(v,stop_vps)
@app.post('/vps/<int:v>/reboot')
@auth
def reboot(v):return action(v,reboot_vps)
@app.post('/vps/<int:v>/delete')
@auth
def delete(v):return action(v,delete_vps)
if __name__=='__main__':panel_init();app.run(host=HOST,port=PORT,debug=False)
