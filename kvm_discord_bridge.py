#!/usr/bin/env python3
"""Shared KVM backend for the Discord bot.

The web panel and Discord bot both use the same vps.db records and libvirt/KVM
backend.  This module intentionally keeps the Discord-facing adapter small.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from kvm import create as kvm_create
from kvm import delete as kvm_delete
from kvm import start as kvm_start
from kvm import stop as kvm_stop
from kvm import reboot as kvm_reboot
from kvm import state as kvm_state
from kvm import ip as kvm_ip

BASE = Path(__file__).resolve().parent
DB = BASE / "vps.db"

IMAGE_MAP = {
    "ubuntu:20.04": "https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img",
    "ubuntu:22.04": "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img",
    "ubuntu:24.04": "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
    "images:debian/11": "https://cloud.debian.org/images/cloud/bullseye/latest/debian-11-generic-amd64.qcow2",
    "images:debian/12": "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2",
    "images:debian/13": "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2",
    "images:debian/10": "https://cloud.debian.org/images/cloud/buster/latest/debian-10-generic-amd64.qcow2",
}


def ensure_schema() -> None:
    """Ensure the shared database has every field used by panel and bot."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS vps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            node_id INTEGER NOT NULL DEFAULT 1,
            container_name TEXT UNIQUE NOT NULL,
            ram TEXT NOT NULL,
            cpu TEXT NOT NULL,
            storage TEXT NOT NULL,
            config TEXT NOT NULL,
            os_version TEXT DEFAULT 'ubuntu:24.04',
            status TEXT DEFAULT 'stopped',
            suspended INTEGER DEFAULT 0,
            whitelisted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            shared_with TEXT DEFAULT '[]',
            suspension_history TEXT DEFAULT '[]',
            expiration_date TEXT DEFAULT NULL,
            root_password TEXT DEFAULT NULL
        )""")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(vps)").fetchall()}
        additions = {
            "suspension_history": "TEXT DEFAULT '[]'",
            "shared_with": "TEXT DEFAULT '[]'",
            "expiration_date": "TEXT DEFAULT NULL",
            "root_password": "TEXT DEFAULT NULL",
            "os_version": "TEXT DEFAULT 'ubuntu:24.04'",
            "node_id": "INTEGER DEFAULT 1",
            "suspended": "INTEGER DEFAULT 0",
            "whitelisted": "INTEGER DEFAULT 0",
        }
        for name, typ in additions.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE vps ADD COLUMN {name} {typ}")
        conn.commit()
    finally:
        conn.close()


def node_uri(node: Optional[Dict[str, Any]]) -> str:
    if not node:
        return ""
    return str(node.get("url") or "")


def normalize_ram_gb(value: Any) -> int:
    text = str(value).strip().lower().replace(" ", "")
    if text.endswith("mb"):
        return max(1, int(int(float(text[:-2])) / 1024))
    if text.endswith("gb"):
        return int(float(text[:-2]))
    return int(float(text))


def normalize_disk_gb(value: Any) -> int:
    text = str(value).strip().lower().replace(" ", "")
    if text.endswith("gb"):
        return int(float(text[:-2]))
    return int(float(text))


async def deploy(name: str, ram: Any, cpu: Any, disk: Any, password: str,
                 os_version: str = "ubuntu:24.04", storage: str = "/var/lib/libvirt/images",
                 uri: str = "") -> str:
    """Create and start a real KVM guest."""
    ensure_schema()
    ram_gb = normalize_ram_gb(ram)
    disk_gb = normalize_disk_gb(disk)
    image = IMAGE_MAP.get(os_version, os_version if str(os_version).startswith("http") else IMAGE_MAP["ubuntu:24.04"])
    await asyncio.to_thread(kvm_create, name, ram_gb * 1024, int(cpu), disk_gb, password,
                            image=image, storage=storage, uri=uri)
    await asyncio.to_thread(kvm_start, name, uri)
    return name


async def start(name: str, uri: str = "") -> str:
    await asyncio.to_thread(kvm_start, name, uri)
    return "running"


async def stop(name: str, uri: str = "") -> str:
    await asyncio.to_thread(kvm_stop, name, uri)
    return "stopped"


async def reboot(name: str, uri: str = "") -> str:
    await asyncio.to_thread(kvm_reboot, name, uri)
    return "running"


async def delete(name: str, uri: str = "", storage: str = "/var/lib/libvirt/images") -> str:
    await asyncio.to_thread(kvm_delete, name, uri, storage)
    return "deleted"


async def stats(name: str, uri: str = "") -> Dict[str, Any]:
    status = await asyncio.to_thread(kvm_state, name, uri)
    address = await asyncio.to_thread(kvm_ip, name, uri)
    return {
        "status": status or "unknown",
        "ip": address or "",
        "cpu": 0.0,
        "ram": {"used": 0, "total": 0, "pct": 0.0},
        "disk": "Managed by libvirt",
        "uptime": "Available from guest",
    }


def persist_vps(user_id: str, node_id: int, name: str, ram: Any, cpu: Any, disk: Any,
                os_version: str, password: str, expiration_date: Optional[str] = None) -> int:
    ensure_schema()
    ram_gb = normalize_ram_gb(ram)
    disk_gb = normalize_disk_gb(disk)
    conn = sqlite3.connect(DB, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO vps
            (user_id,node_id,container_name,ram,cpu,storage,config,os_version,status,
             suspended,whitelisted,created_at,shared_with,suspension_history,expiration_date,root_password)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(user_id), int(node_id), name, f"{ram_gb}GB", str(cpu), f"{disk_gb}GB",
             f"{ram_gb}GB RAM / {int(cpu)} CPU / {disk_gb}GB Disk", os_version, "running",
             0, 0, datetime.now().isoformat(), "[]", "[]", expiration_date, password),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()
