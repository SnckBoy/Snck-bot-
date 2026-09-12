#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Snck Discord VPS Deploy Bot + KVM"
SERVICE_NAME="snck-discord-bot"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
INSTALLER_VERSION="3.0.0"
APP_DIR="${SNCK_APP_DIR:-/opt/snck-bot}"
ENV_FILE="$APP_DIR/.env"

ESC=$'\033'; RESET="${ESC}[0m"; BOLD="${ESC}[1m"; DIM="${ESC}[2m"
CYAN="${ESC}[38;5;51m"; BLUE="${ESC}[38;5;39m"; PURPLE="${ESC}[38;5;141m"
MAGENTA="${ESC}[38;5;201m"; GREEN="${ESC}[38;5;82m"; YELLOW="${ESC}[38;5;220m"
RED="${ESC}[38;5;196m"; WHITE="${ESC}[38;5;255m"; GRAY="${ESC}[38;5;245m"

# Important for: curl -fsSL URL | bash
# FD 3 reads from the real terminal, so the menu never consumes the piped script.
if [[ -r /dev/tty ]]; then
  exec 3<>/dev/tty
else
  printf '%b\n' "${RED}ERROR${RESET}: interactive terminal not available." >&2
  exit 1
fi

say(){ printf '%b\n' "$*"; }
info(){ say "${CYAN}[INFO]${RESET} $*"; }
ok(){ say "${GREEN}[ OK ]${RESET} $*"; }
warn(){ say "${YELLOW}[WARN]${RESET} $*"; }
die(){ say "${RED}[FAIL]${RESET} $*" >&2; exit 1; }

run_root(){
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

require_root(){
  if [[ "$(id -u)" -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || die "Run as root or install sudo."
  fi
}

installed(){ [[ -d "$APP_DIR" && -f "$ENV_FILE" ]]; }
files_ready(){ [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/bot.py" && -f "$APP_DIR/launcher.py" ]]; }
service_state(){
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    printf 'ONLINE'
  elif command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    printf 'OFFLINE'
  else
    printf 'NOT INSTALLED'
  fi
}

kvm_state(){
  if [[ -e /dev/kvm ]]; then printf 'ENABLED'; else printf 'UNAVAILABLE'; fi
}

live_status(){
  local i f s k
  if installed; then i="INSTALLED"; else i="NOT INSTALLED"; fi
  if files_ready; then f="READY"; else f="NOT READY"; fi
  s="$(service_state)"; k="$(kvm_state)"

  printf '%b  LIVE STATUS  %bInstaller v%s%b\n' "$BOLD$CYAN" "$DIM" "$INSTALLER_VERSION" "$RESET"
  printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"
  [[ "$i" == INSTALLED ]] && printf '%b  │  INSTALLATION   : %-30s │%b\n' "$GREEN" "$i" "$RESET" || printf '%b  │  INSTALLATION   : %-30s │%b\n' "$YELLOW" "$i" "$RESET"
  [[ "$f" == READY ]] && printf '%b  │  BOT FILES      : %-30s │%b\n' "$GREEN" "$f" "$RESET" || printf '%b  │  BOT FILES      : %-30s │%b\n' "$YELLOW" "$f" "$RESET"
  case "$s" in ONLINE) printf '%b  │  SERVICE        : %-30s │%b\n' "$GREEN" "$s" "$RESET";; OFFLINE) printf '%b  │  SERVICE        : %-30s │%b\n' "$YELLOW" "$s" "$RESET";; *) printf '%b  │  SERVICE        : %-30s │%b\n' "$GRAY" "$s" "$RESET";; esac
  [[ "$k" == ENABLED ]] && printf '%b  │  KVM             : %-30s │%b\n' "$GREEN" "$k" "$RESET" || printf '%b  │  KVM             : %-30s │%b\n' "$YELLOW" "$k" "$RESET"
  printf '%b  ╰──────────────────────────────────────────────────╯%b\n' "$BLUE" "$RESET"
}

banner(){
  printf '\n'
  printf '%b╭──────────────────────────────────────────────────────╮%b\n' "$PURPLE" "$RESET"
  printf '%b│%b  %bSNCK DISCORD VPS DEPLOY BOT + KVM%b               %b│%b\n' "$PURPLE" "$RESET" "$BOLD$WHITE" "$RESET" "$PURPLE" "$RESET"
  printf '%b│%b  %bPremium VPS deployment and KVM management%b        %b│%b\n' "$PURPLE" "$RESET" "$DIM$CYAN" "$RESET" "$PURPLE" "$RESET"
  printf '%b├──────────────────────────────────────────────────────┤%b\n' "$BLUE" "$RESET"
  printf '%b│%b  %bPRODUCTION INSTALLER%b   %bUbuntu / Debian%b          %b│%b\n' "$BLUE" "$RESET" "$BOLD$MAGENTA" "$RESET" "$GRAY" "$RESET" "$BLUE" "$RESET"
  printf '%b╰──────────────────────────────────────────────────────╯%b\n' "$PURPLE" "$RESET"
}

install_kvm(){
  require_root
  info "Installing KVM/QEMU and virtualization tools..."
  run_root apt-get update -y
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients bridge-utils cpu-checker
  if [[ -e /dev/kvm ]]; then ok "KVM hardware acceleration is ENABLED."; else warn "KVM packages installed, but /dev/kvm is unavailable on this host."; fi
}

install_bot(){
  require_root
  info "Installing required system packages..."
  run_root apt-get update -y
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl ca-certificates
  ok "System dependencies installed."

  mkdir -p "$APP_DIR"
  info "Downloading Snck bot files..."
  for f in bot.py launcher.py requirements.txt start.sh; do
    curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || die "Failed to download $f"
  done
  chmod +x "$APP_DIR/start.sh"
  ok "Bot files downloaded."

  info "Creating Python virtual environment..."
  [[ -d "$APP_DIR/venv" ]] || python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/python" -m pip install --upgrade pip >/dev/null
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
  ok "Python dependencies installed."

  printf '\n%b  DISCORD BOT SETUP%b\n' "$BOLD$MAGENTA" "$RESET"
  printf '%b  Discord Bot Token: %b' "$WHITE" "$RESET"
  IFS= read -r DISCORD_TOKEN <&3 || true
  [[ -n "${DISCORD_TOKEN:-}" ]] || die "Discord bot token cannot be empty."

  printf 'DISCORD_TOKEN=%s\n' "$DISCORD_TOKEN" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
    info "Creating systemd service..."
    run_root tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null <<EOF
[Unit]
Description=Snck Discord VPS Deploy Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/launcher.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    run_root systemctl daemon-reload
    run_root systemctl enable --now "$SERVICE_NAME"
    sleep 3
    systemctl is-active --quiet "$SERVICE_NAME" || {
      warn "Bot service failed to start. Last log entries:"
      run_root journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
      die "Installation completed but the bot is not online."
    }
    ok "Snck Discord VPS Deploy Bot is ONLINE."
  else
    warn "systemd is unavailable; use start.sh to run the bot."
  fi

  printf '\n%bINSTALL COMPLETE%b\n' "$BOLD$GREEN" "$RESET"
  ok "Bot installed at $APP_DIR"
  menu
}

update_bot(){
  require_root
  if ! installed; then warn "Bot is not installed at $APP_DIR."; sleep 2; return; fi
  info "Updating Snck bot files..."
  for f in bot.py launcher.py requirements.txt start.sh; do
    curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || die "Failed to update $f"
  done
  chmod +x "$APP_DIR/start.sh"
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
  run_root systemctl restart "$SERVICE_NAME" 2>/dev/null || true
  ok "Bot updated."
}

uninstall_bot(){
  require_root
  if ! installed; then warn "Nothing is installed at $APP_DIR."; sleep 2; return; fi
  printf '%b  Remove Snck Bot and its local data? [y/N]: %b' "$WHITE" "$RESET"
  IFS= read -r c <&3 || true
  if [[ "$c" =~ ^[Yy]$ ]]; then
    run_root systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    run_root rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    run_root systemctl daemon-reload 2>/dev/null || true
    run_root rm -rf "$APP_DIR"
    ok "Bot removed."
  else
    info "Uninstall cancelled."
  fi
}

status_page(){
  banner
  live_status
  printf '\n%b  SYSTEM%b\n' "$BOLD$CYAN" "$RESET"
  printf '  Install path : %s\n' "$APP_DIR"
  printf '  Service      : %s\n' "$SERVICE_NAME"
  printf '  KVM device   : %s\n' "$(kvm_state)"
  if command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    printf '  Autostart    : ENABLED\n'
  else
    printf '  Autostart    : NOT ENABLED\n'
  fi
  printf '\n%b  Press Enter to return to menu...%b' "$DIM" "$RESET"
  IFS= read -r _ <&3 || true
}

menu(){
  while true; do
    banner
    live_status
    printf '\n%b  MAIN MENU%b\n' "$BOLD$CYAN" "$RESET"
    printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"
    printf '%b  │%b  %b[1]%b  Install Snck Bot + KVM Support             %b│%b\n' "$BLUE" "$GREEN" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[2]%b  Update Snck Bot                             %b│%b\n' "$BLUE" "$CYAN" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[3]%b  Uninstall Snck Bot                          %b│%b\n' "$BLUE" "$RED" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[4]%b  Install / Check KVM                        %b│%b\n' "$BLUE" "$PURPLE" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[5]%b  Live System Status                          %b│%b\n' "$BLUE" "$YELLOW" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[0]%b  Exit                                         %b│%b\n' "$BLUE" "$MAGENTA" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  ╰──────────────────────────────────────────────────╯%b\n' "$BLUE" "$RESET"
    printf '\n%b  Select an option [0-5]: %b' "$BOLD$WHITE" "$RESET"
    IFS= read -r choice <&3 || true
    printf '\n'
    case "${choice:-}" in
      1) install_kvm; install_bot ;;
      2) update_bot ;;
      3) uninstall_bot ;;
      4) install_kvm ;;
      5) status_page ;;
      0) say "${DIM}Exiting.${RESET}"; exit 0 ;;
      *) warn "Invalid option. Choose 0, 1, 2, 3, 4, or 5."; sleep 1 ;;
    esac
  done
}

menu
