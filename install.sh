#!/usr/bin/env bash
set -Eeuo pipefail
APP_NAME="SNCK DISCORD VPS DEPLOY BOT + KVM PANEL"
SERVICE_NAME="snck-kvm-panel"
REPO_RAW="https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main"
INSTALLER_VERSION="5.0.0"
APP_DIR="${SNCK_APP_DIR:-/opt/snck-bot}"
ENV_FILE="$APP_DIR/.env"
ESC=$'\033'; RESET="${ESC}[0m"; BOLD="${ESC}[1m"; DIM="${ESC}[2m"
CYAN="${ESC}[38;5;51m"; BLUE="${ESC}[38;5;39m"; PURPLE="${ESC}[38;5;141m"; MAGENTA="${ESC}[38;5;201m"
GREEN="${ESC}[38;5;82m"; YELLOW="${ESC}[38;5;220m"; RED="${ESC}[38;5;196m"; WHITE="${ESC}[38;5;255m"
[[ -r /dev/tty ]] || { printf '%b\n' "${RED}ERROR${RESET}: interactive terminal required." >&2; exit 1; }
exec 3<>/dev/tty
say(){ printf '%b\n' "$*"; }; info(){ say "${CYAN}[INFO]${RESET} $*"; }; ok(){ say "${GREEN}[ OK ]${RESET} $*"; }; warn(){ say "${YELLOW}[WARN]${RESET} $*"; }; die(){ say "${RED}[FAIL]${RESET} $*" >&2; exit 1; }
installed(){ [[ -d "$APP_DIR" && -f "$APP_DIR/panel.py" && -f "$APP_DIR/kvm.py" ]]; }
files_ready(){ [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/panel.py" && -f "$APP_DIR/kvm.py" && -f "$APP_DIR/bot.py" && -f "$APP_DIR/launcher.py" && -f "$APP_DIR/requirements.txt" ]]; }
service_state(){ if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then printf ONLINE; elif command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then printf OFFLINE; else printf 'NOT INSTALLED'; fi; }
kvm_state(){ [[ -e /dev/kvm ]] && printf ENABLED || printf UNAVAILABLE; }
status(){ local i f s k; installed&&i=INSTALLED||i='NOT INSTALLED'; files_ready&&f=READY||f='NOT READY'; s=$(service_state); k=$(kvm_state); printf '%b  LIVE STATUS  %bInstaller v%s%b\n' "$BOLD$CYAN" "$DIM" "$INSTALLER_VERSION" "$RESET"; printf '%b  ╭──────────────────────────────────────────────────╮%b\n' "$BLUE" "$RESET"; printf '%b  │  PANEL INSTALL  : %-30s │%b\n' "$GREEN" "$i" "$RESET"; printf '%b  │  PANEL FILES    : %-30s │%b\n' "$CYAN" "$f" "$RESET"; printf '%b  │  PANEL SERVICE  : %-30s │%b\n' "$GREEN" "$s" "$RESET"; printf '%b  │  KVM            : %-30s │%b\n' "$PURPLE" "$k" "$RESET"; printf '%b  ╰──────────────────────────────────────────────────╯%b\n' "$BLUE" "$RESET"; }
banner(){ printf '\n%b╭──────────────────────────────────────────────────────╮%b\n%b│%b  %bSNCK DISCORD VPS DEPLOY BOT + KVM PANEL%b         %b│%b\n%b│%b  %bPremium KVM VPS management and bot control%b        %b│%b\n%b├──────────────────────────────────────────────────────┤%b\n%b│%b  %bPRODUCTION INSTALLER%b   %bUbuntu / Debian / KVM%b     %b│%b\n%b╰──────────────────────────────────────────────────────╯%b\n' "$PURPLE" "$RESET" "$PURPLE" "$RESET" "$BOLD$WHITE" "$RESET" "$PURPLE" "$RESET" "$PURPLE" "$RESET" "$DIM$CYAN" "$RESET" "$PURPLE" "$RESET" "$BLUE" "$RESET" "$BOLD$MAGENTA" "$RESET" "$CYAN" "$RESET" "$BLUE" "$RESET" "$PURPLE" "$RESET"; }
require_root(){ [[ $(id -u) -eq 0 ]] || exec sudo -E bash "$0" "$@"; }
install(){
 require_root
 info "Installing host dependencies..."
 apt-get update -y
 DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl ca-certificates qemu-kvm qemu-utils libvirt-daemon-system libvirt-daemon-driver-qemu libvirt-clients virtinst cloud-image-utils bridge-utils cpu-checker openssh-client
 systemctl enable --now libvirtd 2>/dev/null || true
 mkdir -p "$APP_DIR"
 info "Downloading Snck panel, KVM module and bot..."
 for f in panel.py kvm.py bot.py launcher.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || die "Failed to download $f"; done
 chmod +x "$APP_DIR/start.sh"; cd "$APP_DIR"
 python3 -m venv venv
 "$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null
 "$APP_DIR/venv/bin/pip" install -r requirements.txt || die "Python dependency installation failed."
 python3 "$APP_DIR/panel.py" --bootstrap > "$APP_DIR/first-install.txt"
 chmod 600 "$APP_DIR/first-install.txt"
 local license admin password
 license=$(grep '^SNCK_LICENSE=' "$APP_DIR/first-install.txt" | cut -d= -f2-)
 admin=$(grep '^SNCK_ADMIN_USER=' "$APP_DIR/first-install.txt" | cut -d= -f2-)
 password=$(grep '^SNCK_ADMIN_PASSWORD=' "$APP_DIR/first-install.txt" | cut -d= -f2-)
 cat > "$APP_DIR/.env" <<EOF
SNCK_PANEL_PORT=5000
SNCK_PANEL_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
BOT_NAME=Snck Discord VPS Deploy Bot
PREFIX=!
EOF
 chmod 600 "$APP_DIR/.env"
 if [[ -d /run/systemd/system ]]; then
  cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Snck KVM Panel
After=network-online.target libvirtd.service
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/panel.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload; systemctl enable --now "$SERVICE_NAME"; sleep 2
  systemctl is-active --quiet "$SERVICE_NAME" || { journalctl -u "$SERVICE_NAME" -n 60 --no-pager || true; die "Panel failed to start."; }
 else
  warn "systemd is unavailable; start the panel with $APP_DIR/start.sh"
 fi
 printf '\n%b╭────────────── SNCK INSTALL COMPLETE ──────────────╮%b\n' "$GREEN" "$RESET"
 printf '%b│%b Panel: http://%s:5000\n' "$GREEN" "$RESET" "$(hostname -I | awk '{print $1}')"
 printf '%b│%b License: %s\n' "$GREEN" "$RESET" "$license"
 printf '%b│%b Admin user: %s\n' "$GREEN" "$RESET" "$admin"
 printf '%b│%b Admin password: %s\n' "$GREEN" "$RESET" "$password"
 printf '%b╰────────────────────────────────────────────────────╯%b\n' "$GREEN" "$RESET"
 warn "Keep the displayed license and admin password private."
}
update(){
 require_root; installed || { warn "Panel is not installed."; return; }
 info "Updating Snck panel, KVM module and bot..."
 for f in panel.py kvm.py bot.py launcher.py requirements.txt start.sh; do curl -fsSL "$REPO_RAW/$f" -o "$APP_DIR/$f" || die "Failed to update $f"; done
 "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" || die "Dependency update failed."
 systemctl restart "$SERVICE_NAME" 2>/dev/null || true
 ok "Snck panel and bot files updated."
}
uninstall(){
 require_root; installed || { warn "Nothing installed."; return; }
 printf 'Remove Snck panel and local data? [y/N]: '; IFS= read -r c <&3 || true; [[ $c =~ ^[Yy]$ ]] || return
 systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true; rm -f "/etc/systemd/system/$SERVICE_NAME.service"; systemctl daemon-reload 2>/dev/null || true; rm -rf "$APP_DIR"; ok "Snck panel removed."
}
status_detail(){ banner; status; printf '\n%b  KVM HOST%b\n' "$BOLD$CYAN" "$RESET"; if command -v kvm-ok >/dev/null 2>&1; then kvm-ok 2>&1 | head -n 3 || true; fi; if command -v virsh >/dev/null 2>&1; then printf '\n  libvirt: '; virsh version --daemon 2>/dev/null | head -n 1 || printf 'not responding\n'; fi; printf '\n%b  Press Enter to return...%b' "$DIM" "$RESET"; IFS= read -r _ <&3 || true; }
menu(){ while true; do banner; status; printf '\n%b  MAIN MENU%b\n' "$BOLD$CYAN" "$RESET"; printf '%b  [1]  Install Snck KVM Panel + Discord Bot%b\n' "$GREEN" "$RESET"; printf '%b  [2]  Update Panel + Bot%b\n' "$CYAN" "$RESET"; printf '%b  [3]  Uninstall%b\n' "$RED" "$RESET"; printf '%b  [4]  Refresh Status%b\n' "$YELLOW" "$RESET"; printf '%b  [0]  Exit%b\n\n' "$MAGENTA" "$RESET"; printf '%b  Select an option [0-4]: %b' "$BOLD$WHITE" "$RESET"; IFS= read -r c <&3 || true; case "$c" in 1) install;;2) update;;3) uninstall;;4) status_detail;;0) exit 0;;*) warn 'Invalid option.'; sleep 1;;esac; done; }
menu
