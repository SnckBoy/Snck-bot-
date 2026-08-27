#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Snck"
SERVICE_NAME="snck-discord-bot"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"

if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  TARGET_USER="$SUDO_USER"
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
else
  TARGET_USER="${USER:-$(id -un)}"
  TARGET_HOME="${HOME}"
fi
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
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'die "Installation failed near line $LINENO."' ERR

if command -v apt-get >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip ca-certificates curl
  elif command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip ca-certificates curl
  else
    die "Ubuntu/Debian package installation requires root or sudo."
  fi
fi

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

info "Preparing Snck Bot in ${APP_DIR}..."
for file in bot.py requirements.txt .env.example; do
  if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/$file" && "$SCRIPT_DIR" != "$APP_DIR" ]]; then
    cp -f "$SCRIPT_DIR/$file" "$APP_DIR/$file"
  elif [[ ! -f "$APP_DIR/$file" ]]; then
    curl -fsSL "$REPO_RAW/$file" -o "$APP_DIR/$file"
  fi
done

[[ -s "$APP_DIR/bot.py" ]] || die "bot.py is missing or empty."
[[ -s "$APP_DIR/requirements.txt" ]] || die "requirements.txt is missing or empty."
[[ -s "$APP_DIR/.env.example" ]] || die ".env.example is missing or empty."

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"
[[ -f "$ENV_FILE" ]] || cp "$APP_DIR/.env.example" "$ENV_FILE"

printf '\n========== Snck Bot Setup ==========\n'
read -r -s -p "Discord Bot Token: " DISCORD_TOKEN; echo
[[ -n "$DISCORD_TOKEN" ]] || die "Discord token is required."
read -r -p "Main admin Discord User ID: " MAIN_ADMIN_ID
[[ -n "$MAIN_ADMIN_ID" ]] || die "Main admin Discord ID is required."
read -r -p "VPS IP/hostname (optional): " YOUR_SERVER_IP
read -r -p "Deploy role ID [0 = disabled]: " DEPLOY_ROLE_ID; DEPLOY_ROLE_ID="${DEPLOY_ROLE_ID:-0}"
read -r -p "Deploy RAM GB [16]: " DEPLOY_RAM; DEPLOY_RAM="${DEPLOY_RAM:-16}"
read -r -p "Deploy CPU cores [3]: " DEPLOY_CPU; DEPLOY_CPU="${DEPLOY_CPU:-3}"
read -r -p "Deploy disk GB [80]: " DEPLOY_DISK; DEPLOY_DISK="${DEPLOY_DISK:-80}"
read -r -p "Per-user VPS limit [1]: " VPS_DEPLOY_LIMIT; VPS_DEPLOY_LIMIT="${VPS_DEPLOY_LIMIT:-1}"
read -r -p "Global VPS slot limit [0 = unlimited]: " DEPLOY_SLOT; DEPLOY_SLOT="${DEPLOY_SLOT:-0}"

export ENV_FILE DISCORD_TOKEN MAIN_ADMIN_ID YOUR_SERVER_IP DEPLOY_ROLE_ID DEPLOY_RAM DEPLOY_CPU DEPLOY_DISK VPS_DEPLOY_LIMIT DEPLOY_SLOT
python3 <<'PY'
from pathlib import Path
import os
p = Path(os.environ["ENV_FILE"])
data = {}
for line in p.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        data[k] = v
for key in ("DISCORD_TOKEN", "MAIN_ADMIN_ID", "YOUR_SERVER_IP", "DEPLOY_ROLE_ID", "DEPLOY_RAM", "DEPLOY_CPU", "DEPLOY_DISK", "VPS_DEPLOY_LIMIT", "DEPLOY_SLOT"):
    data[key] = os.environ.get(key, "")
data["BOT_NAME"] = "Snck"
data.setdefault("PREFIX", "!")
data.setdefault("VPS_USER_ROLE_ID", "0")
data.setdefault("DEFAULT_STORAGE_POOL", "default")
data.setdefault("BOT_VERSION", "1.0")
data.setdefault("BOT_DEVELOPER", "Snck")
data.setdefault("BOT_THUMBNAIL_URL", "")
data.setdefault("BOT_ICON_URL", "")
data.setdefault("DEFAULT_VPS_EXPIRATION_DAYS", "30")
data.setdefault("EXPIRATION_WARNING_DAYS", "1")
p.write_text("\n".join(f"{k}={v}" for k, v in data.items()) + "\n")
PY
chmod 600 "$ENV_FILE"
"$VENV/bin/python" -m py_compile "$APP_DIR/bot.py"

SYSTEMD_READY=false
if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
  PRIV=""
  if [[ "$(id -u)" -eq 0 ]]; then
    PRIV=""
  elif command -v sudo >/dev/null 2>&1 && sudo -v; then
    PRIV="sudo"
  else
    warn "systemd is present but root/sudo access is unavailable; using background mode."
  fi

  if [[ "$(id -u)" -eq 0 || "$PRIV" == "sudo" ]]; then
    SERVICE_TMP="$(mktemp)"
    cat > "$SERVICE_TMP" <<EOF
[Unit]
Description=Snck Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV}/bin/python ${APP_DIR}/bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
    if [[ "$PRIV" == "sudo" ]]; then
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
    ok "Snck Bot installed and started with systemd."
    echo "Logs: journalctl -u ${SERVICE_NAME} -f"
  fi
fi

if [[ "$SYSTEMD_READY" != true ]]; then
  chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR" 2>/dev/null || true
  nohup "$VENV/bin/python" "$APP_DIR/bot.py" > "$APP_DIR/bot.log" 2>&1 &
  echo $! > "$APP_DIR/bot.pid"
  sleep 2
  if kill -0 "$(cat "$APP_DIR/bot.pid")" 2>/dev/null; then
    ok "Snck Bot started in background mode."
    echo "Logs: tail -f $APP_DIR/bot.log"
  else
    warn "Snck Bot did not stay running. Check: $APP_DIR/bot.log"
  fi
fi
chmod 600 "$ENV_FILE"
printf '\nSnck Bot is installed. Configuration: %s\n' "$ENV_FILE"
printf 'Codespaces/non-systemd mode is supported, but actual LXC/VPS creation requires a privileged VPS node.\n'
