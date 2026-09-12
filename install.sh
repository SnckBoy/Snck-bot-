#!/usr/bin/env bash
set -Eeuo pipefail
APP_NAME="SNCK DISCORD VPS DEPLOY BOT"
SERVICE_NAME="snck-discord-bot"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
INSTALLER_VERSION="2.4.0"
ESC=$'\033'; RESET="${ESC}[0m"; BOLD="${ESC}[1m"; DIM="${ESC}[2m"
CYAN="${ESC}[38;5;51m"; BLUE="${ESC}[38;5;39m"; PURPLE="${ESC}[38;5;141m"; MAGENTA="${ESC}[38;5;201m"; GREEN="${ESC}[38;5;82m"; YELLOW="${ESC}[38;5;220m"; RED="${ESC}[38;5;196m"; WHITE="${ESC}[38;5;255m"; GRAY="${ESC}[38;5;245m"

# curl | bash: read menu input from the real terminal, not curl's stdin.
if [[ -r /dev/tty ]]; then exec 3<>/dev/tty; else printf '%b\n' "${RED}ERROR:${RESET} An interactive terminal is required." >&2; exit 1; fi
say(){ printf '%b\n' "$*"; }
line(){ printf '%b%s%b\n' "$BLUE" '────────────────────────────────────────────────────────' "$RESET"; }
info(){ say "${CYAN}[INFO]${RESET} $*"; }
ok(){ say "${GREEN}[OK]${RESET} $*"; }
warn(){ say "${YELLOW}[WARN]${RESET} $*"; }
die(){ say "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# Dynamic accent used by the menu header on every redraw.
ACCENTS=("$CYAN" "$BLUE" "$PURPLE" "$MAGENTA" "$GREEN")
accent_index=0
next_accent(){ accent_index=$(( (accent_index + 1) % ${#ACCENTS[@]} )); printf '%s' "${ACCENTS[$accent_index]}"; }

resolve_paths(){
  local user home_dir=''
  if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then user="$SUDO_USER"; else user="${USER:-root}"; fi
  if command -v getent >/dev/null 2>&1; then home_dir="$(timeout 3 getent passwd "$user" 2>/dev/null | cut -d: -f6 || true)"; fi
  home_dir="${home_dir:-${HOME:-/root}}"
  APP_DIR="$home_dir/snck-bot"
  ENV_FILE="$APP_DIR/.env"
}

status_value(){
  local kind="$1"; resolve_paths
  case "$kind" in
    install) [[ -d "$APP_DIR" && -f "$ENV_FILE" ]] && printf 'INSTALLED' || printf 'NOT INSTALLED' ;;
    files) [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/bot.py" && -f "$APP_DIR/launcher.py" ]] && printf 'READY' || printf 'NOT READY' ;;
    service)
      if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then printf 'ONLINE'
      elif command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then printf 'OFFLINE'
      else printf 'NOT INSTALLED'; fi ;;
  esac
}

live_status(){
  local install_state files_state service_state
  install_state="$(status_value install)"; files_state="$(status_value files)"; service_state="$(status_value service)"
  printf '%b  LIVE SYSTEM STATUS%b  %bInstaller v%s%b\n' "$BOLD$CYAN" "$RESET" "$DIM" "$INSTALLER_VERSION" "$RESET"
  printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"
  [[ "$install_state" == INSTALLED ]] && printf '%b  │  INSTALLATION   : INSTALLED                      │%b\n' "$GREEN" "$RESET" || printf '%b  │  INSTALLATION   : NOT INSTALLED                  │%b\n' "$YELLOW" "$RESET"
  [[ "$files_state" == READY ]] && printf '%b  │  BOT FILES      : READY                          │%b\n' "$GREEN" "$RESET" || printf '%b  │  BOT FILES      : NOT READY                      │%b\n' "$YELLOW" "$RESET"
  case "$service_state" in
    ONLINE) printf '%b  │  SERVICE        : ONLINE                         │%b\n' "$GREEN" "$RESET";;
    OFFLINE) printf '%b  │  SERVICE        : OFFLINE                        │%b\n' "$YELLOW" "$RESET";;
    *) printf '%b  │  SERVICE        : NOT INSTALLED                 │%b\n' "$GRAY" "$RESET";;
  esac
  printf '%b  ╰──────────────────────────────────────────────────╯%b\n' "$BLUE" "$RESET"
}

banner(){
  local a; a="$(next_accent)"
  printf '\n'
  printf '%b╭──────────────────────────────────────────────────────╮%b\n' "$a" "$RESET"
  printf '%b│  %bSNCK DISCORD VPS DEPLOY BOT%b                     %b│%b\n' "$a" "$BOLD$WHITE" "$RESET" "$a" "$RESET"
  printf '%b│  %bPremium VPS deployment and management             %b│%b\n' "$a" "$DIM$CYAN" "$RESET" "$a" "$RESET"
  printf '%b├──────────────────────────────────────────────────────┤%b\n' "$a" "$RESET"
  printf '%b│  %bPRODUCTION INSTALLER%b   %bUbuntu / Debian          %b│%b\n' "$a" "$BOLD$MAGENTA" "$RESET" "$GRAY" "$a" "$RESET"
  printf '%b╰──────────────────────────────────────────────────────╯%b\n' "$a" "$RESET"
}

menu(){
  while true; do
    banner; live_status
    printf '\n%b  MAIN MENU%b\n' "$BOLD$CYAN" "$RESET"
    printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"
    printf '%b  │  %b[1]%b  Install Snck Discord VPS Deploy Bot       %b│%b\n' "$BLUE" "$GREEN" "$WHITE" "$BLUE" "$RESET"
    printf '%b  │  %b[2]%b  Update Bot                                 %b│%b\n' "$BLUE" "$CYAN" "$WHITE" "$BLUE" "$RESET"
    printf '%b  │  %b[3]%b  Uninstall Bot                              %b│%b\n' "$BLUE" "$RED" "$WHITE" "$BLUE" "$RESET"
    printf '%b  │  %b[4]%b  Refresh Live Status                         %b│%b\n' "$BLUE" "$YELLOW" "$WHITE" "$BLUE" "$RESET"
    printf '%b  │  %b[0]%b  Exit                                        %b│%b\n' "$BLUE" "$MAGENTA" "$WHITE" "$BLUE" "$RESET"
    printf '%b  ╰──────────────────────────────────────────────────╯%b\n' "$BLUE" "$RESET"
    printf '\n%b  Select an option [1-4, 0]: %b' "$BOLD$WHITE" "$RESET"
    IFS= read -r choice <&3 || true; printf '\n'
    case "${choice:-}" in
      1) install_bot; return;;
      2) update_bot; return;;
      3) uninstall_bot; return;;
      4) continue;;
      0) say "${DIM}Exiting.${RESET}"; exit 0;;
      *) warn 'Invalid option. Please choose 1, 2, 3, 4, or 0.'; sleep 1;;
    esac
  done
}

require_root(){ [[ "$(id -u)" -eq 0 || "$(command -v sudo >/dev/null 2>&1; echo $?)" -eq 0 ]] || die 'Root or sudo is required.'; }
run_root(){ if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi; }

install_bot(){
  require_root; resolve_paths; line; say "${BOLD}${CYAN}INSTALLATION${RESET}"; line
  info 'Installing system dependencies...'; run_root apt-get update -y; run_root apt-get install -y python3 python3-venv python3-pip curl ca-certificates; ok 'Dependencies installed.'
  mkdir -p "$APP_DIR"; info 'Downloading Snck Bot...'; for f in bot.py launcher.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f"; done; chmod +x "$APP_DIR/start.sh"; ok 'Bot files downloaded.'
  [[ -d "$APP_DIR/venv" ]] || python3 -m venv "$APP_DIR/venv"; "$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"; ok 'Python packages installed.'
  printf '\n%b  DISCORD BOT SETUP%b\n' "$BOLD$MAGENTA" "$RESET"; printf '%b  Discord Bot Token: %b' "$WHITE" "$RESET"; IFS= read -r DISCORD_TOKEN <&3 || true; [[ -n "${DISCORD_TOKEN:-}" ]] || die 'Discord bot token cannot be empty.'
  printf 'DISCORD_TOKEN=%s\n' "$DISCORD_TOKEN" > "$ENV_FILE"; chmod 600 "$ENV_FILE"
  info 'Installing system service...'; run_root tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null <<EOF
[Unit]
Description=Snck Discord VPS Deploy Bot
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=${SUDO_USER:-${USER:-root}}
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/launcher.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  run_root systemctl daemon-reload; run_root systemctl enable --now "$SERVICE_NAME"; ok 'Snck Discord VPS Deploy Bot is installed and running.'; menu
}

update_bot(){ resolve_paths; [[ -d "$APP_DIR" ]] || { warn "Bot is not installed at $APP_DIR."; sleep 2; return; }; line; say "${BOLD}${CYAN}UPDATE${RESET}"; line; for f in bot.py launcher.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f"; done; chmod +x "$APP_DIR/start.sh"; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"; run_root systemctl restart "$SERVICE_NAME" || true; ok 'Bot updated successfully.'; menu; }
uninstall_bot(){ resolve_paths; line; say "${BOLD}${RED}UNINSTALL${RESET}"; line; printf '%b  Remove Snck Bot and local data? [y/N]: %b' "$WHITE" "$RESET"; IFS= read -r c <&3 || true; if [[ "$c" =~ ^[Yy]$ ]]; then run_root systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true; run_root rm -f "/etc/systemd/system/$SERVICE_NAME.service"; run_root systemctl daemon-reload; rm -rf "$APP_DIR"; ok 'Bot removed.'; else info 'Uninstall cancelled.'; fi; menu; }

menu
