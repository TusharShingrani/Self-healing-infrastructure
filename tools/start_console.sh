#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
case "${1:-status}" in
start)
  test -f "$HOME/.config/healer-console/auth.json" || { echo 'Set a console password first: python3 tools/console.py --set-password'; exit 1; }
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/healer-console.service" <<EOF
[Unit]
Description=Private job-service operator console
After=healer-jobs.service
[Service]
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 -u $REPO/tools/console.py
Restart=on-failure
RestartSec=10
MemoryMax=256M
CPUQuota=50%
NoNewPrivileges=true
UMask=0077
[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable healer-console
  systemctl --user restart healer-console
  ;;
stop) systemctl --user stop healer-console ;;
status) systemctl --user --no-pager status healer-console ;;
*) echo 'Usage: start_console.sh start|stop|status'; exit 2 ;;
esac
