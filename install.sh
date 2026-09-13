#!/usr/bin/env bash
set -u
REPO=https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main
APP=${SNCK_APP_DIR:-/opt/snck-bot}; PS=snck-kvm-panel; BS=snck-discord-bot; V=8.2.9
C=$'\033[38;5;51m';P=$'\033[38;5;141m';G=$'\033[38;5;82m';Y=$'\033[38;5;220m';R=$'\033[0m'
[ -r /dev/tty ] || { echo 'Interactive terminal required.'; exit 1; }
exec 3<>/dev/tty
root(){ [ "$(id -u)" = 0 ] || exec sudo -E bash "$0" "$@"; }
st(){ systemctl is-active --quiet "$1" 2>/dev/null && echo ONLINE || systemctl is-enabled --quiet "$1" 2>/dev/null && echo OFFLINE || echo NOT-INSTALLED; }
get(){
  mkdir -p "$APP" || return 1
  for f in snck_panel_v2.py kvm.py kvm_discord_bridge.py bot.py launcher.py panel_bridge.py snck_panel_bridge.py requirements.txt patch_panel_bot_setup.py patch_kvm_runtime.py branding_patch.py; do
    printf '%b[INFO]%b Downloading %s\n' "$C" "$R" "$f"
    curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 "$REPO/$f" -o "$APP/$f" || { echo "Download failed: $f"; return 1; }
  done
  cp "$APP/snck_panel_v2.py" "$APP/snck_panel.py" || return 1
}
network(){
  command -v virsh >/dev/null 2>&1 || return 1
  virsh net-list --all --name 2>/dev/null | grep -qx default || {
    [ -f /usr/share/libvirt/networks/default.xml ] || return 1
    virsh net-define /usr/share/libvirt/networks/default.xml >/dev/null 2>&1 || return 1
  }
  virsh net-autostart default >/dev/null 2>&1 || :
  if ! virsh net-info default 2>/dev/null | grep -qi 'Active:.*yes'; then virsh net-start default >/dev/null 2>&1 || :; fi
  virsh net-info default 2>/dev/null | grep -qi 'Active:.*yes'
}
env(){
  local t='' c='' g='' p='' s o=''
  s=$(python3 -c 'import secrets;print(secrets.token_hex(32))') || return 1
  if [ -f "$APP/.env" ]; then
    t=$(grep '^DISCORD_TOKEN=' "$APP/.env" | head -1 | cut -d= -f2- || :)
    c=$(grep '^DISCORD_CLIENT_ID=' "$APP/.env" | head -1 | cut -d= -f2- || :)
    g=$(grep '^DISCORD_GUILD_ID=' "$APP/.env" | head -1 | cut -d= -f2- || :)
    p=$(grep '^DISCORD_PUBLIC_KEY=' "$APP/.env" | head -1 | cut -d= -f2- || :)
    o=$(grep '^SNCK_PANEL_SECRET=' "$APP/.env" | head -1 | cut -d= -f2- || :); [ -n "$o" ] && s=$o
  fi
  cat >"$APP/.env" <<EOF
SNCK_PANEL_PORT=5000
SNCK_PANEL_SECRET=$s
BOT_NAME=Snck Discord VPS Deploy Bot
BOT_DEVELOPER=Clark
BOT_ICON_URL=https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/assets/snck-logo.svg
BOT_THUMBNAIL_URL=https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/assets/snck-logo.svg
PREFIX=!
EOF
  [ -n "$t" ] && printf 'DISCORD_TOKEN=%s\n' "$t" >>"$APP/.env"
  [ -n "$c" ] && printf 'DISCORD_CLIENT_ID=%s\n' "$c" >>"$APP/.env"
  [ -n "$g" ] && printf 'DISCORD_GUILD_ID=%s\n' "$g" >>"$APP/.env"
  [ -n "$p" ] && printf 'DISCORD_PUBLIC_KEY=%s\n' "$p" >>"$APP/.env"
  chmod 600 "$APP/.env"
}
svc(){
  cat >/etc/systemd/system/$PS.service <<EOF
[Unit]
Description=Snck KVM Panel
After=network-online.target libvirtd.service
[Service]
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python $APP/snck_panel.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  cat >/etc/systemd/system/$BS.service <<EOF
[Unit]
Description=Snck Discord VPS Deploy Bot
After=network-online.target libvirtd.service
[Service]
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python $APP/launcher.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$PS" "$BS" >/dev/null 2>&1 || return 1
}
prepare(){
  root
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a APT_LISTCHANGES_FRONTEND=none
  apt-get update -y || return 1
  apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils openssh-client || return 1
  systemctl enable --now libvirtd >/dev/null 2>&1 || systemctl enable --now libvirt >/dev/null 2>&1 || return 1
  get || return 1
  [ -d "$APP/venv" ] || python3 -m venv "$APP/venv" || return 1
  "$APP/venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements.txt" || return 1
  network || { echo 'KVM network setup failed.'; return 1; }
  "$APP/venv/bin/python" "$APP/patch_panel_bot_setup.py" || return 1
  "$APP/venv/bin/python" "$APP/patch_kvm_runtime.py" || return 1
  "$APP/venv/bin/python" "$APP/branding_patch.py" || return 1
  "$APP/venv/bin/python" -m py_compile "$APP"/*.py || return 1
  env || return 1
  svc || return 1
}
install(){ echo 'Installing Snck Panel + Bot + KVM...'; prepare || { echo 'INSTALL FAILED'; return; }; systemctl restart "$PS" || { echo 'Panel failed to start'; journalctl -u "$PS" -n 50 --no-pager; return; }; sleep 2; [ "$(st "$PS")" = ONLINE ] || { journalctl -u "$PS" -n 50 --no-pager; return; }; if grep -q '^DISCORD_TOKEN=' "$APP/.env" 2>/dev/null; then systemctl restart "$BS" || :; fi; echo 'INSTALL COMPLETE'; }
update(){ echo 'Updating Snck Panel + Bot...'; prepare || { echo 'UPDATE FAILED'; return; }; systemctl restart "$PS" || return; if grep -q '^DISCORD_TOKEN=' "$APP/.env" 2>/dev/null; then systemctl restart "$BS" || :; fi; echo "UPDATE COMPLETE - $V"; }
check(){ root; echo "Panel: $(st "$PS")"; echo "Bot: $(st "$BS")"; echo "KVM: $([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"; echo "Tools: $(command -v virsh >/dev/null && command -v virt-install >/dev/null && command -v cloud-localds >/dev/null && command -v qemu-img >/dev/null && echo READY || echo MISSING)"; command -v virsh >/dev/null 2>&1 && virsh list --all || :; printf 'Press Enter... '; read -r _ <&3 || :; }
restart(){ root; systemctl restart "$PS" 2>/dev/null || :; systemctl restart "$BS" 2>/dev/null || :; echo 'Services restarted.'; }
uninstall(){
  root
  echo
  echo 'SNCK PANEL + BOT UNINSTALL'
  echo 'Removing Snck Panel + Bot...'
  systemctl stop "$PS" "$BS" 2>/dev/null || true
  systemctl disable "$PS" "$BS" 2>/dev/null || true
  systemctl mask "$PS" "$BS" 2>/dev/null || true
  rm -f "/etc/systemd/system/$PS.service" "/etc/systemd/system/$BS.service" "/etc/systemd/system/multi-user.target.wants/$PS.service" "/etc/systemd/system/multi-user.target.wants/$BS.service"
  systemctl unmask "$PS" "$BS" 2>/dev/null || true
  systemctl daemon-reload
  systemctl reset-failed "$PS" "$BS" 2>/dev/null || true
  pkill -TERM -f "$APP/.*python" 2>/dev/null || true
  sleep 1
  pkill -KILL -f "$APP/.*python" 2>/dev/null || true
  rm -rf "$APP"
  echo 'SNCK PANEL + BOT UNINSTALLED SUCCESSFULLY'
  echo 'Uninstall complete. Returning to shell.'
  exec 3>&-
  exit 0
}
while :; do
  clear 2>/dev/null || :
  printf '\n%bSNCK DISCORD VPS DEPLOY BOT + KVM PANEL%b\n%bLIVE STATUS%b v%s\nPanel: %s | Bot: %s | KVM: %s\n\n[1] Install / Repair\n[2] Update Panel + Bot\n[3] Check VPS / KVM Status\n[4] Restart Panel and Bot\n[5] Uninstall Snck Panel + Bot\n[0] Exit\n\nSelect an option [0-5]: ' "$P" "$R" "$C" "$R" "$V" "$(st "$PS")" "$(st "$BS")" "$([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"
  read -r n <&3 || n=''
  case $n in 1) install;; 2) update;; 3) check;; 4) restart;; 5) uninstall;; 0) exit 0;; *) echo 'Invalid option.'; sleep 1;; esac
done