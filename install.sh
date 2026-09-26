#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${SNCK_REPO_URL:-https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main}"
APP="${SNCK_APP_DIR:-/opt/snck-bot}"
PS=snck-kvm-panel
BS=snck-discord-bot
V="9.0.0"
C=$'\033[38;5;51m'; P=$'\033[38;5;141m'; R=$'\033[0m'

[ -r /dev/tty ] || { echo 'Interactive terminal required.'; exit 1; }
exec 3<>/dev/tty

root(){ [ "$(id -u)" = 0 ] || exec sudo -E bash "$0" "$@"; }
st(){ systemctl is-active --quiet "$1" 2>/dev/null && echo ONLINE || systemctl is-enabled --quiet "$1" 2>/dev/null && echo OFFLINE || echo NOT-INSTALLED; }

get(){
  mkdir -p "$APP"
  for f in snck_panel_fixed.py kvm.py kvm_discord_bridge.py bot.py launcher.py requirements.txt; do
    printf '%b[INFO]%b Downloading %s\n' "$C" "$R" "$f"
    curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 "$REPO/$f" -o "$APP/$f"
  done
  cp "$APP/snck_panel_fixed.py" "$APP/snck_panel.py"
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

env_setup(){
  local secret token client guild public old
  secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  token='' client='' guild='' public='' old=''
  if [ -f "$APP/.env" ]; then
    token="$(grep '^DISCORD_TOKEN=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    client="$(grep '^DISCORD_CLIENT_ID=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    guild="$(grep '^DISCORD_GUILD_ID=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    public="$(grep '^DISCORD_PUBLIC_KEY=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    old="$(grep '^SNCK_PANEL_SECRET=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    [ -n "$old" ] && secret="$old"
  fi
  {
    printf 'SNCK_PANEL_PORT=5000\n'
    printf 'SNCK_PANEL_SECRET=%s\n' "$secret"
    printf 'SNCK_COOKIE_SECURE=0\n'
    printf 'BOT_NAME=Snck Discord VPS Deploy Bot\n'
    printf 'BOT_DEVELOPER=Clark\n'
    printf 'PREFIX=!\n'
    [ -n "$token" ] && printf 'DISCORD_TOKEN=%s\n' "$token"
    [ -n "$client" ] && printf 'DISCORD_CLIENT_ID=%s\n' "$client"
    [ -n "$guild" ] && printf 'DISCORD_GUILD_ID=%s\n' "$guild"
    [ -n "$public" ] && printf 'DISCORD_PUBLIC_KEY=%s\n' "$public"
  } >"$APP/.env"
  chmod 600 "$APP/.env"
}

svc(){
  cat >"/etc/systemd/system/$PS.service" <<EOF
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
  cat >"/etc/systemd/system/$BS.service" <<EOF
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
  systemctl enable "$PS" "$BS" >/dev/null
}

prepare(){
  root
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a APT_LISTCHANGES_FRONTEND=none
  apt-get update -y
  apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils openssh-client
  systemctl enable --now libvirtd >/dev/null 2>&1 || systemctl enable --now libvirt >/dev/null 2>&1
  get
  [ -d "$APP/venv" ] || python3 -m venv "$APP/venv"
  "$APP/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
  "$APP/venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements.txt"
  network
  "$APP/venv/bin/python" -m py_compile "$APP/snck_panel.py" "$APP/kvm.py" "$APP/kvm_discord_bridge.py" "$APP/bot.py" "$APP/launcher.py"
  env_setup
  svc
}

install(){
  echo 'Installing Snck Panel + Bot + KVM...'
  prepare || { echo 'INSTALL FAILED'; return 1; }
  systemctl restart "$PS"
  sleep 2
  [ "$(st "$PS")" = ONLINE ] || { journalctl -u "$PS" -n 80 --no-pager; return 1; }
  if grep -q '^DISCORD_TOKEN=' "$APP/.env" 2>/dev/null; then systemctl restart "$BS" || true; fi
  echo 'INSTALL COMPLETE'
}

update(){
  echo 'Updating Snck Panel + Bot...'
  prepare || { echo 'UPDATE FAILED'; return 1; }
  systemctl restart "$PS"
  if grep -q '^DISCORD_TOKEN=' "$APP/.env" 2>/dev/null; then systemctl restart "$BS" || true; fi
  echo "UPDATE COMPLETE - $V"
}

check(){
  root
  echo "Panel: $(st "$PS")"
  echo "Bot: $(st "$BS")"
  echo "KVM: $([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"
  echo "Tools: $(command -v virsh >/dev/null && command -v virt-install >/dev/null && command -v cloud-localds >/dev/null && command -v qemu-img >/dev/null && echo READY || echo MISSING)"
  command -v virsh >/dev/null 2>&1 && virsh list --all || true
  printf 'Press Enter... '; read -r _ <&3 || true
}

restart(){ root; systemctl restart "$PS" 2>/dev/null || true; systemctl restart "$BS" 2>/dev/null || true; echo 'Services restarted.'; }

uninstall(){
  root
  systemctl stop "$PS" "$BS" 2>/dev/null || true
  systemctl disable "$PS" "$BS" 2>/dev/null || true
  rm -f "/etc/systemd/system/$PS.service" "/etc/systemd/system/$BS.service"
  systemctl daemon-reload
  rm -rf "$APP"
  echo 'SNCK PANEL + BOT UNINSTALLED SUCCESSFULLY'
}

while :; do
  clear 2>/dev/null || true
  printf '\n%bSNCK DISCORD VPS DEPLOY BOT + KVM PANEL%b\nPanel: %s | Bot: %s | KVM: %s\n\n[1] Install / Repair\n[2] Update Panel + Bot\n[3] Check VPS / KVM Status\n[4] Restart Panel and Bot\n[5] Uninstall Snck Panel + Bot\n[0] Exit\n\nSelect an option [0-5]: ' "$P" "$R" "$(st "$PS")" "$(st "$BS")" "$([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"
  read -r n <&3 || n=''
  case "$n" in
    1) install;;
    2) update;;
    3) check;;
    4) restart;;
    5) uninstall; exec 3>&-; exit 0;;
    0) exec 3>&-; exit 0;;
    *) echo 'Invalid option.'; sleep 1;;
  esac
done
