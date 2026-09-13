#!/usr/bin/env bash
set -Eeuo pipefail
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
APP_DIR="${SNCK_APP_DIR:-/opt/snck-bot}"
PANEL_SERVICE="snck-kvm-panel"
BOT_SERVICE="snck-discord-bot"
VERSION="8.2.0"
E=$'\033'; R="${E}[0m"; B="${E}[1m"; C="${E}[38;5;51m"; P="${E}[38;5;141m"; G="${E}[38;5;82m"; Y="${E}[38;5;220m"; M="${E}[38;5;201m"; W="${E}[38;5;255m"; D="${E}[38;5;245m"
[[ -r /dev/tty ]] || { echo "Interactive terminal required."; exit 1; }
exec 3<>/dev/tty
ok(){ printf '%b[ OK ]%b %s\n' "$G" "$R" "$*"; }
info(){ printf '%b[INFO]%b %s\n' "$C" "$R" "$*"; }
fail(){ printf '%b[FAIL]%b %s\n' "$M" "$R" "$*" >&2; return 1; }
state(){ systemctl is-active --quiet "$1" 2>/dev/null && echo ONLINE || systemctl is-enabled --quiet "$1" 2>/dev/null && echo OFFLINE || echo NOT-INSTALLED; }
kvm(){ [[ -e /dev/kvm ]] && echo ENABLED || echo UNAVAILABLE; }
installed(){ [[ -f "$APP_DIR/snck_panel.py" && -f "$APP_DIR/kvm.py" && -f "$APP_DIR/launcher.py" && -f "$APP_DIR/kvm_discord_bridge.py" ]]; }
menu(){
 clear 2>/dev/null || true
 printf '\n%b╭──────────────────────────────────────────────────────╮%b\n' "$P" "$R"
 printf '%b│%b  %bSNCK DISCORD VPS DEPLOY BOT + KVM PANEL%b       %b│%b\n' "$P" "$R" "$B$W" "$R" "$P"
 printf '%b│%b  %bPremium KVM virtualization and Discord control%b  %b│%b\n' "$P" "$R" "$C" "$R" "$P"
 printf '%b╰──────────────────────────────────────────────────────╯%b\n\n' "$P" "$R"
 printf '%b  LIVE STATUS  %bv%s%b\n' "$C" "$W" "$VERSION" "$R"
 printf '  Panel files   : %s\n' "$(installed && echo READY || echo NOT-READY)"
 printf '  Panel service : %s\n' "$(state "$PANEL_SERVICE")"
 printf '  Discord bot   : %s\n' "$(state "$BOT_SERVICE")"
 printf '  KVM           : %s\n\n' "$(kvm)"
 printf '%b  MAIN MENU%b\n\n' "$B$W" "$R"
 printf '%b  [1]%b  Install / Repair Snck Panel + KVM\n' "$G" "$R"
 printf '%b  [2]%b  Update Panel + Bot\n' "$C" "$R"
 printf '%b  [3]%b  Check VPS / KVM Status\n' "$Y" "$R"
 printf '%b  [4]%b  Restart Panel and Bot\n' "$M" "$R"
 printf '%b  [5]%b  Uninstall\n' "$M" "$R"
 printf '%b  [0]%b  Exit\n\n' "$P" "$R"
 printf '%bSelect an option [0-5]: %b' "$B$W" "$R"
 IFS= read -r choice <&3 || true
 case "$choice" in 1) install;; 2) update;; 3) check;; 4) restart;; 5) uninstall;; 0) exit 0;; *) echo "Invalid option."; sleep 1;; esac
}
root(){ [[ $(id -u) -eq 0 ]] || exec sudo -E bash "$0" "$@"; }
write_env(){
 mkdir -p "$APP_DIR"
 local secret token client guild public old_secret
 token=""; client=""; guild=""; public=""; old_secret=""
 if [[ -f "$APP_DIR/.env" ]]; then
  token="$(grep '^DISCORD_TOKEN=' "$APP_DIR/.env" | head -n1 | cut -d= -f2- || true)"
  client="$(grep '^DISCORD_CLIENT_ID=' "$APP_DIR/.env" | head -n1 | cut -d= -f2- || true)"
  guild="$(grep '^DISCORD_GUILD_ID=' "$APP_DIR/.env" | head -n1 | cut -d= -f2- || true)"
  public="$(grep '^DISCORD_PUBLIC_KEY=' "$APP_DIR/.env" | head -n1 | cut -d= -f2- || true)"
  old_secret="$(grep '^SNCK_PANEL_SECRET=' "$APP_DIR/.env" | head -n1 | cut -d= -f2- || true)"
 fi
 secret="${old_secret:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
 cat > "$APP_DIR/.env" <<EOF
SNCK_PANEL_PORT=5000
SNCK_PANEL_SECRET=$secret
BOT_NAME=Snck Discord VPS Deploy Bot
PREFIX=!
EOF
 [[ -n "$token" ]] && printf 'DISCORD_TOKEN=%s\n' "$token" >> "$APP_DIR/.env"
 [[ -n "$client" ]] && printf 'DISCORD_CLIENT_ID=%s\n' "$client" >> "$APP_DIR/.env"
 [[ -n "$guild" ]] && printf 'DISCORD_GUILD_ID=%s\n' "$guild" >> "$APP_DIR/.env"
 [[ -n "$public" ]] && printf 'DISCORD_PUBLIC_KEY=%s\n' "$public" >> "$APP_DIR/.env"
 chmod 600 "$APP_DIR/.env"
}
download_files(){
 local f
 for f in snck_panel_v2.py kvm.py bot.py launcher.py snck_panel_bridge.py kvm_discord_bridge.py requirements.txt; do
  info "Downloading $f..."
  curl -fsSL --retry 3 --connect-timeout 15 --max-time 180 "$REPO_RAW/$f" -o "$APP_DIR/$f" || { fail "Download failed: $f"; return 1; }
 done
 cp "$APP_DIR/snck_panel_v2.py" "$APP_DIR/snck_panel.py"
}
install_deps(){
 info "Installing Ubuntu/Debian KVM dependencies..."
 apt-get update -y || { fail "apt update failed"; return 1; }
 DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils openssh-client || { fail "System packages failed"; return 1; }
 systemctl enable --now libvirtd 2>/dev/null || systemctl enable --now libvirt 2>/dev/null || true
}
setup_python(){
 cd "$APP_DIR"
 [[ -d venv ]] || python3 -m venv venv
 "$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null || { fail "pip upgrade failed"; return 1; }
 "$APP_DIR/venv/bin/pip" install -r requirements.txt || { fail "Python dependencies failed"; return 1; }
 "$APP_DIR/venv/bin/python" -m py_compile snck_panel.py kvm.py bot.py launcher.py snck_panel_bridge.py kvm_discord_bridge.py || { fail "Python syntax check failed"; return 1; }
}
write_services(){
 cat > "/etc/systemd/system/$PANEL_SERVICE.service" <<EOF
[Unit]
Description=Snck KVM Panel
After=network-online.target libvirtd.service
Wants=network-online.target
[Service]
Type=simple
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
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/launcher.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
}
install(){
 root
 install_deps || return 1
 mkdir -p "$APP_DIR"
 info "Downloading latest Snck application..."
 download_files || return 1
 setup_python || return 1
 write_env
 write_services
 systemctl daemon-reload
 systemctl enable "$PANEL_SERVICE" "$BOT_SERVICE" >/dev/null
 systemctl restart "$PANEL_SERVICE"
 sleep 2
 if ! systemctl is-active --quiet "$PANEL_SERVICE"; then journalctl -u "$PANEL_SERVICE" -n 80 --no-pager; fail "Panel failed to start"; return 1; fi
 if grep -q '^DISCORD_TOKEN=' "$APP_DIR/.env" 2>/dev/null; then systemctl restart "$BOT_SERVICE"; sleep 2; fi
 ok "Snck KVM Panel is ONLINE"
 local addr; addr="$(hostname -I 2>/dev/null | awk '{print $1}')"
 printf '\n%bINSTALL COMPLETE%b\nPanel: http://%s:5000\nLicense: official.snck.fun\nAdmin: create on first login\nDiscord bot: configure from the panel\n\n' "$G" "$R" "${addr:-YOUR-SERVER-IP}"
}
update(){
 root
 printf '\n%b[ UPDATE ]%b Starting Snck Panel + Bot update...\n' "$C" "$R"
 install_deps || return 1
 mkdir -p "$APP_DIR"
 info "Downloading latest panel, KVM, bridge and Discord files..."
 download_files || return 1
 setup_python || return 1
 write_env
 write_services
 systemctl daemon-reload
 systemctl enable "$PANEL_SERVICE" "$BOT_SERVICE" >/dev/null 2>&1 || true
 info "Restarting Snck panel..."
 systemctl restart "$PANEL_SERVICE" || { journalctl -u "$PANEL_SERVICE" -n 60 --no-pager; fail "Panel restart failed"; return 1; }
 if grep -q '^DISCORD_TOKEN=' "$APP_DIR/.env" 2>/dev/null; then
  info "Restarting Discord bot..."
  systemctl restart "$BOT_SERVICE" || { journalctl -u "$BOT_SERVICE" -n 60 --no-pager; fail "Bot restart failed"; return 1; }
 fi
 sleep 2
 ok "Snck update completed successfully."
 printf '  Panel: %s\n' "$(state "$PANEL_SERVICE")"
 printf '  Bot  : %s\n' "$(state "$BOT_SERVICE")"
 printf '  KVM  : %s\n' "$(kvm)"
 printf '  Version: %s\n' "$VERSION"
 printf '%bReturning to menu...%b\n' "$C" "$R"
 sleep 1
}
check(){
 root
 echo "Panel: $(state "$PANEL_SERVICE")"
 echo "Bot: $(state "$BOT_SERVICE")"
 echo "KVM: $(kvm)"
 if command -v virsh >/dev/null 2>&1; then echo "Libvirt domains:"; virsh list --all || true; fi
 printf '\nPress Enter... '; IFS= read -r _ <&3 || true
}
restart(){ root; systemctl restart "$PANEL_SERVICE" 2>/dev/null || true; systemctl restart "$BOT_SERVICE" 2>/dev/null || true; ok "Services restarted."; }
uninstall(){
 root
 printf 'Remove Snck panel files and local database? [y/N]: '
 IFS= read -r x <&3 || true
 [[ "$x" =~ ^[Yy]$ ]] || return
 systemctl disable --now "$PANEL_SERVICE" "$BOT_SERVICE" 2>/dev/null || true
 rm -f "/etc/systemd/system/$PANEL_SERVICE.service" "/etc/systemd/system/$BOT_SERVICE.service"
 systemctl daemon-reload
 rm -rf "$APP_DIR"
 ok "Snck panel removed. Existing libvirt VMs are not automatically deleted."
}
while true; do menu; done
