#!/usr/bin/env bash
set -Eeuo pipefail
REPO="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
APP="${SNCK_APP_DIR:-/opt/snck-bot}"
PS=snck-kvm-panel
BS=snck-discord-bot
V=9.1.0

root(){
  if [ "$(id -u)" != 0 ]; then exec sudo -E bash "$0" "$@"; fi
}

has_systemd(){
  command -v systemctl >/dev/null 2>&1 && [ "$(ps -p 1 -o comm= 2>/dev/null || true)" = "systemd" ] && systemctl is-system-running >/dev/null 2>&1 || {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
  }
}

st(){
  if has_systemd; then
    systemctl is-active --quiet "$1" 2>/dev/null && echo ONLINE || systemctl is-enabled --quiet "$1" 2>/dev/null && echo OFFLINE || echo NOT-INSTALLED
  else
    case "$1" in
      "$PS") [ -f "$APP/panel.pid" ] && kill -0 "$(cat "$APP/panel.pid")" 2>/dev/null && echo ONLINE || echo OFFLINE ;;
      "$BS") [ -f "$APP/bot.pid" ] && kill -0 "$(cat "$APP/bot.pid")" 2>/dev/null && echo ONLINE || echo OFFLINE ;;
      *) echo NOT-INSTALLED ;;
    esac
  fi
}

get(){
  mkdir -p "$APP"
  for f in snck_panel.py kvm.py kvm_discord_bridge.py bot.py launcher.py panel_bridge.py snck_panel_bridge.py requirements.txt; do
    printf '[INFO] Downloading %s\n' "$f"
    curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 "$REPO/$f" -o "$APP/$f"
  done
}

network(){
  command -v virsh >/dev/null 2>&1 || return 1
  virsh net-list --all --name 2>/dev/null | grep -qx default || {
    [ -f /usr/share/libvirt/networks/default.xml ] || return 1
    virsh net-define /usr/share/libvirt/networks/default.xml >/dev/null 2>&1 || return 1
  }
  virsh net-autostart default >/dev/null 2>&1 || true
  virsh net-info default 2>/dev/null | grep -qi 'Active:.*yes' || virsh net-start default >/dev/null 2>&1 || true
  virsh net-info default 2>/dev/null | grep -qi 'Active:.*yes'
}

env(){
  local token='' client='' guild='' public='' secret old
  secret=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
  if [ -f "$APP/.env" ]; then
    token=$(grep '^DISCORD_TOKEN=' "$APP/.env" | head -1 | cut -d= -f2- || true)
    client=$(grep '^DISCORD_CLIENT_ID=' "$APP/.env" | head -1 | cut -d= -f2- || true)
    guild=$(grep '^DISCORD_GUILD_ID=' "$APP/.env" | head -1 | cut -d= -f2- || true)
    public=$(grep '^DISCORD_PUBLIC_KEY=' "$APP/.env" | head -1 | cut -d= -f2- || true)
    old=$(grep '^SNCK_PANEL_SECRET=' "$APP/.env" | head -1 | cut -d= -f2- || true)
    [ -n "$old" ] && secret="$old"
  fi
  cat >"$APP/.env" <<EOF
SNCK_PANEL_HOST=0.0.0.0
SNCK_PANEL_PORT=5000
SNCK_PANEL_SECRET=$secret
SNCK_CODESPACE=${SNCK_CODESPACE:-0}
BOT_NAME=Snck Discord VPS Deploy Bot
BOT_DEVELOPER=Clark
BOT_ICON_URL=https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/assets/snck-logo.svg
BOT_THUMBNAIL_URL=https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/assets/snck-logo.svg
PREFIX=!
EOF
  [ -n "$token" ] && printf 'DISCORD_TOKEN=%s\n' "$token" >>"$APP/.env"
  [ -n "$client" ] && printf 'DISCORD_CLIENT_ID=%s\n' "$client" >>"$APP/.env"
  [ -n "$guild" ] && printf 'DISCORD_GUILD_ID=%s\n' "$guild" >>"$APP/.env"
  [ -n "$public" ] && printf 'DISCORD_PUBLIC_KEY=%s\n' "$public" >>"$APP/.env"
  chmod 600 "$APP/.env"
}

svc_systemd(){
  cat >"/etc/systemd/system/$PS.service" <<EOF
[Unit]
Description=Snck KVM Panel
After=network-online.target libvirtd.service
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python $APP/snck_panel.py
Restart=always
RestartSec=3
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
EOF
  cat >"/etc/systemd/system/$BS.service" <<EOF
[Unit]
Description=Snck Discord VPS Deploy Bot
After=network-online.target libvirtd.service
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python $APP/launcher.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$PS" "$BS" >/dev/null 2>&1 || true
}

stop_fallback(){
  local pidfile="$1"
  if [ -f "$pidfile" ]; then
    local pid
    pid=$(cat "$pidfile" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
    for _ in $(seq 1 10); do
      [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null && break
      sleep 0.2
    done
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" 2>/dev/null || true; fi
    rm -f "$pidfile"
  fi
}

start_fallback(){
  local name="$1" cmd="$2" pidfile="$APP/$3" logfile="$APP/$4"
  stop_fallback "$pidfile"
  nohup bash -c "cd '$APP' && exec '$APP/venv/bin/python' '$APP/$cmd'" >>"$logfile" 2>&1 < /dev/null &
  echo $! >"$pidfile"
  chmod 600 "$pidfile" "$logfile"
}

start_services(){
  if has_systemd; then
    systemctl daemon-reload
    systemctl restart "$PS"
  else
    start_fallback "$PS" snck_panel.py panel.pid panel.log
  fi
}

start_bot(){
  if has_systemd; then
    systemctl restart "$BS" || true
  elif grep -q '^DISCORD_TOKEN=' "$APP/.env" 2>/dev/null; then
    start_fallback "$BS" launcher.py bot.pid bot.log
  fi
}

stop_services(){
  if has_systemd; then
    systemctl stop "$PS" "$BS" 2>/dev/null || true
  else
    stop_fallback "$APP/panel.pid"
    stop_fallback "$APP/bot.pid"
  fi
}

prepare(){
  root
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a APT_LISTCHANGES_FRONTEND=none
  apt-get update -y
  apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils openssh-client
  if has_systemd; then
    systemctl enable --now libvirtd >/dev/null 2>&1 || systemctl enable --now libvirt >/dev/null 2>&1 || true
  else
    echo '[INFO] systemd is unavailable; using standalone process mode for the panel.'
  fi
  get
  if [ ! -x "$APP/venv/bin/python" ]; then python3 -m venv "$APP/venv"; fi
  "$APP/venv/bin/python" -m pip install --upgrade pip
  "$APP/venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements.txt"
  network || echo '[INFO] libvirt default network unavailable; real KVM will remain unavailable until the host provides libvirt/KVM.'
  "$APP/venv/bin/python" -m py_compile "$APP/snck_panel.py" "$APP/kvm.py" "$APP/bot.py" "$APP/launcher.py"
  env
  if has_systemd; then svc_systemd; fi
}

install_all(){
  echo 'Installing Snck Panel + Discord Bot + KVM...'
  prepare
  start_services
  local healthy=0
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 http://127.0.0.1:5000/health >/dev/null 2>&1; then healthy=1; break; fi
    sleep 1
  done
  if [ "$healthy" != 1 ]; then
    echo '[ERROR] Panel failed its health check.'
    if has_systemd; then journalctl -u "$PS" -n 100 --no-pager || true; else tail -n 100 "$APP/panel.log" 2>/dev/null || true; fi
    return 1
  fi
  start_bot
  echo
  echo 'INSTALL COMPLETE'
  echo 'Panel: http://SERVER-IP:5000'
  echo 'Health: http://SERVER-IP:5000/health'
  echo "Runtime: $(has_systemd && echo systemd || echo standalone)"
}

update_all(){ install_all; echo "UPDATE COMPLETE - $V"; }

check(){
  root
  echo "Panel: $(st "$PS")"
  echo "Bot: $(st "$BS")"
  echo "KVM: $([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"
  echo "Tools: $(command -v virsh >/dev/null && command -v virt-install >/dev/null && command -v cloud-localds >/dev/null && command -v qemu-img >/dev/null && echo READY || echo MISSING)"
  curl -fsS --max-time 3 http://127.0.0.1:5000/health 2>/dev/null || true
  command -v virsh >/dev/null 2>&1 && virsh list --all || true
}

restart(){ root; start_services; start_bot; echo 'Services restarted.'; }
uninstall(){
  root
  stop_services
  if has_systemd; then
    systemctl disable "$PS" "$BS" 2>/dev/null || true
    rm -f "/etc/systemd/system/$PS.service" "/etc/systemd/system/$BS.service"
    systemctl daemon-reload
  fi
  rm -rf "$APP"
  echo 'Snck Panel + Bot removed.'
}

if [ "${1:-}" = "--install" ] || [ "${1:-}" = "install" ]; then install_all; exit $?; fi
if [ "${1:-}" = "--update" ] || [ "${1:-}" = "update" ]; then update_all; exit $?; fi

if [ -r /dev/tty ]; then exec 3<>/dev/tty; else exec 3<>/dev/null; fi
while :; do
  clear 2>/dev/null || true
  printf '\nSNCK KVM PANEL + DISCORD BOT\nPanel: %s | Bot: %s | KVM: %s\n\n[1] Install / Repair\n[2] Update\n[3] Check Status\n[4] Restart\n[5] Uninstall\n[0] Exit\n\nSelect [0-5]: ' "$(st "$PS")" "$(st "$BS")" "$([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"
  read -r n <&3 || n=0
  case "$n" in
    1) install_all;; 2) update_all;; 3) check; read -r _ <&3 || true;; 4) restart;; 5) uninstall; exit 0;; 0) exit 0;; *) echo 'Invalid option.'; sleep 1;;
  esac
done
