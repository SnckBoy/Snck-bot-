#!/usr/bin/env python3
from __future__ import annotations

import os
import secrets
import shlex
import sqlite3
import string
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
VPS_DB = Path(os.getenv("SNCK_VPS_DB", str(BASE / "vps.db")))
DEFAULT_STORAGE_POOL = os.getenv("DEFAULT_STORAGE_POOL", "default")
DEFAULT_EXPIRATION_DAYS = int(os.getenv("DEFAULT_VPS_EXPIRATION_DAYS", "30"))

OS_OPTIONS = {
    "ubuntu:20.04": "Ubuntu 20.04 LTS",
    "ubuntu:22.04": "Ubuntu 22.04 LTS",
    "ubuntu:24.04": "Ubuntu 24.04 LTS",
    "images:debian/11": "Debian 11",
    "images:debian/12": "Debian 12",
    "images:debian/13": "Debian 13",
}

def db():
    c = sqlite3.connect(VPS_DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS nodes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            location TEXT, total_vps INTEGER DEFAULT 100, tags TEXT DEFAULT '[]',
            api_key TEXT, url TEXT, is_local INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS vps(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            node_id INTEGER NOT NULL DEFAULT 1, container_name TEXT UNIQUE NOT NULL,
            ram TEXT NOT NULL, cpu TEXT NOT NULL, storage TEXT NOT NULL,
            config TEXT NOT NULL, os_version TEXT DEFAULT 'ubuntu:22.04',
            status TEXT DEFAULT 'stopped', suspended INTEGER DEFAULT 0,
            whitelisted INTEGER DEFAULT 0, created_at TEXT NOT NULL,
            shared_with TEXT DEFAULT '[]', suspension_history TEXT DEFAULT '[]',
            expiration_date TEXT DEFAULT NULL, root_password TEXT DEFAULT NULL,
            owner_name TEXT DEFAULT NULL, FOREIGN KEY(node_id) REFERENCES nodes(id))""")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(vps)").fetchall()}
        migrations = {
            "os_version": "TEXT DEFAULT 'ubuntu:22.04'", "status": "TEXT DEFAULT 'stopped'",
            "suspended": "INTEGER DEFAULT 0", "whitelisted": "INTEGER DEFAULT 0",
            "shared_with": "TEXT DEFAULT '[]'", "suspension_history": "TEXT DEFAULT '[]'",
            "expiration_date": "TEXT DEFAULT NULL", "root_password": "TEXT DEFAULT NULL",
            "owner_name": "TEXT DEFAULT NULL",
        }
        for name, definition in migrations.items():
            if name not in cols:
                c.execute(f"ALTER TABLE vps ADD COLUMN {name} {definition}")
        if not c.execute("SELECT 1 FROM nodes LIMIT 1").fetchone():
            c.execute("INSERT INTO nodes(name,location,total_vps,is_local) VALUES(?,?,?,1)", ("Local Node", "Local", 100))

def _run_local(args: list[str], timeout: int = 180) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        detail = (proc.stderr or proc.stdout or "command failed").strip()
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return proc.stdout.strip()

def node(node_id: int):
    with db() as c:
        row = c.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        raise ValueError("Node not found")
    return dict(row)

def run_lxc(node_id: int, args: list[str], timeout: int = 180) -> str:
    n = node(node_id)
    if int(n.get("is_local", 1)):
        return _run_local(["lxc", *args], timeout)
    url = (n.get("url") or "").rstrip("/")
    key = n.get("api_key") or ""
    if not url or not key:
        raise RuntimeError("Remote node is missing URL/API key")
    import requests
    command = "lxc " + " ".join(shlex.quote(x) for x in args)
    r = requests.post(f"{url}/api/execute", json={"command": command}, params={"api_key": key}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Remote node HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    if int(data.get("returncode", 1)) != 0:
        raise RuntimeError(data.get("stderr") or "remote command failed")
    return data.get("stdout", "")

def random_password(length=24):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def next_vps_id():
    init_db()
    with db() as c:
        return int(c.execute("SELECT COALESCE(MAX(id),0)+1 n FROM vps").fetchone()["n"])

def _configure_ssh(node_id: int, name: str, password: str):
    config = """Port 22
AddressFamily any
ListenAddress 0.0.0.0
PasswordAuthentication yes
PubkeyAuthentication yes
PermitRootLogin yes
PermitEmptyPasswords no
UsePAM yes
MaxAuthTries 6
MaxSessions 10
Subsystem sftp /usr/lib/openssh/sftp-server
"""
    payload = config.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    run_lxc(node_id, ["exec", name, "--", "bash", "-lc", f'printf "%b" "{payload}" > /etc/ssh/sshd_config'])
    run_lxc(node_id, ["exec", name, "--", "bash", "-lc", "systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || service ssh restart 2>/dev/null || true"], timeout=30)
    run_lxc(node_id, ["exec", name, "--", "bash", "-lc", f"printf '%s\\n' {shlex.quote('root:' + password)} | chpasswd"], timeout=30)

def create_vps(*, owner_id: str, owner_name: str, name: str, ram_gb: int, cpu: int,
               disk_gb: int, os_version: str, node_id: int = 1, expiry_days: int | None = None,
               mock: bool = False) -> dict[str, Any]:
    init_db()
    if os_version not in OS_OPTIONS:
        raise ValueError("Unsupported operating system")
    if not 1 <= ram_gb <= 1024 or not 1 <= cpu <= 128 or not 5 <= disk_gb <= 16384:
        raise ValueError("Requested resources are outside allowed limits")
    if not re_full_name(name):
        raise ValueError("Invalid VPS name")
    n = node(node_id)
    with db() as c:
        used = c.execute("SELECT COUNT(*) n FROM vps WHERE node_id=?", (node_id,)).fetchone()["n"]
        if int(n.get("total_vps") or 0) > 0 and used >= int(n["total_vps"]):
            raise RuntimeError("Node capacity is full")
        if c.execute("SELECT 1 FROM vps WHERE container_name=?", (name,)).fetchone():
            raise ValueError("A VPS with this name already exists")
    password = random_password()
    import shutil
    mock_mode = bool(mock or os.getenv("SNCK_CODESPACE") == "1" or not shutil.which("lxc"))
    if not mock_mode:
        try:
            run_lxc(node_id, ["init", os_version, name, "-s", DEFAULT_STORAGE_POOL, "-c", "security.privileged=true"])
            run_lxc(node_id, ["config", "set", name, "limits.memory", f"{ram_gb}GB"])
            run_lxc(node_id, ["config", "set", name, "limits.cpu", str(cpu)])
            run_lxc(node_id, ["config", "device", "set", name, "root", "size", f"{disk_gb}GB"])
            for key, value in [("security.nesting", "true"), ("security.privileged", "true"), ("security.syscalls.intercept.mknod", "true"), ("security.syscalls.intercept.setxattr", "true")]:
                run_lxc(node_id, ["config", "set", name, key, value])
            run_lxc(node_id, ["start", name])
            _configure_ssh(node_id, name, password)
        except Exception:
            try:
                run_lxc(node_id, ["delete", name, "--force"], timeout=60)
            except Exception:
                pass
            raise
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=expiry_days or DEFAULT_EXPIRATION_DAYS)
    with db() as c:
        cur = c.execute("""INSERT INTO vps(user_id,node_id,container_name,ram,cpu,storage,config,os_version,status,suspended,whitelisted,created_at,shared_with,suspension_history,expiration_date,root_password,owner_name)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(owner_id), node_id, name, f"{ram_gb}GB", str(cpu), f"{disk_gb}GB", f"{ram_gb}GB RAM / {cpu} CPU / {disk_gb}GB Disk", os_version, "running", 0, 0, now.isoformat(), "[]", "[]", expiry.isoformat(), password, owner_name))
        vps_id = cur.lastrowid
    return {"id": vps_id, "owner_id": str(owner_id), "owner_name": owner_name, "name": name, "ram_gb": ram_gb, "cpu": cpu, "disk_gb": disk_gb, "os_version": os_version, "status": "running", "password": password, "mock": mock_mode, "node_id": node_id, "expires": expiry.isoformat()}

def re_full_name(name: str) -> bool:
    return bool(name and len(name) <= 63 and all(ch in string.ascii_letters + string.digits + "._-" for ch in name))

def _action(vps_id: int, action: str):
    init_db()
    with db() as c:
        row = c.execute("SELECT * FROM vps WHERE id=?", (vps_id,)).fetchone()
    if not row:
        raise ValueError("VPS not found")
    v = dict(row)
    import shutil
    mock = os.getenv("SNCK_CODESPACE") == "1" or not shutil.which("lxc")
    if not mock:
        run_lxc(int(v["node_id"]), [action, v["container_name"]])
    status = {"start": "running", "stop": "stopped", "restart": "running"}[action]
    with db() as c:
        c.execute("UPDATE vps SET status=? WHERE id=?", (status, vps_id))
    return status

def start_vps(vps_id): return _action(vps_id, "start")
def stop_vps(vps_id): return _action(vps_id, "stop")
def reboot_vps(vps_id): return _action(vps_id, "restart")

def delete_vps(vps_id):
    init_db()
    with db() as c:
        row = c.execute("SELECT * FROM vps WHERE id=?", (vps_id,)).fetchone()
    if not row:
        raise ValueError("VPS not found")
    v = dict(row)
    import shutil
    if os.getenv("SNCK_CODESPACE") != "1" and shutil.which("lxc"):
        run_lxc(int(v["node_id"]), ["delete", v["container_name"], "--force"])
    with db() as c:
        c.execute("DELETE FROM vps WHERE id=?", (vps_id,))
    return True

def vps_list():
    init_db()
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM vps ORDER BY id DESC").fetchall()]

def get_vps(vps_id):
    init_db()
    with db() as c:
        r = c.execute("SELECT * FROM vps WHERE id=?", (vps_id,)).fetchone()
    return dict(r) if r else None

def get_ips(vps_id):
    v = get_vps(vps_id)
    import shutil
    if not v or os.getenv("SNCK_CODESPACE") == "1" or not shutil.which("lxc"):
        return []
    try:
        out = run_lxc(int(v["node_id"]), ["list", v["container_name"], "-c", "4", "--format", "csv"], timeout=20)
        return [x.strip() for x in out.replace("\n", ",").split(",") if x.strip()]
    except Exception:
        return []
