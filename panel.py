#!/usr/bin/env python3
from __future__ import annotations
import html, os, secrets, sqlite3, subprocess, threading
from functools import wraps
from pathlib import Path
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from kvm import kvm_available, tools_ok, domains, state, ip as vm_ip, start as vm_start, stop as vm_stop, reboot, create as vm_create, delete as vm_delete, virsh
APP_DIR=Path(__file__).resolve().parent; DB=APP_DIR/"panel.db"; ENV=APP_DIR/".env"; SECRET=APP_DIR/"secrets"; SECRET.mkdir(mode=0o700,exist_ok=True)
app=Flask(__name__); app.secret_key=os.environ.get("SNCK_PANEL_SECRET") or secrets.token_hex(32)
CSS="""<style>:root{--card:#ffffff;--ring:#a78bfa;--input:#e9d8fd;--muted:#f3e8ff;--accent:#f3e5f5;--border:#e9d8fd;--radius:1.5rem;--chart-1:#a78bfa;--chart-2:#8b5cf6;--chart-3:#7c3aed;--chart-4:#6d28d9;--chart-5:#5b21b6;--popover:#ffffff;--primary:#a78bfa;--sidebar:#e9d8fd;--font-mono:IBM Plex Mono,monospace;--font-sans:Open Sans,sans-serif;--secondary:#e9d8fd;--background:#f7f3f9;--font-serif:Source Serif 4,serif;--foreground:#374151;--destructive:#fca5a5;--shadow-blur:16px;--shadow-color:hsl(0 0% 0%);--sidebar-ring:#a78bfa;--shadow-spread:-4px;--shadow-opacity:.08;--sidebar-accent:#f3e5f5;--sidebar-border:#e9d8fd;--card-foreground:#374151;--shadow-offset-x:0px;--shadow-offset-y:8px;--sidebar-primary:#a78bfa;--muted-foreground:#6b7280;--accent-foreground:#374151;--popover-foreground:#374151;--primary-foreground:#ffffff;--sidebar-foreground:#374151;--secondary-foreground:#4b5563;--destructive-foreground:#ffffff;--sidebar-accent-foreground:#374151;--sidebar-primary-foreground:#ffffff} .dark{--card:#2d2535;--ring:#c0aafd;--input:#3f324a;--muted:#20182b;--accent:#4a3d5a;--border:#3f324a;--radius:1.5rem;--chart-1:#c0aafd;--chart-2:#a78bfa;--chart-3:#8b5cf6;--chart-4:#7c3aed;--chart-5:#6d28d9;--popover:#2d2535;--primary:#c0aafd;--sidebar:#3f324a;--secondary:#3f324a;--background:#1c1917;--foreground:#e0e7ff;--destructive:#fca5a5;--sidebar-ring:#c0aafd;--sidebar-accent:#4a3d5a;--sidebar-border:#3f324a;--card-foreground:#e0e7ff;--sidebar-primary:#c0aafd;--muted-foreground:#9ca3af;--accent-foreground:#d1d5db;--popover-foreground:#e0e7ff;--primary-foreground:#1c1917;--sidebar-foreground:#e0e7ff;--secondary-foreground:#d1d5db;--destructive-foreground:#1c1917;--sidebar-accent-foreground:#d1d5db;--sidebar-primary-foreground:#1c1917}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 8% 0%,#eee4ff 0,#f7f3f9 38%,#fff 100%);color:var(--foreground);font:15px var(--font-sans),system-ui,Arial,sans-serif;min-height:100vh}.wrap{max-width:1240px;margin:auto;padding:24px}.nav{display:flex;gap:18px;justify-content:space-between;align-items:center;padding:16px 20px;border:1px solid var(--border);background:rgba(255,255,255,.82);border-radius:var(--radius);backdrop-filter:blur(18px);position:sticky;top:14px;z-index:5;box-shadow:0 var(--shadow-offset-y) var(--shadow-blur) rgba(0,0,0,var(--shadow-opacity))}.brand{font-weight:900;letter-spacing:.12em;color:var(--foreground)}.brand span{color:var(--primary)}a{color:#7c3aed;text-decoration:none}.links{display:flex;gap:10px;flex-wrap:wrap}.links a{padding:9px 12px;border-radius:12px;color:var(--secondary-foreground)}.links a:hover{background:var(--accent);color:#6d28d9}.hero{margin:30px 0 22px}.title{font-size:32px;font-weight:900;margin:0 0 7px;letter-spacing:-.025em}.muted{color:var(--muted-foreground)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}.card{background:rgba(255,255,255,.88);border:1px solid var(--border);border-radius:var(--radius);padding:21px;box-shadow:0 var(--shadow-offset-y) var(--shadow-blur) rgba(0,0,0,var(--shadow-opacity));transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease}.card:hover{transform:translateY(-2px);border-color:var(--ring);box-shadow:0 12px 28px rgba(124,58,237,.10)}.value{font-size:25px;font-weight:900;margin-top:8px}.ok{color:#16a34a}.bad{color:#dc2626}.warn{color:#b45309}label{display:block;color:var(--muted-foreground);margin:12px 0 6px;font-weight:650}input,select{width:100%;padding:12px 13px;border-radius:12px;border:1px solid var(--input);background:#fff;color:var(--foreground);outline:0}input:focus,select:focus{border-color:var(--ring);box-shadow:0 0 0 3px rgba(167,139,250,.18)}button{border:0;border-radius:12px;padding:11px 16px;background:linear-gradient(100deg,var(--primary),#8b5cf6);color:var(--primary-foreground);font-weight:850;cursor:pointer;box-shadow:0 8px 18px rgba(139,92,246,.18);transition:transform .15s ease,box-shadow .15s ease}button:hover{transform:translateY(-1px);box-shadow:0 11px 24px rgba(139,92,246,.24)}.secondary{background:var(--secondary);color:var(--foreground);border:1px solid var(--border);box-shadow:none}.danger{background:linear-gradient(100deg,#fca5a5,#c084fc)}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}.flash{padding:13px 15px;border:1px solid var(--border);background:var(--accent);border-radius:14px;margin:12px 0}.table{width:100%;border-collapse:collapse;background:rgba(255,255,255,.45)}.table th,.table td{text-align:left;padding:13px;border-bottom:1px solid var(--border)}.table th{color:var(--muted-foreground);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:var(--muted);border:1px solid var(--border);font-size:12px}.login{max-width:470px;margin:9vh auto}.code{font-family:var(--font-mono);background:var(--background);border:1px solid var(--border);padding:13px;border-radius:14px;overflow:auto}@media(max-width:700px){.wrap{padding:12px}.nav{position:static}.title{font-size:26px}.table{font-size:13px}.links{gap:4px}.links a{padding:8px 9px}}</style>"""
LAYOUT="""<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>{{title}} · Snck</title>"""+CSS+"""</head><body><div class=wrap><div class=nav><div class=brand>SNCK <span>KVM PANEL</span></div>{% if session.get('admin') %}<div class=links><a href="/">Dashboard</a><a href="/vps">VPS</a><a href="/nodes">Nodes</a><a href="/bot">Discord Bot</a><a href="/license-info">License</a><a href="/logout">Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>"""
def db(): c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row; return c
def init_db():
 c=db(); c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)"); c.execute("CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,uri TEXT NOT NULL DEFAULT '',storage TEXT NOT NULL DEFAULT '/var/lib/libvirt/images')"); c.execute("CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,node_id INTEGER NOT NULL,ram INTEGER NOT NULL,cpu INTEGER NOT NULL,disk INTEGER NOT NULL,status TEXT NOT NULL,ip TEXT DEFAULT '',created_at TEXT NOT NULL,FOREIGN KEY(node_id) REFERENCES nodes(id))")
 if not c.execute("SELECT 1 FROM settings WHERE key='license'").fetchone(): c.execute("INSERT INTO settings VALUES('license',?)",("SNCK-"+secrets.token_hex(6).upper()+"-"+secrets.token_hex(6).upper()))
 for k,v in (("admin_user","admin"),("admin_pass",""),("license_active","0")):
  if not c.execute("SELECT 1 FROM settings WHERE key=?",(k,)).fetchone(): c.execute("INSERT INTO settings VALUES(?,?)",(k,v))
 if not c.execute("SELECT 1 FROM nodes").fetchone(): c.execute("INSERT INTO nodes(name,uri,storage) VALUES(?,?,?)",("Local KVM Node","","/var/lib/libvirt/images"))
 c.commit(); c.close()
def setting(k):
 c=db(); r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone(); c.close(); return r["value"] if r else ""
def set_setting(k,v):
 c=db(); c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v)); c.commit(); c.close()
def env_values():
 d={}
 if ENV.exists():
  for line in ENV.read_text().splitlines():
   if "=" in line and not line.lstrip().startswith("#"):
    k,v=line.split("=",1); d[k]=v.strip().strip('"').strip("'")
 return d
def write_env(vals):
 d=env_values(); d.update(vals); ENV.write_text("\n".join(f"{k}={v}" for k,v in d.items())+"\n"); os.chmod(ENV,0o600)
def bot_running():
 try:return bool(subprocess.run(["pgrep","-f",str(APP_DIR/"launcher.py")],capture_output=True,text=True).stdout.strip())
 except:return False
def auth(f):
 @wraps(f)
 def w(*a,**kw):
  if setting("license_active")!="1": return redirect(url_for("license"))
  if not session.get("admin"): return redirect(url_for("login"))
  return f(*a,**kw)
 return w
@app.route("/license",methods=["GET","POST"])
def license():
 init_db()
 if request.method=="POST":
  if secrets.compare_digest(request.form.get("license","").strip(),setting("license")): set_setting("license_active","1"); return redirect(url_for("setup"))
  flash("License key is invalid.")
 body="""<div class=login><div class=card><div class=title>Activate Snck License</div><p class=muted>Enter the license issued for this installation.</p><form method=post><label>License Key</label><input name=license placeholder="SNCK-XXXX-XXXX" required><button>Activate License</button></form></div></div>"""
 return render_template_string(LAYOUT,title="License",body=body)
@app.route("/setup",methods=["GET","POST"])
def setup():
 init_db()
 if setting("license_active")!="1": return redirect(url_for("license"))
 if setting("admin_pass"): return redirect(url_for("login"))
 if request.method=="POST":
  u=request.form.get("username","admin").strip() or "admin"; p=request.form.get("password","")
  if len(p)<8: flash("Administrator password must be at least 8 characters.")
  else: set_setting("admin_user",u); set_setting("admin_pass",p); return redirect(url_for("login"))
 body="""<div class=login><div class=card><div class=title>Create Administrator</div><p class=muted>Create the first panel administrator.</p><form method=post><label>Username</label><input name=username value=admin required><label>Password</label><input type=password name=password minlength=8 required><button>Create Admin Account</button></form></div></div>"""
 return render_template_string(LAYOUT,title="Admin Setup",body=body)
@app.route("/login",methods=["GET","POST"])
def login():
 init_db()
 if setting("license_active")!="1": return redirect(url_for("license"))
 if not setting("admin_pass"): return redirect(url_for("setup"))
 if request.method=="POST":
  if secrets.compare_digest(request.form.get("username",""),setting("admin_user")) and secrets.compare_digest(request.form.get("password",""),setting("admin_pass")): session["admin"]=True; return redirect(url_for("index"))
  flash("Invalid administrator credentials.")
 body="""<div class=login><div class=card><div class=title>Administrator Login</div><p class=muted>SNCK KVM Panel</p><form method=post><label>Username</label><input name=username required><label>Password</label><input type=password name=password required><button>Sign in</button></form></div></div>"""
 return render_template_string(LAYOUT,title="Login",body=body)
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))
@app.route("/")
@auth
def index():
 c=db(); n=c.execute("SELECT COUNT(*) x FROM nodes").fetchone()["x"]; total=c.execute("SELECT COUNT(*) x FROM vps WHERE status!='deleted'").fetchone()["x"]; online=c.execute("SELECT COUNT(*) x FROM vps WHERE status='running'").fetchone()["x"]; c.close(); kvm="ENABLED" if kvm_available() else "UNAVAILABLE"; tools="READY" if tools_ok() else "MISSING"; bot="ONLINE" if bot_running() else "OFFLINE"
 body=f"""<div class=hero><div class=title>Command Center</div><p class=muted>Premium KVM virtualization and Discord VPS deployment control.</p></div><div class=grid><div class=card><div class=muted>Nodes</div><div class=value>{n}</div></div><div class=card><div class=muted>VPS</div><div class=value>{total}</div></div><div class=card><div class=muted>Online VPS</div><div class=value ok>{online}</div></div><div class=card><div class=muted>KVM</div><div class=value {'ok' if kvm=='ENABLED' else 'bad'}>{kvm}</div></div><div class=card><div class=muted>QEMU/libvirt</div><div class=value>{tools}</div></div><div class=card><div class=muted>Discord Bot</div><div class=value {'ok' if bot=='ONLINE' else 'bad'}>{bot}</div></div></div><div class=grid><div class=card><h2>VPS Deployment</h2><p class=muted>Create real libvirt/KVM virtual machines.</p><div class=actions><a href=/vps><button>Manage VPS</button></a><a href=/vps/create><button class=secondary>Create VPS</button></a></div></div><div class=card><h2>Discord Control</h2><p class=muted>Configure the Snck Discord bot and connect it to your deployment workflow.</p><a href=/bot><button>Bot Settings</button></a></div></div>"""
 return render_template_string(LAYOUT,title="Dashboard",body=body)
@app.route("/license-info")
@auth
def license_info():
 body=f"""<div class=hero><div class=title>Snck License</div><p class=muted>License status for this installation.</p></div><div class=card><div class=grid><div><div class=muted>Status</div><div class=value ok>ACTIVE</div></div><div><div class=muted>License ID</div><div class=code>{html.escape(setting('license'))}</div></div></div></div>"""; return render_template_string(LAYOUT,title="License",body=body)
@app.route("/bot",methods=["GET","POST"])
@auth
def bot():
 if request.method=="POST":
  token=request.form.get("token","").strip()
  if not token: flash("Bot token cannot be empty."); return redirect(url_for("bot"))
  write_env({"DISCORD_TOKEN":token,"BOT_NAME":request.form.get("name","Snck Discord VPS Deploy Bot").strip() or "Snck Discord VPS Deploy Bot","PREFIX":request.form.get("prefix","!").strip() or "!"})
  subprocess.run(["pkill","-f",str(APP_DIR/"launcher.py")],capture_output=True); log=open(APP_DIR/"bot-panel.log","a"); subprocess.Popen([str(APP_DIR/"venv/bin/python"),str(APP_DIR/"launcher.py")],cwd=APP_DIR,stdout=log,stderr=log,start_new_session=True); flash("Discord bot configuration saved and launch requested."); return redirect(url_for("bot"))
 v=env_values(); body=f"""<div class=hero><div class=title>Discord VPS Deploy Bot</div><p class=muted>Connect your Discord application to Snck.</p></div><div class=card><form method=post><label>Bot Name</label><input name=name value="{html.escape(v.get('BOT_NAME','Snck Discord VPS Deploy Bot'))}"><label>Command Prefix</label><input name=prefix value="{html.escape(v.get('PREFIX','!'))}"><label>Discord Bot Token</label><input type=password name=token placeholder="Enter token" required><button>Save & Start Bot</button></form><p class=muted>Configured: {'YES' if v.get('DISCORD_TOKEN') else 'NO'}</p></div>"""; return render_template_string(LAYOUT,title="Discord Bot",body=body)
@app.route("/nodes",methods=["GET","POST"])
@auth
def nodes_page():
 if request.method=="POST":
  name=request.form.get("name","").strip(); uri=request.form.get("uri","").strip(); storage=request.form.get("storage","/var/lib/libvirt/images").strip()
  if not name: flash("Node name is required."); return redirect(url_for("nodes_page"))
  try:
   c=db(); c.execute("INSERT INTO nodes(name,uri,storage) VALUES(?,?,?)",(name,uri,storage)); c.commit(); c.close(); flash("KVM node added.")
  except Exception as e: flash("Could not add node: "+str(e))
  return redirect(url_for("nodes_page"))
 c=db(); rows=c.execute("SELECT * FROM nodes ORDER BY id").fetchall(); c.close(); trs=""
 for r in rows:
  try: count=len(domains(r["uri"])); st="ONLINE"
  except Exception: count=0; st="OFFLINE"
  trs+=f"<tr><td>{html.escape(r['name'])}</td><td class={'ok' if st=='ONLINE' else 'bad'}>{st}</td><td>{count}</td><td><form method=post action=/nodes/test/{r['id']}><button class=secondary>Test</button></form></td></tr>"
 body=f"""<div class=hero><div class=title>Nodes</div><p class=muted>Local or SSH-backed libvirt nodes.</p></div><div class=card><table class=table><tr><th>Name</th><th>Status</th><th>VMs</th><th>Action</th></tr>{trs}</table></div><div class=card style="margin-top:16px"><h2>Add KVM Node</h2><form method=post><label>Node Name</label><input name=name placeholder="Singapore-01" required><label>Libvirt URI</label><input name=uri placeholder="Blank = local KVM"><label>Storage Directory</label><input name=storage value="/var/lib/libvirt/images" required><button>Add Node</button></form><p class=muted>Remote libvirt nodes require SSH key access. Snck does not store node passwords.</p></div>"""; return render_template_string(LAYOUT,title="Nodes",body=body)
@app.post("/nodes/test/<int:node_id>")
@auth
def node_test(node_id):
 c=db(); n=c.execute("SELECT * FROM nodes WHERE id=?",(node_id,)).fetchone(); c.close()
 if not n: flash("Node not found."); return redirect(url_for("nodes_page"))
 try: virsh(n["uri"],["version"],15); flash(f"Node {n['name']} is reachable.")
 except Exception as e: flash("Node test failed: "+str(e))
 return redirect(url_for("nodes_page"))
def set_status(i,s,addr=None):
 c=db(); c.execute("UPDATE vps SET status=?"+(",ip=?" if addr is not None else "")+" WHERE id=?",(s,addr,i) if addr is not None else (s,i)); c.commit(); c.close()
def provision(vps_id,name,node,ram,cpu,disk,password):
 try:
  set_status(vps_id,"provisioning"); vm_create(name,ram,cpu,disk,password,storage=node["storage"],uri=node["uri"]); vm_start(name,node["uri"]); set_status(vps_id,"running",vm_ip(name,node["uri"])); f=SECRET/f"{name}.txt"; f.write_text(f"VPS={name}\nROOT_PASSWORD={password}\n"); os.chmod(f,0o600)
 except Exception as e:
  set_status(vps_id,"failed"); (SECRET/f"{name}.error").write_text(str(e));
  try: vm_delete(name,node["uri"],node["storage"])
  except Exception: pass
@app.route("/vps")
@auth
def vps_page():
 c=db(); rows=c.execute("SELECT v.*,n.name node_name FROM vps v JOIN nodes n ON n.id=v.node_id WHERE v.status!='deleted' ORDER BY v.id DESC").fetchall(); c.close(); trs="".join(f"<tr><td><a href=/vps/{r['id']}>{html.escape(r['name'])}</a></td><td>{html.escape(r['node_name'])}</td><td>{r['cpu']} CPU / {r['ram']} MB</td><td>{r['disk']} GB</td><td class={'ok' if r['status']=='running' else 'warn'}>{html.escape(r['status'].upper())}</td><td>{html.escape(r['ip'] or 'Pending')}</td></tr>" for r in rows)
 body=f"""<div class=hero><div class=title>VPS Instances</div><p class=muted>Real KVM virtual machines managed by libvirt.</p><a href=/vps/create><button>Deploy New VPS</button></a></div><div class=card><table class=table><tr><th>VPS</th><th>Node</th><th>Resources</th><th>Disk</th><th>Status</th><th>IPv4</th></tr>{trs or '<tr><td colspan=6>No VPS deployed yet.</td></tr>'}</table></div>"""; return render_template_string(LAYOUT,title="VPS",body=body)
@app.route("/vps/create",methods=["GET","POST"])
@auth
def create_vps():
 c=db(); nodes_rows=c.execute("SELECT * FROM nodes ORDER BY id").fetchall(); c.close()
 if request.method=="POST":
  try:
   name=request.form.get("name","").strip(); node_id=int(request.form.get("node_id","1")); ram=int(request.form.get("ram","2048")); cpu=int(request.form.get("cpu","2")); disk=int(request.form.get("disk","20")); password=request.form.get("password","").strip() or secrets.token_urlsafe(12)
   c=db(); node=c.execute("SELECT * FROM nodes WHERE id=?",(node_id,)).fetchone()
   if not node: c.close(); raise ValueError("Node not found")
   c.execute("INSERT INTO vps(name,node_id,ram,cpu,disk,status,created_at) VALUES(?,?,?,?,?,?,datetime('now'))",(name,node_id,ram,cpu,disk,"queued")); vid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.commit(); c.close(); threading.Thread(target=provision,args=(vid,name,node,ram,cpu,disk,password),daemon=True).start(); flash("VPS deployment started. Refresh the VPS list to follow progress."); return redirect(url_for("vps_page"))
  except Exception as e: flash("Could not start deployment: "+str(e))
 opts="".join(f"<option value={n['id']}>{html.escape(n['name'])}</option>" for n in nodes_rows); body=f"""<div class=hero><div class=title>Deploy New KVM VPS</div><p class=muted>Ubuntu 24.04 cloud image, virtio disk and DHCP network.</p></div><div class=card><form method=post><label>VPS Name</label><input name=name pattern="[A-Za-z0-9_.-]+" required><label>Node</label><select name=node_id>{opts}</select><label>CPU Cores</label><input type=number name=cpu value=2 min=1 max=128 required><label>RAM (MB)</label><input type=number name=ram value=2048 min=512 required><label>Disk (GB)</label><input type=number name=disk value=20 min=5 required><label>Root Password</label><input type=password name=password minlength=8 placeholder="Leave blank to generate"><button>Deploy VPS</button></form></div>"""; return render_template_string(LAYOUT,title="Create VPS",body=body)
@app.route("/vps/<int:vps_id>")
@auth
def vps_detail(vps_id):
 c=db(); r=c.execute("SELECT v.*,n.name node_name,n.uri,n.storage FROM vps v JOIN nodes n ON n.id=v.node_id WHERE v.id=?",(vps_id,)).fetchone(); c.close()
 if not r:return "VPS not found",404
 live=r["status"] if r["status"] in ("queued","provisioning","failed") else state(r["name"],r["uri"]); addr=r["ip"] or vm_ip(r["name"],r["uri"])
 if live=="running": set_status(vps_id,"running",addr)
 body=f"""<div class=hero><div class=title>{html.escape(r['name'])}</div><p class=muted>{html.escape(r['node_name'])} · <span class={'ok' if live=='running' else 'warn'}>{html.escape(live.upper())}</span></p></div><div class=grid><div class=card><div class=muted>CPU</div><div class=value>{r['cpu']}</div></div><div class=card><div class=muted>RAM</div><div class=value>{r['ram']} MB</div></div><div class=card><div class=muted>Disk</div><div class=value>{r['disk']} GB</div></div><div class=card><div class=muted>IPv4</div><div class=value>{html.escape(addr or 'Pending')}</div></div></div><div class=card style="margin-top:16px"><h2>Actions</h2><div class=actions><form method=post action=/vps/{r['id']}/action/start><button>Start</button></form><form method=post action=/vps/{r['id']}/action/stop><button class=secondary>Stop</button></form><form method=post action=/vps/{r['id']}/action/restart><button class=secondary>Restart</button></form><form method=post action=/vps/{r['id']}/action/delete onsubmit="return confirm('Delete this VPS and its disk?')"><button class=danger>Delete VPS</button></form></div></div><div class=card style="margin-top:16px"><h2>Credentials</h2><p class=muted>Root password is stored locally with restricted permissions.</p><a href=/vps/{r['id']}/credentials><button class=secondary>Show Credentials</button></a></div><script>setTimeout(()=>location.reload(),5000)</script>"""; return render_template_string(LAYOUT,title=r["name"],body=body)
@app.post("/vps/<int:vps_id>/action/<action>")
@auth
def vps_action(vps_id,action):
 if action not in {"start","stop","restart","delete"}: return "Invalid action",400
 c=db(); r=c.execute("SELECT v.*,n.uri,n.storage FROM vps v JOIN nodes n ON n.id=v.node_id WHERE v.id=?",(vps_id,)).fetchone(); c.close()
 if not r:return "VPS not found",404
 try:
  if action=="start": vm_start(r["name"],r["uri"]); set_status(vps_id,"running",vm_ip(r["name"],r["uri"]))
  elif action=="stop": vm_stop(r["name"],r["uri"]); set_status(vps_id,"stopped")
  elif action=="restart": reboot(r["name"],r["uri"]); set_status(vps_id,"running")
  else: vm_delete(r["name"],r["uri"],r["storage"]); set_status(vps_id,"deleted")
  flash(f"VPS {action} completed.")
 except Exception as e: flash(f"{action.title()} failed: {e}")
 return redirect(url_for("vps_detail",vps_id=vps_id) if action!="delete" else url_for("vps_page"))
@app.route("/vps/<int:vps_id>/credentials")
@auth
def credentials(vps_id):
 c=db(); r=c.execute("SELECT * FROM vps WHERE id=?",(vps_id,)).fetchone(); c.close()
 if not r:return "VPS not found",404
 f=SECRET/f"{r['name']}.txt"
 if not f.exists():return "Credentials are not available yet.",404
 body=f"<div class=hero><div class=title>VPS Credentials</div><p class=muted>Keep these credentials private.</p></div><div class=card><div class=code>{html.escape(f.read_text())}</div><a href=/vps/{vps_id}><button>Back</button></a></div>"; return render_template_string(LAYOUT,title="Credentials",body=body)
def bootstrap():
 init_db(); p=setting("admin_pass")
 if not p:p=secrets.token_urlsafe(12); set_setting("admin_pass",p); set_setting("admin_user","admin")
 print("SNCK_LICENSE="+setting("license")); print("SNCK_ADMIN_USER="+setting("admin_user")); print("SNCK_ADMIN_PASSWORD="+p)
if __name__=="__main__":
 if "--bootstrap" in os.sys.argv: bootstrap(); raise SystemExit(0)
 init_db(); app.run(host="0.0.0.0",port=int(os.environ.get("SNCK_PANEL_PORT","5000")))
