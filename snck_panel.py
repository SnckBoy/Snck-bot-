#!/usr/bin/env python3
from __future__ import annotations
import hmac, os, re, secrets, sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, flash, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).resolve().parent
DB = BASE / "snck_panel.db"
PORT = int(os.getenv("SNCK_PANEL_PORT", "5000"))
HOST = os.getenv("SNCK_PANEL_HOST", "0.0.0.0")
CODESPACE = os.getenv("SNCK_CODESPACE") == "1"
LICENSE_KEY = os.getenv("SNCK_LICENSE_KEY", "official.snck.fun")

try:
    from kvm import create as kvm_create, delete as kvm_delete, reboot as kvm_reboot, start as kvm_start, stop as kvm_stop, kvm_available, tools_ok
except Exception:
    kvm_create = kvm_delete = kvm_reboot = kvm_start = kvm_stop = None
    def kvm_available(): return False
    def tools_ok(): return False

app = Flask(__name__)
app.secret_key = os.getenv("SNCK_PANEL_SECRET") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("SNCK_COOKIE_SECURE", "0") == "1", MAX_CONTENT_LENGTH=64 * 1024)

CSS = """<style>
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0%,#211b48,#070811 45%);color:#f5f7ff;font:15px system-ui,Arial}.wrap{max-width:1200px;margin:auto;padding:20px}.nav{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:15px 18px;background:#0c1120ee;border:1px solid #27304e;border-radius:18px}.brand{font-weight:900;letter-spacing:.12em}.brand span{color:#57e6ff}.links{display:flex;gap:8px;flex-wrap:wrap}.links a{color:#57e6ff;text-decoration:none;padding:8px 10px;border-radius:10px}.hero{margin:28px 0}.title{font-size:31px;font-weight:900}.muted{color:#8d96b5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:16px 0}.card{background:#101528ee;border:1px solid #27304e;border-radius:18px;padding:20px;box-shadow:0 15px 45px #0006}.value{font-size:25px;font-weight:900;margin-top:8px}.ok{color:#57e39b}.bad{color:#ff667f}label{display:block;margin:11px 0 5px;color:#8d96b5}input,select{width:100%;padding:11px;border:1px solid #27304e;border-radius:10px;background:#070a14;color:#fff;margin-bottom:8px}button{border:0;border-radius:10px;padding:10px 14px;background:linear-gradient(100deg,#57e6ff,#a970ff);color:#05060c;font-weight:800;cursor:pointer}.secondary{background:#171d31;color:#fff;border:1px solid #27304e}.danger{background:#7f3044;color:#fff}.actions{display:flex;gap:7px;flex-wrap:wrap}.flash{padding:12px;margin:12px 0;border:1px solid #27304e;border-radius:12px;background:#12182a}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:11px;border-bottom:1px solid #27304e}.login{max-width:460px;margin:9vh auto}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#171d31;border:1px solid #27304e}@media(max-width:700px){.wrap{padding:12px}.nav{flex-direction:column;align-items:flex-start}.table{display:block;overflow:auto;white-space:nowrap}}
</style>"""
LAYOUT = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{{title}} · Snck</title>""" + CSS + """</head><body><div class='wrap'><div class='nav'><div class='brand'>SNCK <span>KVM PANEL</span></div>{% if session.get('role') %}<div class='links'><a href='/'>Dashboard</a><a href='/vps'>VPS</a>{% if session.get('role')=='admin' %}<a href='/nodes'>Nodes</a>{% endif %}<a href='/logout'>Logout</a></div>{% endif %}</div>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class='flash'>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>"""

def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,uri TEXT NOT NULL DEFAULT '',storage TEXT NOT NULL DEFAULT '/var/lib/libvirt/images')")
        c.execute("CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL DEFAULT 'admin',node_id INTEGER NOT NULL,container_name TEXT UNIQUE NOT NULL,ram INTEGER NOT NULL,cpu INTEGER NOT NULL,disk INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'stopped',created_at TEXT NOT NULL,mock INTEGER NOT NULL DEFAULT 0,FOREIGN KEY(node_id) REFERENCES nodes(id))")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('license_active','0')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('admin_user','admin')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('admin_pass_hash','')")
        if not c.execute("SELECT 1 FROM nodes LIMIT 1").fetchone():
            c.execute("INSERT INTO nodes(name,uri,storage) VALUES(?,?,?)",("Local KVM Node","","/var/lib/libvirt/images"))

def setting(key, default=""):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with db() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]

@app.context_processor
def context(): return {"csrf_token": csrf_token}

@app.before_request
def csrf_guard():
    if request.method == "POST" and request.endpoint not in {"license", "setup", "login"}:
        token = request.form.get("_csrf", "")
        if not session.get("_csrf") or not hmac.compare_digest(token, session["_csrf"]):
            return "CSRF validation failed", 400

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        init_db()
        if setting("license_active") != "1": return redirect(url_for("license"))
        if session.get("role") != "admin": return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        init_db()
        if setting("license_active") != "1": return redirect(url_for("license"))
        if session.get("role") != "admin": return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

@app.get("/health")
def health():
    return {"status":"ok","panel":"snck","port":PORT,"codespace":CODESPACE,"kvm":bool(kvm_available()),"tools":bool(tools_ok())}

@app.route("/license", methods=["GET","POST"])
def license():
    init_db()
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("license", "").strip(), LICENSE_KEY):
            set_setting("license_active", "1")
            return redirect(url_for("setup"))
        flash("License key is invalid.")
    return render_template_string(LAYOUT,title="License",body="<div class='login'><div class='card'><div class='title'>Activate Snck</div><p class='muted'>Enter your Snck license.</p><form method='post'><label>License</label><input name='license' required><button>Activate</button></form></div></div>")

@app.route("/setup", methods=["GET","POST"])
def setup():
    init_db()
    if setting("license_active") != "1": return redirect(url_for("license"))
    if setting("admin_pass_hash"): return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "admin").strip() or "admin"
        password = request.form.get("password", "")
        if not 3 <= len(username) <= 64: flash("Username must be 3-64 characters.")
        elif len(password) < 10: flash("Password must be at least 10 characters.")
        else:
            set_setting("admin_user", username)
            set_setting("admin_pass_hash", generate_password_hash(password, method="scrypt"))
            return redirect(url_for("login"))
    return render_template_string(LAYOUT,title="Setup",body="<div class='login'><div class='card'><div class='title'>Create Administrator</div><form method='post'><label>Username</label><input name='username' value='admin' minlength='3' maxlength='64' required><label>Password</label><input type='password' name='password' minlength='10' required><button>Create Admin</button></form></div></div>")

@app.route("/login", methods=["GET","POST"])
def login():
    init_db()
    if setting("license_active") != "1": return redirect(url_for("license"))
    if not setting("admin_pass_hash"): return redirect(url_for("setup"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if hmac.compare_digest(username, setting("admin_user")) and check_password_hash(setting("admin_pass_hash"), password):
            session.clear(); session["role"] = "admin"; session["uid"] = "admin"; session["_csrf"] = secrets.token_urlsafe(32)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.")
    return render_template_string(LAYOUT,title="Login",body="<div class='login'><div class='card'><div class='title'>Snck KVM Panel</div><form method='post'><label>Username</label><input name='username' required><label>Password</label><input type='password' name='password' required><button>Sign in</button></form></div></div>")

@app.get("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.get("/")
@login_required
def dashboard():
    with db() as c:
        nodes = c.execute("SELECT COUNT(*) n FROM nodes").fetchone()["n"]
        vps = c.execute("SELECT COUNT(*) n FROM vps WHERE status!='deleted'").fetchone()["n"]
        online = c.execute("SELECT COUNT(*) n FROM vps WHERE status='running'").fetchone()["n"]
    body = f"<div class='hero'><div class='title'>Command Center</div><p class='muted'>{'Codespace test mode' if CODESPACE else 'KVM host mode'} · port {PORT}</p></div><div class='grid'><div class='card'>Nodes<div class='value'>{nodes}</div></div><div class='card'>VPS<div class='value'>{vps}</div></div><div class='card'>Online<div class='value ok'>{online}</div></div><div class='card'>KVM<div class='value {'ok' if kvm_available() else 'bad'}'>{'READY' if kvm_available() else 'TEST/MISSING'}</div></div></div><div class='card'><a href='/vps'><button>Manage VPS</button></a> <a href='/vps/create'><button class='secondary'>Create VPS</button></a></div>"
    return render_template_string(LAYOUT,title="Dashboard",body=body)

@app.get("/vps")
@login_required
def vps_list():
    with db() as c: rows = c.execute("SELECT * FROM vps WHERE status!='deleted' ORDER BY id DESC").fetchall()
    trs = []
    for r in rows:
        trs.append(f"<tr><td>{r['container_name']}</td><td>{r['ram']} MB</td><td>{r['cpu']}</td><td>{r['disk']} GB</td><td><span class='pill'>{r['status']}</span></td><td><form method='post' action='/vps/{r['id']}/start' style='display:inline'><input type='hidden' name='_csrf' value='{csrf_token()}'><button>Start</button></form> <form method='post' action='/vps/{r['id']}/stop' style='display:inline'><input type='hidden' name='_csrf' value='{csrf_token()}'><button class='secondary'>Stop</button></form> <form method='post' action='/vps/{r['id']}/reboot' style='display:inline'><input type='hidden' name='_csrf' value='{csrf_token()}'><button class='secondary'>Reboot</button></form> <form method='post' action='/vps/{r['id']}/delete' style='display:inline'><input type='hidden' name='_csrf' value='{csrf_token()}'><button class='danger'>Delete</button></form></td></tr>")
    body = "<div class='hero'><div class='title'>VPS</div><p class='muted'>Codespaces use mock lifecycle mode because KVM hardware is unavailable.</p><a href='/vps/create'><button>Create VPS</button></a></div><div class='card'><table class='table'><tr><th>Name</th><th>RAM</th><th>CPU</th><th>Disk</th><th>Status</th><th>Actions</th></tr>" + ("".join(trs) or "<tr><td colspan='6'>No VPS.</td></tr>") + "</table></div>"
    return render_template_string(LAYOUT,title="VPS",body=body)

@app.route("/vps/create", methods=["GET","POST"])
@admin_required
def vps_create():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip(); ram = int(request.form.get("ram", "1024")); cpu = int(request.form.get("cpu", "1")); disk = int(request.form.get("disk", "10")); password = request.form.get("password", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,63}", name): raise ValueError("Invalid VPS name")
            if not 512 <= ram <= 1048576 or not 1 <= cpu <= 128 or not 5 <= disk <= 16384: raise ValueError("Resource limits are invalid")
            if len(password) < 12: raise ValueError("Temporary root password must be at least 12 characters")
            mock = int(CODESPACE or not kvm_available() or not tools_ok())
            if not mock: kvm_create(name, ram, cpu, disk, password); kvm_start(name)
            with db() as c:
                nid = c.execute("SELECT id FROM nodes ORDER BY id LIMIT 1").fetchone()["id"]
                c.execute("INSERT INTO vps(user_id,node_id,container_name,ram,cpu,disk,status,created_at,mock) VALUES(?,?,?,?,?,?,?,?,?)",("admin",nid,name,ram,cpu,disk,"running",datetime.now(timezone.utc).isoformat(),mock))
            flash(f"VPS {name} created successfully.")
        except sqlite3.IntegrityError: flash("A VPS with that name already exists.")
        except Exception as exc: flash(f"VPS creation failed: {str(exc)[:300]}")
        return redirect(url_for("vps_list"))
    body = "<div class='hero'><div class='title'>Create VPS</div></div><div class='card'><form method='post'><input type='hidden' name='_csrf' value='{{ csrf_token() }}'><label>Name</label><input name='name' pattern='[A-Za-z0-9_.-]{1,63}' maxlength='63' required><label>RAM MB</label><input name='ram' type='number' min='512' max='1048576' value='1024' required><label>CPU</label><input name='cpu' type='number' min='1' max='128' value='1' required><label>Disk GB</label><input name='disk' type='number' min='5' max='16384' value='10' required><label>Temporary root password</label><input name='password' type='password' minlength='12' required><button>Create VPS</button></form></div>"
    return render_template_string(LAYOUT,title="Create VPS",body=body)

def action(vid, op):
    with db() as c: row = c.execute("SELECT * FROM vps WHERE id=? AND status!='deleted'",(vid,)).fetchone()
    if not row: flash("VPS not found."); return redirect(url_for("vps_list"))
    try:
        if not row["mock"] and not CODESPACE:
            {"start":kvm_start,"stop":kvm_stop,"reboot":kvm_reboot}[op](row["container_name"])
        status = "running" if op in {"start","reboot"} else "stopped"
        with db() as c: c.execute("UPDATE vps SET status=? WHERE id=?",(status,vid))
        flash(f"{row['container_name']}: {status}")
    except Exception as exc: flash(f"{op.title()} failed: {str(exc)[:300]}")
    return redirect(url_for("vps_list"))

@app.post("/vps/<int:vid>/start")
@admin_required
def start_vps(vid): return action(vid,"start")
@app.post("/vps/<int:vid>/stop")
@admin_required
def stop_vps(vid): return action(vid,"stop")
@app.post("/vps/<int:vid>/reboot")
@admin_required
def reboot_vps(vid): return action(vid,"reboot")
@app.post("/vps/<int:vid>/delete")
@admin_required
def delete_vps(vid):
    with db() as c: row = c.execute("SELECT * FROM vps WHERE id=? AND status!='deleted'",(vid,)).fetchone()
    if not row: flash("VPS not found."); return redirect(url_for("vps_list"))
    try:
        if not row["mock"] and not CODESPACE and kvm_delete: kvm_delete(row["container_name"])
        with db() as c: c.execute("UPDATE vps SET status='deleted' WHERE id=?",(vid,))
        flash(f"{row['container_name']} deleted.")
    except Exception as exc: flash(f"Delete failed: {str(exc)[:300]}")
    return redirect(url_for("vps_list"))

@app.get("/nodes")
@admin_required
def nodes():
    with db() as c: rows = c.execute("SELECT * FROM nodes ORDER BY id").fetchall()
    body = "<div class='hero'><div class='title'>Nodes</div></div><div class='grid'>" + "".join(f"<div class='card'><div class='value'>{r['name']}</div><p>URI: {r['uri'] or 'local'}</p><p>KVM: {'READY' if kvm_available() else 'UNAVAILABLE'}</p></div>" for r in rows) + "</div>"
    return render_template_string(LAYOUT,title="Nodes",body=body)

init_db()
if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
