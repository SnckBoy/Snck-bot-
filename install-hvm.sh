#!/usr/bin/env bash
set -Eeuo pipefail
APP="${SNCK_APP_DIR:-/opt/snck-bot}"; REPO="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"; PORT="${SNCK_PANEL_PORT:-5000}"
log(){ printf '[Snck] %s\n' "$*"; }; die(){ printf '[Snck][ERROR] %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" "$@"
mkdir -p "$APP"; export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils openssh-client
# Ubuntu 24.04 uses lxd-installer for first-use LXD installation; KVM remains the HVM backend.
apt-get install -y --no-install-recommends lxd-installer 2>/dev/null || true
for f in snck_hvm_panel.py vps_service.py kvm.py kvm_discord_bridge.py bot.py launcher.py snck_panel_bridge.py requirements.txt; do log "Downloading $f"; curl -fsSL --retry 3 --connect-timeout 15 --max-time 300 "$REPO/$f" -o "$APP/$f"; done
[ -x "$APP/venv/bin/python" ] || python3 -m venv "$APP/venv"
"$APP/venv/bin/python" -m pip install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"
python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('/opt/snck-bot/.env')
old={}
if p.exists():
 for line in p.read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1);old[k]=v
vals={'SNCK_PANEL_HOST':old.get('SNCK_PANEL_HOST','0.0.0.0'),'SNCK_PANEL_PORT':old.get('SNCK_PANEL_PORT','5000'),'SNCK_PANEL_SECRET':old.get('SNCK_PANEL_SECRET',secrets.token_hex(32)),'SNCK_CODESPACE':'0','SNCK_LICENSE_KEY':old.get('SNCK_LICENSE_KEY','official.snck.fun'),'DEFAULT_STORAGE_POOL':old.get('DEFAULT_STORAGE_POOL','default'),'DEFAULT_VPS_EXPIRATION_DAYS':old.get('DEFAULT_VPS_EXPIRATION_DAYS','30')}
for k in ('DISCORD_TOKEN','DISCORD_GUILD_ID','MAIN_ADMIN_ID','VPS_USER_ROLE_ID','DEPLOY_ROLE_ID','DEPLOY_RAM','DEPLOY_CPU','DEPLOY_DISK','DEPLOY_SLOT','VPS_DEPLOY_LIMIT'):
 if k in old: vals[k]=old[k]
p.write_text(''.join(f'{k}={v}\n' for k,v in vals.items()));p.chmod(0o600)
PY
"$APP/venv/bin/python" -m py_compile "$APP/snck_hvm_panel.py" "$APP/vps_service.py" "$APP/kvm.py" "$APP/kvm_discord_bridge.py" "$APP/bot.py" "$APP/launcher.py"
cat >/usr/local/bin/snck-hvm <<EOF
#!/usr/bin/env bash
set -e
APP="$APP"
case "\${1:-status}" in
 start) nohup "\$APP/venv/bin/python" "\$APP/snck_hvm_panel.py" >>"\$APP/panel.log" 2>&1 & echo \$! >"\$APP/panel.pid"; [ -n "\${DISCORD_TOKEN:-}" ] && nohup "\$APP/venv/bin/python" "\$APP/launcher.py" >>"\$APP/bot.log" 2>&1 & echo \$! >"\$APP/bot.pid" || true;;
 stop) [ -f "\$APP/panel.pid" ] && kill "\$(cat \$APP/panel.pid)" 2>/dev/null || true; [ -f "\$APP/bot.pid" ] && kill "\$(cat \$APP/bot.pid)" 2>/dev/null || true;;
 status) curl -fsS "http://127.0.0.1:$PORT/health" || true;;
 logs) tail -n 100 "\$APP/panel.log" 2>/dev/null || true; tail -n 100 "\$APP/bot.log" 2>/dev/null || true;;
 *) echo 'Usage: snck-hvm {start|stop|status|logs}'; exit 2;; esac
EOF
chmod +x /usr/local/bin/snck-hvm
nohup "$APP/venv/bin/python" "$APP/snck_hvm_panel.py" >"$APP/panel.log" 2>&1 & echo $! >"$APP/panel.pid"
for i in $(seq 1 30); do curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null || { cat "$APP/panel.log" >&2; exit 1; }
if grep -q '^DISCORD_TOKEN=' "$APP/.env"; then set -a; . "$APP/.env"; set +a; nohup "$APP/venv/bin/python" "$APP/launcher.py" >"$APP/bot.log" 2>&1 & echo $! >"$APP/bot.pid"; fi
log "INSTALL COMPLETE"; log "Panel: http://SERVER-IP:$PORT"; log "Health: http://SERVER-IP:$PORT/health"; log "Discord token: configure DISCORD_TOKEN in $APP/.env, then run: snck-hvm start"