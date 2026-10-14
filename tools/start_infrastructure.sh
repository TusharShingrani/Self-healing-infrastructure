#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
case "${1:-status}" in
start)
  # Uses the same memory-only credential manager as the original loop.
  python3 "$REPO/tools/lab_shell.py" python3 -c 'import os;assert all(os.environ.get(n) for n in ("CS_URL","CS_KEY","CS_SECRET","LAB_SSH_KEY"))'
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/healer-infrastructure.service <<EOF
[Unit]
Description=Reviewed infrastructure dependency MAPE-K loop
After=network-online.target
[Service]
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 -u $REPO/tools/infrastructure_service.py
Restart=on-failure
RestartSec=10
MemoryMax=256M
CPUQuota=50%
EOF
  systemctl --user daemon-reload
  systemctl --user restart healer-infrastructure
  ;;
stop) systemctl --user stop healer-infrastructure ;;
status) systemctl --user --no-pager status healer-infrastructure ;;
*) exit 2 ;;
esac
