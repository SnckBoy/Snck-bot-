#!/usr/bin/env python3
"""Real KVM/libvirt operations for the Snck KVM Panel."""
import re, shutil, subprocess
from pathlib import Path

DEFAULT_IMAGE = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
TOOLS = ("virsh", "virt-install", "cloud-localds", "qemu-img", "curl")

def run(cmd, timeout=30, check=True):
    try:
        r = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required command is missing: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out: {' '.join(map(str, cmd))}") from exc
    if check and r.returncode:
        msg = (r.stderr or r.stdout or "command failed").strip()
        raise RuntimeError(msg[-3000:])
    return r.stdout.strip()

def virsh(uri, args, timeout=30, check=True):
    return run(["virsh"] + (["-c", uri] if uri else []) + args, timeout, check)

def kvm_available():
    return Path("/dev/kvm").exists()

def tools_ok():
    return all(shutil.which(x) for x in TOOLS)

def missing_tools():
    return [x for x in TOOLS if not shutil.which(x)]

def ensure_default_network(uri=""):
    networks = virsh(uri, ["net-list", "--all", "--name"], 60, check=False)
    if "default" not in networks.splitlines():
        if uri:
            raise RuntimeError("Remote libvirt node has no 'default' network.")
        xml = Path("/usr/share/libvirt/networks/default.xml")
        if not xml.exists():
            raise RuntimeError("Libvirt default network definition is missing.")
        run(["virsh", "net-define", str(xml)], 60)
    virsh(uri, ["net-autostart", "default"], 60, check=False)
    info = virsh(uri, ["net-info", "default"], 60, check=False)
    if not re.search(r"Active:\s+yes", info, re.I):
        virsh(uri, ["net-start", "default"], 60, check=False)
    info = virsh(uri, ["net-info", "default"], 60, check=False)
    if not re.search(r"Active:\s+yes", info, re.I):
        raise RuntimeError("Libvirt default network is not active.")

def domains(uri=""):
    return [x for x in virsh(uri, ["list", "--all", "--name"]).splitlines() if x.strip()]

def state(name, uri=""):
    return virsh(uri, ["domstate", name], check=False).strip().lower() or "unknown"

def ip(name, uri=""):
    out = virsh(uri, ["domifaddr", name, "--source", "lease"], check=False)
    for line in out.splitlines():
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)/\d+", line)
        if m:
            return m.group(1)
    return ""

def start(name, uri=""):
    ensure_default_network(uri)
    return virsh(uri, ["start", name])

def stop(name, uri=""):
    return virsh(uri, ["shutdown", name], check=False)

def force_stop(name, uri=""):
    return virsh(uri, ["destroy", name], check=False)

def reboot(name, uri=""):
    return virsh(uri, ["reboot", name], check=False)

def undefine(name, uri=""):
    return virsh(uri, ["undefine", name, "--nvram"], check=False)

def create(name, ram, cpu, disk, password, image=DEFAULT_IMAGE, storage="/var/lib/libvirt/images", uri=""):
    """Create a local KVM guest from an Ubuntu/Debian cloud image.

    The current panel's default node is local. Remote libvirt URIs are accepted
    for control operations, but image preparation must be performed on the same
    host as the libvirt storage; this prevents creating a VM that points at a
    disk path which exists only on the panel host.
    """
    name = str(name).strip()
    ram, cpu, disk = int(ram), int(cpu), int(disk)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,63}", name):
        raise ValueError("Invalid VPS name")
    if not (512 <= ram <= 1048576):
        raise ValueError("RAM must be 512-1048576 MB")
    if not (1 <= cpu <= 128):
        raise ValueError("CPU must be 1-128")
    if not (5 <= disk <= 16384):
        raise ValueError("Disk must be 5-16384 GB")
    if not password:
        raise ValueError("Root password is required")
    if uri:
        raise RuntimeError("Remote KVM deployment requires node-local storage; configure the node on its KVM host before deploying.")
    missing = missing_tools()
    if missing:
        raise RuntimeError("Missing KVM tools: " + ", ".join(missing))
    if not kvm_available():
        raise RuntimeError("/dev/kvm is unavailable on this host. Use a KVM-capable VPS or enable nested virtualization.")

    ensure_default_network()
    storage = Path(storage).expanduser().resolve()
    storage.mkdir(parents=True, exist_ok=True)
    cache = storage / "snck-cache"
    cache.mkdir(parents=True, exist_ok=True)
    image_name = Path(image.split("?", 1)[0]).name
    img = cache / image_name
    if not img.exists():
        run(["curl", "-fL", "--retry", "3", "--retry-delay", "2", "--connect-timeout", "15", "--max-time", "900", "-o", str(img), image], 920)
    if not img.is_file() or img.stat().st_size < 1024 * 1024:
        img.unlink(missing_ok=True)
        raise RuntimeError("Downloaded OS image is missing or invalid")

    disk_path = storage / f"{name}.qcow2"
    seed_dir = storage / f".snck-seed-{name}"
    seed_iso = storage / f"{name}-seed.iso"
    if disk_path.exists() or seed_iso.exists() or seed_dir.exists():
        raise RuntimeError("VPS files already exist; choose another VPS name or remove the incomplete deployment")

    created_disk = False
    created_domain = False
    try:
        run(["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", str(img), str(disk_path), f"{disk}G"], 120)
        created_disk = True
        seed_dir.mkdir(mode=0o700)
        (seed_dir / "meta-data").write_text(f"instance-id: snck-{name}\nlocal-hostname: {name}\n", encoding="utf-8")
        (seed_dir / "user-data").write_text(
            "#cloud-config\n"
            "ssh_pwauth: true\n"
            "disable_root: false\n"
            "chpasswd:\n"
            "  expire: false\n"
            "  list:\n"
            f"    - root:{password}\n"
            "runcmd:\n"
            "  - [systemctl, enable, --now, ssh]\n",
            encoding="utf-8",
        )
        (seed_dir / "network-config").write_text(
            "version: 2\n"
            "ethernets:\n"
            "  ens3:\n"
            "    dhcp4: true\n",
            encoding="utf-8",
        )
        run(["cloud-localds", "--network-config=" + str(seed_dir / "network-config"), str(seed_iso), str(seed_dir / "user-data"), str(seed_dir / "meta-data")], 60)
        cmd = [
            "virt-install", "--name", name, "--memory", str(ram), "--vcpus", str(cpu),
            "--disk", f"path={disk_path},format=qcow2,bus=virtio",
            "--disk", f"path={seed_iso},device=cdrom",
            "--os-variant", "generic",
            "--network", "network=default,model=virtio",
            "--import", "--noautoconsole",
        ]
        run(cmd, 180)
        created_domain = True
        return str(disk_path)
    except Exception:
        if created_domain:
            force_stop(name)
            undefine(name)
        if created_disk:
            disk_path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(seed_dir, ignore_errors=True)
        seed_iso.unlink(missing_ok=True)

def delete(name, uri="", storage="/var/lib/libvirt/images"):
    force_stop(name, uri)
    undefine(name, uri)
    if not uri:
        (Path(storage).expanduser().resolve() / f"{name}.qcow2").unlink(missing_ok=True)
