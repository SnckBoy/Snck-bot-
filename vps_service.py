#!/usr/bin/env python3
from __future__ import annotations
import os, secrets, sqlite3, string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from kvm import create as kvm_create, delete as kvm_delete, reboot as kvm_reboot, start as kvm_start, stop as kvm_stop, ip as kvm_ip, kvm_available, tools_ok
BASE=Path(__file__).resolve().parent
DB_PATH=Path(os.getenv('SNCK_VPS_DB',str(BASE/'vps.db')))
DEFAULT_STORAGE='/var/lib/libvirt/images'
EXPIRY=int(os.getenv('DEFAULT_VPS_EXPIRATION_DAYS','30'))
IMAGES={'ubuntu:20.04':'https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img','ubuntu:22.04':'https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img','ubuntu:24.04':'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img','images:debian/11':'https://cloud.debian.org/images/cloud/bullseye/latest/debian-11-generic-amd64.qcow2','images:debian/12':'https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2','images:debian/13':'https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2'}
OS_OPTIONS={k:k.replace('images:','').replace(':',' ').title() for k in IMAGES}
def db():
 c=sqlite3.connect(DB_PATH,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA foreign_keys=ON');return c
def init_db():
 with db() as c:
  c.execute("CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,location TEXT,url TEXT,is_local INTEGER DEFAULT 1,storage TEXT NOT NULL DEFAULT '/var/lib/libvirt/images',total_vps INTEGER DEFAULT 100,tags TEXT DEFAULT '[]',api_key TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,node_id INTEGER NOT NULL DEFAULT 1,container_name TEXT UNIQUE NOT NULL,ram TEXT NOT NULL,cpu TEXT NOT NULL,storage TEXT NOT NULL,config TEXT NOT NULL,os_version TEXT DEFAULT 'ubuntu:24.04',status TEXT DEFAULT 'stopped',suspended INTEGER DEFAULT 0,whitelisted INTEGER DEFAULT 0,created_at TEXT NOT NULL,shared_with TEXT DEFAULT '[]',suspension_history TEXT DEFAULT '[]',expiration_date TEXT DEFAULT NULL,root_password TEXT DEFAULT NULL,owner_name TEXT DEFAULT NULL)")
  cols={r['name'] for r in c.execute('PRAGMA table_info(vps)').fetchall()}
  for n,t in {'owner_name':'TEXT DEFAULT NULL','root_password':'TEXT DEFAULT NULL','expiration_date':'TEXT DEFAULT NULL','os_version':"TEXT DEFAULT 'ubuntu:24.04'"}.items():
   if n not in cols:c.execute(f'ALTER TABLE vps ADD COLUMN {n} {t}')
  if not c.execute('SELECT 1 FROM nodes LIMIT 1').fetchone():c.execute("INSERT INTO nodes(name,location,url,is_local,storage,total_vps,tags) VALUES('Local KVM Node','Local','',1,?,100,'[]')",(DEFAULT_STORAGE,))
def node(node_id):
 init_db()
 with db() as c:r=c.execute('SELECT * FROM nodes WHERE id=?',(node_id,)).fetchone()
 if not r:raise ValueError('Node not found')
 return dict(r)
def next_vps_id():
 init_db()
 with db() as c:return int(c.execute('SELECT COALESCE(MAX(id),0)+1 n FROM vps').fetchone()['n'])
def password(n=24):return ''.join(secrets.choice(string.ascii_letters+string.digits+'!@#$%^&*') for _ in range(n))
def valid_name(v):return bool(v and len(v)<=63 and all(x in string.ascii_letters+string.digits+'._-' for x in v))
def create_vps(*,owner_id:str,owner_name:str,name:str,ram_gb:int,cpu:int,disk_gb:int,os_version:str,node_id:int=1,expiry_days:int|None=None,mock:bool=False)->dict[str,Any]:
 init_db()
 if os_version not in IMAGES:raise ValueError('Unsupported operating system')
 if not valid_name(name):raise ValueError('Invalid VPS name')
 if not 1<=ram_gb<=1024 or not 1<=cpu<=128 or not 5<=disk_gb<=16384:raise ValueError('Requested resources are outside allowed limits')
 n=node(node_id)
 with db() as c:
  if c.execute('SELECT 1 FROM vps WHERE container_name=?',(name,)).fetchone():raise ValueError('A VPS with this name already exists')
  used=c.execute('SELECT COUNT(*) n FROM vps WHERE node_id=?',(node_id,)).fetchone()['n']
  if int(n.get('total_vps') or 0)>0 and used>=int(n['total_vps']):raise ValueError('Node capacity is full')
  if not int(n.get('is_local',1)):raise RuntimeError('Remote KVM deployment requires node-local storage and libvirt; configure the remote node before deploying.')
 pw=password();mock_mode=bool(mock or not kvm_available() or not tools_ok())
 if not mock_mode:
  kvm_create(name,ram_gb*1024,cpu,disk_gb,pw,image=IMAGES[os_version],storage=n.get('storage') or DEFAULT_STORAGE);kvm_start(name)
 now=datetime.now(timezone.utc);expiry=now+timedelta(days=expiry_days or EXPIRY)
 with db() as c:
  cur=c.execute("INSERT INTO vps(user_id,node_id,container_name,ram,cpu,storage,config,os_version,status,suspended,whitelisted,created_at,shared_with,suspension_history,expiration_date,root_password,owner_name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(str(owner_id),node_id,name,f'{ram_gb}GB',str(cpu),f'{disk_gb}GB',f'{ram_gb}GB RAM / {cpu} CPU / {disk_gb}GB Disk',os_version,'running',0,0,now.isoformat(),'[]','[]',expiry.isoformat(),pw,owner_name));vid=cur.lastrowid
 return {'id':vid,'owner_id':str(owner_id),'owner_name':owner_name,'name':name,'ram_gb':ram_gb,'cpu':cpu,'disk_gb':disk_gb,'os_version':os_version,'status':'running','password':pw,'mock':mock_mode,'node_id':node_id,'expires':expiry.isoformat()}
def get_vps(vps_id):
 init_db()
 with db() as c:r=c.execute('SELECT * FROM vps WHERE id=?',(vps_id,)).fetchone()
 return dict(r) if r else None
def vps_list():
 init_db()
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM vps ORDER BY id DESC').fetchall()]
def _real():return os.getenv('SNCK_CODESPACE')!='1' and kvm_available() and tools_ok()
def action(vps_id,what):
 v=get_vps(vps_id)
 if not v:raise ValueError('VPS not found')
 if _real():{'start':kvm_start,'stop':kvm_stop,'reboot':kvm_reboot}[what](v['container_name'])
 status={'start':'running','stop':'stopped','reboot':'running'}[what]
 with db() as c:c.execute('UPDATE vps SET status=? WHERE id=?',(status,vps_id))
 return status
def start_vps(vps_id):return action(vps_id,'start')
def stop_vps(vps_id):return action(vps_id,'stop')
def reboot_vps(vps_id):return action(vps_id,'reboot')
def delete_vps(vps_id):
 v=get_vps(vps_id)
 if not v:raise ValueError('VPS not found')
 if _real():kvm_delete(v['container_name'],storage=(node(v['node_id']).get('storage') or DEFAULT_STORAGE))
 with db() as c:c.execute('DELETE FROM vps WHERE id=?',(vps_id,))
 return True
def get_ips(vps_id):
 v=get_vps(vps_id)
 if not v or not _real():return []
 try:
  ip=kvm_ip(v['container_name']);return [ip] if ip else []
 except Exception:return []
