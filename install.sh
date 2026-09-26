#!/usr/bin/env bash
set -Eeuo pipefail

REPO="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
APP="${SNCK_APP_DIR:-/opt/snck-bot}"
PS="snck-kvm-panel"
BS="snck-discord-bot"
V="10.0.0"
PANEL_PID="$APP/panel.pid"
BOT_PID="$APP/bot.pid"
PANEL_LOG="$APP/panel.log"
BOT_LOG="$APP/bot.log"

log(){ printf '[INFO] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*" >&2; }
die(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }

root(){
  if [ "$(id -u)" -ne 0 ]; then
    exec sudo -E bash "$0" "$@"
  fi
}

has_systemd(){
  [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1
}

stop_pidfile(){
  local file="$1" pid=""
  if [ -f "$file" ]; then
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.25
      done
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

start_standalone_panel(){
  mkdir -p "$APP"
  stop_pidfile "$PANEL_PID"
  : > "$PANEL_LOG"
  export SNCK_PANEL_HOST="${SNCK_PANEL_HOST:-0.0.0.0}"
  export SNCK_PANEL_PORT="${SNCK_PANEL_PORT:-5000}"
  export SNCK_CODESPACE="${SNCK_CODESPACE:-0}"
  nohup "$APP/venv/bin/python" "$APP/snck_panel.py" >>"$PANEL_LOG" 2>&1 &
  echo $! > "$PANEL_PID"
  chmod 600 "$PANEL_PID" "$PANEL_LOG"
}

start_standalone_bot(){
  [ -n "${DISCORD_TOKEN:-}" ] || return 0
  mkdir -p "$APP"
  stop_pidfile "$BOT_PID"
  : > "$BOT_LOG"
  nohup "$APP/venv/bin/python" "$APP/launcher.py" >>"$BOT_LOG" 2>&1 &
  echo $! > "$BOT_PID"
  chmod 600 "$BOT_PID" "$BOT_LOG"
}

stop_runtime(){
  if has_systemd; then
    systemctl stop "$PS" "$BS" 2>/dev/null || true
  fi
  stop_pidfile "$PANEL_PID"
  stop_pidfile "$BOT_PID"
}

get(){
  mkdir -p "$APP"
  for f in snck_panel.py kvm.py kvm_discord_bridge.py bot.py launcher.py panel_bridge.py snck_panel_bridge.py requirements.txt; do
    log "Downloading $f"
    curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 "$REPO/$f" -o "$APP/$f"
  done
}

setup_env(){
  local secret old="" token="" client="" guild="" public=""
  secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  if [ -f "$APP/.env" ]; then
    old="$(grep '^SNCK_PANEL_SECRET=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    token="$(grep '^DISCORD_TOKEN=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    client="$(grep '^DISCORD_CLIENT_ID=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    guild="$(grep '^DISCORD_GUILD_ID=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    public="$(grep '^DISCORD_PUBLIC_KEY=' "$APP/.env" | head -1 | cut -d= -f2- || true)"
    [ -n "$old" ] && secret="$old"
  fi
  cat > "$APP/.env" <<EOF
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
  [ -n "$token" ] && printf 'DISCORD_TOKEN=%s\n' "$token" >> "$APP/.env"
  [ -n "$client" ] && printf 'DISCORD_CLIENT_ID=%s\n' "$client" >> "$APP/.env"
  [ -n "$guild" ] && printf 'DISCORD_GUILD_ID=%s\n' "$guild" >> "$APP/.env"
  [ -n "$public" ] && printf 'DISCORD_PUBLIC_KEY=%s\n' "$public" >> "$APP/.env"
  chmod 600 "$APP/.env"
}

setup_services(){
  if ! has_systemd; then
    return 0
  fi
  cat > "/etc/systemd/system/$PS.service" <<EOF
[Unit]
Description=Snck KVM Panel
After=network-online.target
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
  cat > "/etc/systemd/system/$BS.service" <<EOF
[Unit]
Description=Snck Discord VPS Deploy Bot
After=network-online.target
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

setup_libvirt(){
  if ! has_systemd; then
    warn "systemd is unavailable; skipping libvirt service management. KVM is optional in this environment."
    return 0
  fi
  systemctl enable --now libvirtd >/dev/null 2>&1 || systemctl enable --now libvirt >/dev/null 2>&1 || warn "libvirt service could not be started."
}

setup_network(){
  command -v virsh >/dev/null 2>&1 || return 0
  virsh net-list --all --name 2>/dev/null | grep -qx default || {
    [ -f /usr/share/libvirt/networks/default.xml ] || return 0
    virsh net-define /usr/share/libvirt/networks/default.xml >/dev/null 2>&1 || return 0
  }
  virsh net-autostart default >/dev/null 2>&1 || true
  virsh net-info default 2>/dev/null | grep -qi 'Active:.*yes' || virsh net-start default >/dev/null 2>&1 || true
}

prepare(){
  root "$@"
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a APT_LISTCHANGES_FRONTEND=none
  apt-get update -y
  apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils openssh-client
  setup_libvirt
  get
  if [ ! -x "$APP/venv/bin/python" ]; then python3 -m venv "$APP/venv"; fi
  "$APP/venv/bin/python" -m pip install --upgrade pip
  "$APP/venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements.txt"
  setup_network || true
  "$APP/venv/bin/python" -m py_compile "$APP/snck_panel.py" "$APP/kvm.py" "$APP/bot.py" "$APP/launcher.py"
  setup_env
  setup_services
}

start_panel(){
  if has_systemd; then
    systemctl restart "$PS"
  else
    start_standalone_panel
  fi
}

start_bot(){
  [ -n "${DISCORD_TOKEN:-}" ] || return 0
  if has_systemd; then
    systemctl restart "$BS" || true
  else
    start_standalone_bot
  fi
}

health(){
  local port="${SNCK_PANEL_PORT:-5000}"
  curl -fsS --max-time 3 "http://127.0.0.1:$port/health"
}

wait_panel(){
  local port="${SNCK_PANEL_PORT:-5000}"
  for _ in $(seq 1 30); do
    if health >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

install_all(){
  root "$@"
  echo 'Installing Snck Panel + Discord Bot + KVM...'
  prepare
  start_panel
  if ! wait_panel; then
    echo 'Panel failed its health check.' >&2
    if [ -f "$PANEL_LOG" ]; then cat "$PANEL_LOG" >&2; fi
    if has_systemd; then journalctl -u "$PS" -n 100 --no-pager >&2 || true; fi
    return 1
  fi
  start_bot
  echo
  echo 'INSTALL COMPLETE'
  echo 'Panel: http://SERVER-IP:5000'
  echo 'Health: http://SERVER-IP:5000/health'
  health || true
}

update_all(){
  install_all "$@"
}

check(){
  root "$@"
  echo "systemd: $(has_systemd && echo AVAILABLE || echo UNAVAILABLE)"
  echo "KVM: $([ -e /dev/kvm ] && echo ENABLED || echo UNAVAILABLE)"
  echo "Panel PID: $([ -f "$PANEL_PID" ] && cat "$PANEL_PID" || echo none)"
  echo "Panel health:"
  health || true
  if command -v virsh >/dev/null 2>&1; then virsh list --all 2>/dev/null || true; fi
}

restart(){
  root "$@"
  start_panel
  start_bot
  wait_panel || die "Panel did not become healthy. See $PANEL_LOG"
  echo 'Services restarted.'
}

uninstall(){
  root "$@"
  stop_runtime
  if has_systemd; then
    systemctl disable "$PS" "$BS" 2>/dev/null || true
    rm -f "/etc/systemd/system/$PS.service" "/etc/systemd/system/$BS.service"
    systemctl daemon-reload || true
  fi
  rm -rf "$APP"
  echo 'Snck Panel + Bot removed.'
}

case "${1:-}" in
  --install|install) install_all; exit $?;;
  --update|update) update_all; exit $?;;
  --check|check) check; exit $?;;
  --restart|restart) restart; exit $?;;
  --uninstall|uninstall) uninstall; exit $?;;
esac

if [ -r /dev/tty ]; then exec 3<>/dev/tty; else exec 3<>/dev/null; fi
while :; do
  clear 2>/dev/null || true
  printf '\nSNCK KVM PANEL + DISCORD BOT\n\n[1] Install / Repair\n[2] Update\n[3] Check Status\n[4] Restart\n[5] Uninstall\n[0] Exit\n\nSelect [0-5]: '
  read -r n <&3 || n=0
  case "$n" in
    1) install_all;;
    2) update_all;;
    3) check; read -r _ <&3 || true;;
    4) restart;;
    5) uninstall; exit 0;;
    0) exit 0;;
    *) echo 'Invalid option.'; sleep 1;;
  esac
done
