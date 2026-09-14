#!/usr/bin/env python3
"""Shared KVM backend for the Snck Discord bot and web panel."""
from __future__ import annotations
import asyncio, sqlite3
from datetime import datetime
from pathlib import Path
from kvm import create as kvm_create, delete as kvm_delete, start as kvm_start, stop as kvm_stop, reboot as kvm_reboot, state as kvm_state, ip as kvm_ip
BASE=Path(__file__).resolve().parent
DB=BASE/'vps.db'
IMAGE_MAP={'ubuntu:20.04':'https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img','ubuntu:22.04':'https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img','ubuntu:24.04':'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img','images:debian/10':'https://cloud.debian.org/images/cloud/buster/latest/debian-10-generic-amd64.qcow2','images:debian/11':'https://cloud.debian.org/images/cloud/bullseye/latest/debian-11-generic-amd64.qcow2','images:debian/12':'https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2','images:debian/13':'https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2'}

def ensure_schema():
    conn=sqlite3.connect(DB,timeout=30); conn.execute('PRAGMA journal_mode=WAL')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,location TEXT,url TEXT,is_local INTEGER DEFAULT 1,storage TEXT NOT NULL DEFAULT '/var/lib/libvirt/images',total_vps INTEGER DEFAULT 100,tags TEXT DEFAULT '[]',api_key TEXT)''')
        ncols={r[1] for r in conn.execute('PRAGMA table_info(nodes)').fetchall()}
        for n,t in {'location':'TEXT','url':'TEXT','is_local':'INTEGER DEFAULT 1','storage':"TEXT NOT NULL DEFAULT '/var/lib/libvirt/images'",'total_vps':'INTEGER DEFAULT 100','tags':"TEXT DEFAULT '[]'",'api_key':'TEXT'}.items():
            if n not in ncols: conn.execute(f'ALTER TABLE nodes ADD COLUMN {n} {t}')
        conn.execute('''CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,node_id INTEGER NOT NULL DEFAULT 1,container_name TEXT UNIQUE NOT NULL,ram TEXT NOT NULL,cpu TEXT NOT NULL,storage TEXT NOT NULL,config TEXT NOT NULL,os_version TEXT DEFAULT 'ubuntu:24.04',status TEXT DEFAULT 'stopped',suspended INTEGER DEFAULT 0,whitelisted INTEGER DEFAULT 0,created_at TEXT NOT NULL,shared_with TEXT DEFAULT '[]',suspension_history TEXT DEFAULT '[]',expiration_date TEXT DEFAULT NULL,root_password TEXT DEFAULT NULL)''')
        vcols={r[1] for r in conn.execute('PRAGMA table_info(vps)').fetchall()}
        for n,t in {'node_id':'INTEGER DEFAULT 1','os_version':"TEXT DEFAULT 'ubuntu:24.04'",'suspended':'INTEGER DEFAULT 0','whitelisted':'INTEGER DEFAULT 0','shared_with':"TEXT DEFAULT '[]'",'suspension_history':"TEXT DEFAULT '[]'",'expiration_date':'TEXT DEFAULT NULL','root_password':'TEXT DEFAULT NULL'}.items():
            if n not in vcols: conn.execute(f'ALTER TABLE vps ADD COLUMN {n} {t}')
        if not conn.execute('SELECT 1 FROM nodes').fetchone(): conn.execute("INSERT INTO nodes(name,location,url,is_local,storage,total_vps,tags) VALUES('Local KVM Node','Local','',1,'/var/lib/libvirt/images',100,'[]')")
        conn.commit()
    finally: conn.close()

def node_uri(node):
    node=node or {}
    return str(node.get('url') or node.get('uri') or '')

def ram_gb(v):
    s=str(v).strip().lower().replace(' ','')
    if s.endswith('mb'): return max(1,int(float(s[:-2])/1024))
    if s.endswith('gb'): return max(1,int(float(s[:-2])))
    return max(1,int(float(s)))

def disk_gb(v):
    s=str(v).strip().lower().replace(' ','')
    return int(float(s[:-2])) if s.endswith('gb') else int(float(s))

async def deploy(name,ram,cpu,disk,password,os_version='ubuntu:24.04',storage='/var/lib/libvirt/images',uri=''):
    ensure_schema(); image=IMAGE_MAP.get(os_version,IMAGE_MAP['ubuntu:24.04'])
    await asyncio.to_thread(kvm_create,name,ram_gb(ram)*1024,int(cpu),disk_gb(disk),password,image=image,storage=storage,uri=uri)
    return await start(name,uri)

async def start(name,uri=''):
    try: await asyncio.to_thread(kvm_start,name,uri)
    except Exception as e:
        if 'already running' not in str(e).lower(): raise
    return 'running'

async def stop(name,uri=''):
    await asyncio.to_thread(kvm_stop,name,uri); return 'stopped'

async def reboot(name,uri=''):
    await asyncio.to_thread(kvm_reboot,name,uri); return 'running'

async def delete(name,uri='',storage='/var/lib/libvirt/images'):
    await asyncio.to_thread(kvm_delete,name,uri,storage); return 'deleted'

async def stats(name,uri=''):
    status=await asyncio.to_thread(kvm_state,name,uri); address=await asyncio.to_thread(kvm_ip,name,uri)
    return {'status':status or 'unknown','ip':address or '','cpu':0.0,'ram':{'used':0,'total':0,'pct':0.0},'disk':'Managed by libvirt','uptime':'Available from guest'}

def persist_vps(user_id,node_id,name,ram,cpu,disk,os_version,password,expiration_date=None):
    ensure_schema(); rg=ram_gb(ram); dg=disk_gb(disk); now=datetime.now().isoformat(); conn=sqlite3.connect(DB,timeout=30)
    try:
        cur=conn.cursor(); cur.execute('''INSERT INTO vps(user_id,node_id,container_name,ram,cpu,storage,config,os_version,status,suspended,whitelisted,created_at,shared_with,suspension_history,expiration_date,root_password) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(str(user_id),int(node_id),name,f'{rg}GB',str(cpu),f'{dg}GB',f'{rg}GB RAM / {int(cpu)} CPU / {dg}GB Disk',os_version,'running',0,0,now,'[]','[]',expiration_date,password)); conn.commit(); return cur.lastrowid
    finally: conn.close()
