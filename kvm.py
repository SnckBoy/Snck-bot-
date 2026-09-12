#!/usr/bin/env python3
"""Real KVM/libvirt operations for Snck KVM Panel."""
import re, shutil, subprocess
from pathlib import Path
DEFAULT_IMAGE="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
def run(cmd,timeout=30,check=True):
    r=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    if check and r.returncode: raise RuntimeError((r.stderr or r.stdout or "command failed").strip()[-2000:])
    return r.stdout.strip()
def virsh(uri,args,timeout=30,check=True):
    return run(["virsh"]+(["-c",uri] if uri else [])+args,timeout,check)
def kvm_available(): return Path("/dev/kvm").exists()
def tools_ok(): return all(shutil.which(x) for x in ("virsh","virt-install","cloud-localds","qemu-img"))
def domains(uri=""): return [x for x in virsh(uri,["list","--all","--name"]).splitlines() if x.strip()]
def state(name,uri=""): return virsh(uri,["domstate",name],check=False).strip().lower() or "unknown"
def ip(name,uri=""):
    out=virsh(uri,["domifaddr",name,"--source","lease"],check=False)
    for line in out.splitlines():
        m=re.search(r"(\d+\.\d+\.\d+\.\d+)/\d+",line)
        if m:return m.group(1)
    return ""
def start(n,u=""): return virsh(u,["start",n])
def stop(n,u=""): return virsh(u,["shutdown",n],check=False)
def force_stop(n,u=""): return virsh(u,["destroy",n],check=False)
def reboot(n,u=""): return virsh(u,["reboot",n],check=False)
def undefine(n,u=""): return virsh(u,["undefine",n,"--nvram"],check=False)
def create(name,ram,cpu,disk,password,image=DEFAULT_IMAGE,storage="/var/lib/libvirt/images",uri=""):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,63}",name): raise ValueError("Invalid VPS name")
    if not(512<=int(ram)<=1048576): raise ValueError("RAM must be 512-1048576 MB")
    if not(1<=int(cpu)<=128): raise ValueError("CPU must be 1-128")
    if not(5<=int(disk)<=16384): raise ValueError("Disk must be 5-16384 GB")
    storage=Path(storage); storage.mkdir(parents=True,exist_ok=True)
    cache=storage/"snck-cache"; cache.mkdir(parents=True,exist_ok=True)
    img=cache/Path(image.split("?")[0]).name
    if not img.exists(): run(["curl","-fL","--retry","3","-o",str(img),image],900)
    d=storage/(name+".qcow2")
    if d.exists(): raise RuntimeError("VPS disk already exists")
    run(["qemu-img","create","-f","qcow2","-F","qcow2","-b",str(img),str(d),f"{disk}G"],120)
    seed=storage/(name+"-seed"); seed.mkdir()
    (seed/"meta-data").write_text(f"instance-id: snck-{name}\nlocal-hostname: {name}\n")
    (seed/"user-data").write_text("#cloud-config\nssh_pwauth: true\ndisable_root: false\nchpasswd:\n  expire: false\n  list:\n    - root:"+password+"\nruncmd:\n  - [systemctl, enable, --now, ssh]\n")
    (seed/"network-config").write_text("version: 2\nethernets:\n  ens3:\n    dhcp4: true\n")
    iso=storage/(name+"-seed.iso")
    run(["cloud-localds","--network-config="+str(seed/"network-config"),str(iso),str(seed/"user-data"),str(seed/"meta-data")],60)
    cmd=["virt-install","--name",name,"--memory",str(ram),"--vcpus",str(cpu),"--disk",f"path={d},format=qcow2,bus=virtio","--disk",f"path={iso},device=cdrom","--os-variant","ubuntu24.04","--network","network=default,model=virtio","--import","--noautoconsole"]
    if uri: cmd += ["--connect",uri]
    try: run(cmd,120)
    except Exception:
        d.unlink(missing_ok=True); raise
    finally:
        for x in seed.glob("*"): x.unlink(missing_ok=True)
        seed.rmdir(); iso.unlink(missing_ok=True)
    return str(d)
def delete(name,uri="",storage="/var/lib/libvirt/images"):
    force_stop(name,uri); undefine(name,uri); (Path(storage)/(name+".qcow2")).unlink(missing_ok=True)
