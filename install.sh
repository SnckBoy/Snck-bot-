#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Snck Discord VPS Deploy Bot"
SERVICE_NAME="snck-discord-bot"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"

# IMPORTANT: when executed as `curl ... | bash`, fd 0 belongs to the script
# itself. Never replace fd 0, because Bash still needs it to read the script.
# fd 3 is the user's interactive terminal.
if [[ -r /dev/tty ]]; then
  exec 3</dev/tty
else
  echo "ERROR: An interactive terminal is required for the Snck Discord VPS Deploy Bot menu." >&2
  echo "Use an SSH/console session with a real terminal." >&2
  exit 1
fi

cyan='\033[1;36m'; blue='\033[1;34m'; magenta='\033[1;35m'; green='\033[1;32m'; yellow='\033[1;33m'; red='\033[1;31m'; white='\033[1;37m'; dim='\033[2m'; reset='\033[0m'
info(){ echo -e "${cyan}[SNCK]${reset} $*"; }
ok(){ echo -e "${green}[  OK ]${reset} $*"; }
warn(){ echo -e "${yellow}[ WARN ]${reset} $*"; }
die(){ echo -e "${red}[ ERROR ]${reset} $*" >&2; [[ -n "${LOG_FILE:-}" ]] && echo "Installer log: ${LOG_FILE}" >&2; exit 1; }

# Keep all potentially slow NSS/package/filesystem work OUTSIDE the menu path.
resolve_paths() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    TARGET_USER="$SUDO_USER"
  else
    TARGET_USER="${USER:-$(id -un)}"
  fi

  # Avoid a potentially blocking NSS lookup. passwd(1) is enough for normal
  # Ubuntu/Debian accounts and has a quick fallback to HOME.
  TARGET_HOME=""
  if command -v getent >/dev/null 2>&1; then
    TARGET_HOME="$(timeout 3 getent passwd "$TARGET_USER" 2>/dev/null | cut -d: -f6 || true)"
  fi
  TARGET_HOME="${TARGET_HOME:-${HOME:-/root}}"
  APP_DIR="${TARGET_HOME}/snck-bot"
  VENV="${APP_DIR}/.venv"
  ENV_FILE="${APP_DIR}/.env"
  LOG_FILE="${APP_DIR}/install.log"
}

run_priv() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "Root or sudo is required for this operation."
  fi
}

read_terminal() {
  local __var="$1"
  local __value=""
  IFS= read -r __value <&3 || true
  printf -v "$__var" '%s' "$__value"
}

show_banner() {
  echo
  echo -e "${cyan}╔══════════════════════════════════════════════════╗${reset}"
  echo -e "${cyan}║${reset}  ${magenta}✦${reset} ${white}SNCK DISCORD VPS DEPLOY BOT${reset}                 ${cyan}║${reset}"
  echo -e "${cyan}║${reset}  ${dim}Premium VPS deployment & management installer${reset} ${cyan}║${reset}"
  echo -e "${cyan}╠══════════════════════════════════════════════════╣${reset}"
  echo -e "${cyan}║${reset}  ${green}●${reset} ${white}Production Installer${reset}   ${blue}◆${reset} ${white}Ubuntu / Debian${reset}       ${cyan}║${reset}"
  echo -e "${cyan}╚══════════════════════════════════════════════════╝${reset}"
  echo
}

show_menu() {
  show_banner
  echo -e "  ${magenta}┌─${reset} ${white}MAIN MENU${reset} ${magenta}────────────────────────────────┐${reset}"
  echo -e "  ${magenta}│${reset}  ${green}[1]${reset} 🚀  ${white}Install Snck Discord VPS Deploy Bot${reset}  ${magenta}│${reset}"
  echo -e "  ${magenta}│${reset}  ${blue}[2]${reset} 🔄  ${white}Update Bot${reset}                         ${magenta}│${reset}"
  echo -e "  ${magenta}│${reset}  ${red}[3]${reset} 🗑️   ${white}Uninstall Bot${reset}                     ${magenta}│${reset}"
  echo -e "  ${magenta}│${reset}  ${cyan}[4]${reset} 📊  ${white}Check Bot Status${reset}                  ${magenta}│${reset}"
  echo -e "  ${magenta}│${reset}  ${yellow}[0]${reset} ❌  ${white}Exit${reset}                              ${magenta}│${reset}"
  echo -e "  ${magenta}└───────────────────────────────────────────────┘${reset}"
  echo
  printf "  ${cyan}➜${reset} ${white}Select an option${reset} ${dim}[1-4, 0]${reset}: "
  read_terminal choice
  echo
}

prepare_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    info "Updating Ubuntu/Debian packages..."
    run_priv apt-get update -y
    run_priv env DEBIAN_FRONTEND=noninteractive apt-get install -y \
      python3 python3-venv python3-pip ca-certificates curl snapd
  else
    command -v python3 >/dev/null 2>&1 || die "python3 is required."
    command -v curl >/dev/null 2>&1 || die "curl is required."
  fi
}

prepare_lxd() {
  if command -v snap >/dev/null 2>&1; then
    info "Checking LXD virtualization support..."
    if ! snap list lxd >/dev/null 2>&1; then
      run_priv snap install lxd
    fi
    run_priv getent group lxd >/dev/null 2>&1 || run_priv groupadd --system lxd
    run_priv usermod -aG lxd "$TARGET_USER" || true
    if ! run_priv lxc info >/dev/null 2>&1; then
      info "Initializing LXD with a minimal local configuration..."
      run_priv lxd init --minimal || warn "LXD initialization needs manual configuration."
    fi
  else
    warn "snap is unavailable. VPS deployment needs a configured LXC/LXD node."
  fi
}

download_files() {
  mkdir -p "$APP_DIR"
  touch "$LOG_FILE"
  if [[ "$(id -u)" -eq 0 ]]; then
    chown "$TARGET_USER:$TARGET_USER" "$APP_DIR" "$LOG_FILE" 2>/dev/null || true
  fi

  info "Downloading Snck Bot files..."
  for file in bot.py requirements.txt .env.example launcher.py start.sh; do
    local tmp
    tmp="$(mktemp)"
    if ! curl --fail --silent --show-error --location --retry 3 --retry-delay 2 \
      "$REPO_RAW/$file" -o "$tmp"; then
      rm -f "$tmp"
      die "Failed to download $file from GitHub."
    fi
    [[ -s "$tmp" ]] || { rm -f "$tmp"; die "Downloaded $file is empty."; }
    install -m 644 "$tmp" "$APP_DIR/$file"
    rm -f "$tmp"
  done
  chmod +x "$APP_DIR/start.sh"
}

create_service() {
  SYSTEMD_READY=false
  if [[ ! -d /run/systemd/system ]] || ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi

  local service_tmp
  service_tmp="$(mktemp)"
  cat > "$service_tmp" <<EOF_SERVICE
[Unit]
Description=Snck Discord VPS Bot
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
SupplementaryGroups=lxd
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV}/bin/python ${APP_DIR}/launcher.py
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF_SERVICE

  run_priv install -m 644 "$service_tmp" "/etc/systemd/system/${SERVICE_NAME}.service"
  rm -f "$service_tmp"
  run_priv chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR"
  run_priv systemctl daemon-reload
  run_priv systemctl enable --now "$SERVICE_NAME"
  SYSTEMD_READY=true
  ok "Snck Bot service is enabled and running."
}

install_bot() {
  resolve_paths
  echo -e "${cyan}╔══════════════════════════════════════════════════╗${reset}"
  echo -e "${cyan}║${reset}  ${magenta}🚀 INSTALLING SNCK DISCORD VPS DEPLOY BOT${reset}   ${cyan}║${reset}"
  echo -e "${cyan}╚══════════════════════════════════════════════════╝${reset}"
  echo

  prepare_packages
  prepare_lxd
  download_files

  info "Creating isolated Python environment..."
  python3 -m venv "$VENV" || die "Could not create Python virtual environment."
  "$VENV/bin/python" -m pip install --upgrade pip wheel
  "$VENV/bin/pip" install --upgrade -r "$APP_DIR/requirements.txt"

  echo
  echo -e "${cyan}========== ${white}Discord Bot Setup${cyan} ==========${reset}"
  echo -e "${dim}Only the Discord bot token is required.${reset}"
  echo
  printf "${cyan}🔐 Discord Bot Token:${reset} "
  IFS= read -r -s DISCORD_TOKEN <&3 || true
  echo
  [[ -n "$DISCORD_TOKEN" ]] || die "Discord token is required."

  cat > "$ENV_FILE" <<EOF_ENV
DISCORD_TOKEN=$DISCORD_TOKEN
BOT_NAME=Snck
PREFIX=!
MAIN_ADMIN_ID=0
YOUR_SERVER_IP=
VPS_USER_ROLE_ID=0
DEFAULT_STORAGE_POOL=default
HOST_MOTD=
BOT_VERSION=2.0
BOT_DEVELOPER=Snck
BOT_THUMBNAIL_URL=
BOT_ICON_URL=
DEFAULT_VPS_EXPIRATION_DAYS=30
EXPIRATION_WARNING_DAYS=1
DEPLOY_RAM=16
DEPLOY_CPU=3
DEPLOY_DISK=80
DEPLOY_ROLE_ID=0
DEPLOY_SLOT=0
VPS_DEPLOY_LIMIT=1
EOF_ENV
  chmod 600 "$ENV_FILE"
  run_priv chown "$TARGET_USER:$TARGET_USER" "$ENV_FILE" "$APP_DIR" 2>/dev/null || true

  "$VENV/bin/python" -m py_compile "$APP_DIR/bot.py" "$APP_DIR/launcher.py" || die "Python syntax validation failed."
  create_service

  if [[ "${SYSTEMD_READY:-false}" != true ]]; then
    run_priv chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR" 2>/dev/null || true
    nohup "$VENV/bin/python" "$APP_DIR/launcher.py" >> "$APP_DIR/bot.log" 2>&1 &
    BOT_PID=$!
    echo "$BOT_PID" > "$APP_DIR/bot.pid"
    sleep 4
    if kill -0 "$BOT_PID" 2>/dev/null; then
      ok "Snck Bot is running in background mode."
      echo "PID: $BOT_PID"
      echo "Logs: tail -f $APP_DIR/bot.log"
    else
      die "Snck Bot did not stay running. Check $APP_DIR/bot.log"
    fi
  fi

  chmod 600 "$ENV_FILE"
  echo
  ok "Installation complete!"
  echo "App directory: $APP_DIR"
  echo "Bot owner is detected automatically from Discord."
  echo
  echo "Next commands:"
  echo "  sudo systemctl status $SERVICE_NAME"
  echo "  sudo journalctl -u $SERVICE_NAME -f"
}

update_bot() {
  resolve_paths
  [[ -d "$APP_DIR" ]] || die "Snck Bot is not installed at $APP_DIR."
  [[ -f "$ENV_FILE" ]] || die "Bot configuration is missing: $ENV_FILE"

  info "Updating Snck Bot..."
  download_files
  [[ -d "$VENV" ]] || die "Python environment is missing. Run Install first."
  "$VENV/bin/pip" install --upgrade -r "$APP_DIR/requirements.txt"
  "$VENV/bin/python" -m py_compile "$APP_DIR/bot.py" "$APP_DIR/launcher.py" || die "Python syntax validation failed."

  if [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]; then
    create_service
  elif [[ -f "$APP_DIR/bot.pid" ]]; then
    local old_pid
    old_pid="$(cat "$APP_DIR/bot.pid" 2>/dev/null || true)"
    if [[ "$old_pid" =~ ^[0-9]+$ ]]; then kill "$old_pid" 2>/dev/null || true; fi
    nohup "$VENV/bin/python" "$APP_DIR/launcher.py" >> "$APP_DIR/bot.log" 2>&1 &
    echo "$!" > "$APP_DIR/bot.pid"
  fi
  ok "Snck Bot update complete."
}

uninstall_bot() {
  resolve_paths
  echo "This will remove Snck Bot and its system service from this VPS."
  printf "Type YES to continue: "
  read_terminal confirm
  [[ "$confirm" == "YES" ]] || { echo "Cancelled."; return 0; }

  if command -v systemctl >/dev/null 2>&1; then
    run_priv systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    run_priv rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    run_priv systemctl daemon-reload 2>/dev/null || true
  fi

  if [[ -f "$APP_DIR/bot.pid" ]]; then
    local old_pid
    old_pid="$(cat "$APP_DIR/bot.pid" 2>/dev/null || true)"
    if [[ "$old_pid" =~ ^[0-9]+$ ]]; then kill "$old_pid" 2>/dev/null || true; fi
  fi

  run_priv rm -rf "$APP_DIR"
  ok "Snck Bot has been uninstalled."
}

status_bot() {
  resolve_paths
  show_banner
  if [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]] && command -v systemctl >/dev/null 2>&1; then
    run_priv systemctl --no-pager status "$SERVICE_NAME" || true
  elif [[ -f "$APP_DIR/bot.pid" ]]; then
    local pid
    pid="$(cat "$APP_DIR/bot.pid" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      ok "Snck Bot is running (PID $pid)."
    else
      warn "Snck Bot is not running."
    fi
  else
    warn "Snck Bot is not installed."
  fi
}

main() {
  # Nothing slow runs before this menu. This is critical for `curl | bash`.
  while true; do
    show_menu
    case "${choice:-}" in
      1) install_bot; break ;;
      2) update_bot; break ;;
      3) uninstall_bot; break ;;
      4) status_bot; printf '\nPress Enter to return to menu... '; read_terminal pause ;;
      0) echo "Goodbye."; exit 0 ;;
      *) warn "Invalid option. Please choose 1, 2, 3, 4, or 0." ;;
    esac
  done
}

main "$@"
