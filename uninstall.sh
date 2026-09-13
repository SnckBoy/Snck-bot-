#!/bin/bash
set -u
A=${SNCK_APP_DIR:-/opt/snck-bot}; P=snck-kvm-panel; B=snck-discord-bot
[ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" "$@"
echo 'SNCK PANEL + BOT UNINSTALL'
printf 'Type UNINSTALL or y to continue: '; read -r x </dev/tty || x=
[[ "$x" == UNINSTALL || "$x" =~ ^[Yy]([Ee][Ss])?$ ]] || exit 0
for s in "$P" "$B"; do systemctl stop "$s" 2>/dev/null || :; systemctl disable "$s" 2>/dev/null || :; done
rm -f /etc/systemd/system/$P.service /etc/systemd/system/$B.service /etc/systemd/system/multi-user.target.wants/$P.service /etc/systemd/system/multi-user.target.wants/$B.service
systemctl daemon-reload; systemctl reset-failed "$P" "$B" 2>/dev/null || :
pkill -f "$A" 2>/dev/null || :
rm -rf "$A"
echo 'SNCK PANEL + BOT UNINSTALLED SUCCESSFULLY'