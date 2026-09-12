#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="SNCK DISCORD VPS DEPLOY BOT + KVM"
SERVICE_NAME="snck-discord-bot"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
INSTALLER_VERSION="3.1.0"
APP_DIR="${SNCK_APP_DIR:-/opt/snck-bot}"
ENV_FILE="$APP_DIR/.env"

ESC=$'\033'; RESET="${ESC}[0m"; BOLD="${ESC}[1m"; DIM="${ESC}[2m"
CYAN="${ESC}[38;5;51m"; BLUE="${ESC}[38;5;39m"; PURPLE="${ESC}[38;5;141m"
MAGENTA="${ESC}[38;5;201m"; GREEN="${ESC}[38;5;82m"; YELLOW="${ESC}[38;5;220m"
RED="${ESC}[38;5;196m"; WHITE="${ESC}[38;5;255m"; GRAY="${ESC}[38;5;245m"

# Required for curl | bash: menu input comes from the real terminal.
if [[ -r /dev/tty ]]; then exec 3<>/dev/tty; else printf '%b\n' "${RED}ERROR${RESET}: interactive terminal not available." >&2; exit 1; fi
say(){ printf '%b\n' "$*"; }
info(){ say "${CYAN}[INFO]${RESET} $*"; }
ok(){ say "${GREEN}[ OK ]${RESET} $*"; }
warn(){ say "${YELLOW}[WARN]${RESET} $*"; }
die(){ say "${RED}[FAIL]${RESET} $*" >&2; exit 1; }
run_root(){ if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi; }
require_root(){ [[ "$(id -u)" -eq 0 ]] || { command -v sudo >/dev/null 2>&1 || die "Run as root or install sudo."; }; }
installed(){ [[ -d "$APP_DIR" && -f "$ENV_FILE" ]]; }
files_ready(){ [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/bot.py" && -f "$APP_DIR/launcher.py" ]]; }
service_state(){ if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then printf 'ONLINE'; elif command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then printf 'OFFLINE'; else printf 'NOT INSTALLED'; fi; }
kvm_state(){ [[ -e /dev/kvm ]] && printf 'ENABLED' || printf 'UNAVAILABLE'; }

live_status(){
  local i f s k; installed && i="INSTALLED" || i="NOT INSTALLED"; files_ready && f="READY" || f="NOT READY"; s="$(service_state)"; k="$(kvm_state)"
  printf '%b  LIVE STATUS  %bInstaller v%s%b\n' "$BOLD$CYAN" "$DIM" "$INSTALLER_VERSION" "$RESET"
  printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"
  printf '%b  │  INSTALLATION   : %-30s │%b\n' "$([[ "$i" == INSTALLED ]] && echo "$GREEN" || echo "$YELLOW")" "$i" "$RESET"
  printf '%b  │  BOT FILES      : %-30s │%b\n' "$([[ "$f" == READY ]] && echo "$GREEN" || echo "$YELLOW")" "$f" "$RESET"
  printf '%b  │  SERVICE        : %-30s │%b\n' "$([[ "$s" == ONLINE ]] && echo "$GREEN" || echo "$YELLOW")" "$s" "$RESET"
  printf '%b  │  KVM             : %-30s │%b\n' "$([[ "$k" == ENABLED ]] && echo "$GREEN" || echo "$YELLOW")" "$k" "$RESET"
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
  [[ -e /dev/kvm ]] && ok "KVM hardware acceleration is ENABLED." || warn "KVM packages installed, but /dev/kvm is unavailable on this host."
}

install_bot(){
  require_root
  info "Installing required system packages..."
  run_root apt-get update -y
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl ca-certificates
  ok "System dependencies installed."
  mkdir -p "$APP_DIR"
  info "Downloading Snck bot files..."
  for f in bot.py launcher.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || die "Failed to download $f"; done
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
    systemctl is-active --quiet "$SERVICE_NAME" || { warn "Bot service failed to start."; run_root journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true; die "Installation completed but the bot is not online."; }
    ok "Snck Discord VPS Deploy Bot is ONLINE."
  else
    warn "systemd is unavailable; use start.sh to run the bot."
  fi
  printf '\n%bINSTALL COMPLETE%b\n' "$BOLD$GREEN" "$RESET"
  ok "Bot installed at $APP_DIR"
}

update_bot(){
  require_root
  installed || { warn "Bot is not installed at $APP_DIR."; return; }
  info "Updating Snck bot files..."
  for f in bot.py launcher.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || die "Failed to update $f"; done
  chmod +x "$APP_DIR/start.sh"
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
  run_root systemctl restart "$SERVICE_NAME" 2>/dev/null || true
  ok "Bot updated."
}

uninstall_bot(){
  require_root
  installed || { warn "Nothing is installed at $APP_DIR."; return; }
  printf '%b  Remove Snck Bot and its local data? [y/N]: %b' "$WHITE" "$RESET"
  IFS= read -r c <&3 || true
  [[ "$c" =~ ^[Yy]$ ]] || { info "Uninstall cancelled."; return; }
  run_root systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  run_root rm -f "/etc/systemd/system/$SERVICE_NAME.service"
  run_root systemctl daemon-reload 2>/dev/null || true
  run_root rm -rf "$APP_DIR"
  ok "Bot removed."
}

status_page(){
  banner; live_status
  printf '\n%b  SYSTEM%b\n' "$BOLD$CYAN" "$RESET"
  printf '  Install path : %s\n' "$APP_DIR"
  printf '  Service      : %s\n' "$SERVICE_NAME"
  printf '  KVM device   : %s\n' "$(kvm_state)"
  printf '\n%b  Press Enter to return to menu...%b' "$DIM" "$RESET"
  IFS= read -r _ <&3 || true
}

menu(){
  while true; do
    banner; live_status
    printf '\n%b  MAIN MENU%b\n' "$BOLD$CYAN" "$RESET"
    printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"
    printf '%b  │%b  %b[1]%b  Install Snck Bot + KVM Support             %b│%b\n' "$BLUE" "$GREEN" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[2]%b  Deploy New KVM VPS                          %b│%b\n' "$BLUE" "$CYAN" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[3]%b  Manage KVM Nodes                            %b│%b\n' "$BLUE" "$PURPLE" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[4]%b  Discord Bot Settings                         %b│%b\n' "$BLUE" "$MAGENTA" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[5]%b  Live System Status                           %b│%b\n' "$BLUE" "$YELLOW" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[6]%b  Update Snck Bot + Panel                      %b│%b\n' "$BLUE" "$CYAN" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[7]%b  Uninstall                                    %b│%b\n' "$BLUE" "$RED" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  │%b  %b[0]%b  Exit                                         %b│%b\n' "$BLUE" "$MAGENTA" "$WHITE" "$RESET" "$BLUE" "$RESET"
    printf '%b  ╰──────────────────────────────────────────────────╯%b\n' "$BLUE" "$RESET"
    printf '\n%b  Select an option [0-7]: %b' "$BOLD$WHITE" "$RESET"
    IFS= read -r choice <&3 || true
    printf '\n'
    case "${choice:-}" in
      1) install_kvm; install_bot; menu ;;
      2) warn "KVM VPS deployment requires the panel backend/API to be configured for real VM provisioning."; sleep 2 ;;
      3) warn "KVM node management requires the panel backend/API."; sleep 2 ;;
      4) warn "Discord bot settings are available after installation."; sleep 2 ;;
      5) status_page ;;
      6) update_bot; sleep 1 ;;
      7) uninstall_bot; sleep 1 ;;
      0) say "${DIM}Exiting.${RESET}"; exit 0 ;;
      *) warn "Invalid option. Choose 0-7."; sleep 1 ;;
    esac
  done
}

menu
