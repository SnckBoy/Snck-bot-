#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Snck Bot"
SERVICE_NAME="snck-discord-bot"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"

# Resolve the real user even when the installer is run through `sudo bash`.
if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  TARGET_USER="$SUDO_USER"
else
  TARGET_USER="${USER:-$(id -un)}"
fi

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"
TARGET_HOME="${TARGET_HOME:-${HOME:-/root}}"
APP_DIR="${TARGET_HOME}/snck-bot"
VENV="${APP_DIR}/.venv"
ENV_FILE="${APP_DIR}/.env"
LOG_FILE="${APP_DIR}/install.log"

cyan='\033[0;36m'; green='\033[0;32m'; yellow='\033[1;33m'; reset='\033[0m'
info(){ echo -e "${cyan}[Snck]${reset} $*"; }
ok(){ echo -e "${green}[OK]${reset} $*"; }
warn(){ echo -e "${yellow}[WARN]${reset} $*"; }
die(){ echo "ERROR: $*" >&2; echo "Installer log: ${LOG_FILE}" >&2; exit 1; }

mkdir -p "$APP_DIR"
touch "$LOG_FILE"
if [[ "$(id -u)" -eq 0 ]]; then
  chown "$TARGET_USER:$TARGET_USER" "$APP_DIR" "$LOG_FILE" 2>/dev/null || true
fi

exec > >(tee -a "$LOG_FILE") 2>&1
trap 'die "Installation failed near line $LINENO."' ERR

run_priv() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "Root or sudo is required for system packages."
  fi
}

if command -v apt-get >/dev/null 2>&1; then
  info "Updating Ubuntu/Debian packages..."
  run_priv apt-get update -y
  run_priv env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv python3-pip ca-certificates curl snapd
else
  command -v python3 >/dev/null 2>&1 || die "python3 is required."
  command -v curl >/dev/null 2>&1 || die "curl is required."
fi

# Snck uses LXC/LXD for local VPS/container operations. The LXD snap is the
# recommended installation method on Ubuntu and provides the lxc client.
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
  warn "snap is unavailable. The bot can still start, but VPS deployment needs a configured LXC/LXD node."
fi

info "Downloading Snck Bot files..."
for file in bot.py requirements.txt .env.example launcher.py; do
  tmp="$(mktemp)"
  curl --fail --silent --show-error --location --retry 3 --retry-delay 2 \
    "$REPO_RAW/$file" -o "$tmp" || { rm -f "$tmp"; die "Failed to download $file from GitHub."; }
  [[ -s "$tmp" ]] || { rm -f "$tmp"; die "Downloaded $file is empty."; }
  install -m 644 "$tmp" "$APP_DIR/$file"
  rm -f "$tmp"
done

info "Creating isolated Python environment..."
python3 -m venv "$VENV" || die "Could not create Python virtual environment."
"$VENV/bin/python" -m pip install --upgrade pip wheel
"$VENV/bin/pip" install --upgrade -r "$APP_DIR/requirements.txt"

# The only interactive value is the bot token. /dev/tty makes this work with
# both `curl | bash` and `curl | sudo bash` without consuming the installer pipe.
printf '\n========== Snck Bot Setup ==========\n'
read -r -s -p "Discord Bot Token: " DISCORD_TOKEN </dev/tty; echo
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
BOT_VERSION=1.0
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
chown "$TARGET_USER:$TARGET_USER" "$ENV_FILE" "$APP_DIR" 2>/dev/null || true

"$VENV/bin/python" -m py_compile "$APP_DIR/bot.py" "$APP_DIR/launcher.py" || die "Python syntax validation failed."

SYSTEMD_READY=false
if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    PRIV_MODE=root
  elif command -v sudo >/dev/null 2>&1; then
    sudo -v || die "sudo authentication failed."
    PRIV_MODE=sudo
  else
    PRIV_MODE=
  fi

  if [[ -n "$PRIV_MODE" ]]; then
    SERVICE_TMP="$(mktemp)"
    cat > "$SERVICE_TMP" <<EOF_SERVICE
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

    if [[ "$PRIV_MODE" == "sudo" ]]; then
      sudo install -m 644 "$SERVICE_TMP" "/etc/systemd/system/${SERVICE_NAME}.service"
      sudo chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR"
      sudo systemctl daemon-reload
      sudo systemctl enable --now "$SERVICE_NAME"
    else
      install -m 644 "$SERVICE_TMP" "/etc/systemd/system/${SERVICE_NAME}.service"
      chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR"
      systemctl daemon-reload
      systemctl enable --now "$SERVICE_NAME"
    fi
    rm -f "$SERVICE_TMP"
    SYSTEMD_READY=true
    ok "Snck Bot is installed and running with systemd."
    echo "Status: sudo systemctl status ${SERVICE_NAME}"
    echo "Logs:   sudo journalctl -u ${SERVICE_NAME} -f"
  fi
fi

if [[ "$SYSTEMD_READY" != true ]]; then
  chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR" 2>/dev/null || true

  if [[ -f "$APP_DIR/bot.pid" ]]; then
    old_pid="$(cat "$APP_DIR/bot.pid" 2>/dev/null || true)"
    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      sleep 1
    fi
  fi

  nohup "$VENV/bin/python" "$APP_DIR/launcher.py" >> "$APP_DIR/bot.log" 2>&1 &
  BOT_PID=$!
  echo "$BOT_PID" > "$APP_DIR/bot.pid"
  sleep 4

  if kill -0 "$BOT_PID" 2>/dev/null; then
    ok "Snck Bot is installed and running in background mode."
    echo "PID:    $BOT_PID"
    echo "Logs:   tail -f $APP_DIR/bot.log"
  else
    warn "Snck Bot did not stay running. Check: $APP_DIR/bot.log"
    exit 1
  fi
fi

chmod 600 "$ENV_FILE"
printf '\nSnck Bot installation complete.\n'
printf 'Only the Discord bot token was requested. The bot owner is detected automatically.\n'
printf 'App directory: %s\n' "$APP_DIR"
