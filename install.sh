#!/usr/bin/env bash
set -Eeuo pipefail
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
APP_DIR="${SNCK_APP_DIR:-/opt/snck-bot}"
PANEL_SERVICE="snck-kvm-panel"; BOT_SERVICE="snck-discord-bot"
VERSION="7.0.0"
E=$'\033';R="${E}[0m";B="${E}[1m";C="${E}[38;5;51m";P="${E}[38;5;141m";G="${E}[38;5;82m";Y="${E}[38;5;220m";M="${E}[38;5;201m";W="${E}[38;5;255m"
[[ -r /dev/tty ]] || { echo "Interactive terminal required."; exit 1; }; exec 3<>/dev/tty
ok(){ printf '%b[ OK ]%b %s\n' "$G" "$R" "$*"; }; info(){ printf '%b[INFO]%b %s\n' "$C" "$R" "$*"; }; fail(){ printf '%b[FAIL]%b %s\n' "$M" "$R" "$*" >&2; exit 1; }
installed(){ [[ -f "$APP_DIR/snck_panel.py" && -f "$APP_DIR/kvm.py" ]]; }
state(){ systemctl is-active --quiet "$1" 2>/dev/null && echo ONLINE || systemctl is-enabled --quiet "$1" 2>/dev/null && echo OFFLINE || echo NOT-INSTALLED; }
kvm(){ [[ -e /dev/kvm ]] && echo ENABLED || echo UNAVAILABLE; }
menu(){ clear 2>/dev/null || true; printf '\n%b╭──────────────────────────────────────────────────────╮%b\n%b│%b  %bSNCK DISCORD VPS DEPLOY BOT + KVM PANEL%b         %b│%b\n%b│%b  %bPremium VPS deployment and customer management%b    %b│%b\n%b╰──────────────────────────────────────────────────────╯%b\n\n' "$P" "$R" "$P" "$R" "$B$W" "$R" "$P" "$R" "$P" "$R" "$C" "$R" "$P" "$R"; printf '%b  LIVE STATUS  %bv%s%b\n' "$C" "$W" "$VERSION" "$R"; printf '  Panel files   : %s\n  Panel service : %s\n  Discord bot   : %s\n  KVM           : %s\n\n' "$([[ -f "$APP_DIR/snck_panel.py" ]] && echo READY || echo NOT-READY)" "$(state "$PANEL_SERVICE")" "$(state "$BOT_SERVICE")" "$(kvm)"; printf '%b  MAIN MENU%b\n\n' "$B$W" "$R"; printf '%b  [1]%b  Install / Repair Snck Panel + KVM\n' "$G" "$R"; printf '%b  [2]%b  Update Panel + Bot\n' "$C" "$R"; printf '%b  [3]%b  Check VPS/KVM status\n' "$Y" "$R"; printf '%b  [4]%b  Restart Panel and Bot\n' "$M" "$R"; printf '%b  [5]%b  Uninstall\n' "$M" "$R"; printf '%b  [0]%b  Exit\n\n' "$P" "$R"; printf '%bSelect an option [0-5]: %b' "$B$W" "$R"; IFS= read -r choice <&3 || true; case "$choice" in 1) install;;2) update;;3) check;;4) restart;;5) uninstall;;0) exit 0;;*) echo "Invalid option."; sleep 1;;esac; }
root(){ [[ $(id -u) -eq 0 ]] || exec sudo -E bash "$0" "$@"; }
install(){ root; info "Installing Ubuntu/Debian KVM dependencies..."; apt-get update -y; DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils cpu-checker openssh-client; systemctl enable --now libvirtd 2>/dev/null || true; mkdir -p "$APP_DIR"; info "Downloading Snck application files..."; for f in snck_panel.py kvm.py bot.py launcher.py snck_panel_bridge.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || fail "Download failed: $f"; done; cd "$APP_DIR"; python3 -m venv venv; "$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null; "$APP_DIR/venv/bin/pip" install -r requirements.txt || fail "Python dependencies failed"; "$APP_DIR/venv/bin/python" -m py_compile *.py || fail "Python syntax check failed"; local pass; pass=$(python3 -c 'import secrets;print(secrets.token_urlsafe(16))'); "$APP_DIR/venv/bin/python" - "$APP_DIR" "$pass" <<'PY'
import sys,sqlite3,hashlib
from pathlib import Path
p=Path(sys.argv[1]);pw=sys.argv[2]
with sqlite3.connect(p/'vps.db') as c:
 c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
 c.execute("INSERT OR REPLACE INTO settings VALUES('license','official.snck.fun')")
 c.execute("INSERT OR REPLACE INTO settings VALUES('license_active','0')")
 c.execute("INSERT OR REPLACE INTO settings VALUES('admin_user','admin')")
 c.execute("INSERT OR REPLACE INTO settings VALUES('admin_pass',?)",(hashlib.sha256(pw.encode()).hexdigest(),))
 c.commit()
PY
 local ip; ip=$(hostname -I | awk '{print $1}'); cat > "$APP_DIR/.env" <<EOF
SNCK_PANEL_PORT=5000
SNCK_PANEL_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
SNCK_PANEL_URL=http://$ip:5000
BOT_NAME=Snck Discord VPS Deploy Bot
PREFIX=!
EOF
 chmod 600 "$APP_DIR/.env"; cat > "/etc/systemd/system/$PANEL_SERVICE.service" <<EOF
[Unit]
Description=Snck KVM Panel
After=network-online.target libvirtd.service
Wants=network-online.target
[Service]
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/snck_panel.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
cat > "/etc/systemd/system/$BOT_SERVICE.service" <<EOF
[Unit]
Description=Snck Discord VPS Deploy Bot
After=network-online.target libvirtd.service
Wants=network-online.target
[Service]
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/launcher.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload; systemctl enable "$PANEL_SERVICE" "$BOT_SERVICE" >/dev/null; systemctl restart "$PANEL_SERVICE"; sleep 2; systemctl is-active --quiet "$PANEL_SERVICE" || { journalctl -u "$PANEL_SERVICE" -n 50 --no-pager; fail "Panel failed to start"; }; ok "Snck KVM Panel is ONLINE"; printf '\n%bINSTALL COMPLETE%b\nPanel: http://%s:5000\nLicense: official.snck.fun\nAdmin user: admin\nAdmin password: %s\n\nOpen the panel, enter the license, then sign in as admin.\nAfter that configure your Discord bot from the panel.\n' "$G" "$R" "$ip" "$pass"; }
update(){ root; installed || { echo "Install the panel first."; return; }; info "Updating Snck panel, KVM and Discord bridge..."; for f in snck_panel.py kvm.py bot.py launcher.py snck_panel_bridge.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || fail "Update failed: $f"; done; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"; "$APP_DIR/venv/bin/python" -m py_compile "$APP_DIR"/*.py; systemctl restart "$PANEL_SERVICE"; [[ -n "$(grep '^DISCORD_TOKEN=' "$APP_DIR/.env" 2>/dev/null || true)" ]] && systemctl restart "$BOT_SERVICE" || true; ok "Updated successfully."; }
check(){ root; echo "Panel: $(state "$PANEL_SERVICE")"; echo "Bot: $(state "$BOT_SERVICE")"; echo "KVM: $(kvm)"; command -v virsh >/dev/null && virsh list --all || true; printf '\nPress Enter... '; IFS= read -r _ <&3 || true; }
restart(){ root; systemctl restart "$PANEL_SERVICE"; systemctl restart "$BOT_SERVICE" 2>/dev/null || true; ok "Services restarted."; }
uninstall(){ root; printf 'Remove Snck panel and local data? [y/N]: '; IFS= read -r x <&3 || true; [[ "$x" =~ ^[Yy]$ ]] || return; systemctl disable --now "$PANEL_SERVICE" "$BOT_SERVICE" 2>/dev/null || true; rm -f "/etc/systemd/system/$PANEL_SERVICE.service" "/etc/systemd/system/$BOT_SERVICE.service"; systemctl daemon-reload; rm -rf "$APP_DIR"; ok "Snck panel removed."; }
while true; do menu; done
