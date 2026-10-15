#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
case "${1:-status}" in
start)
  python3 "$REPO/tools/lab_shell.py" python3 -c 'from pathlib import Path;assert (Path.home()/".config/healer-jobs/kube.json").exists()'
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/healer-jobs.service <<EOF
[Unit]
Description=Reviewed Kubernetes job-processing MAPE-K loop
After=network-online.target
[Service]
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 -u $REPO/tools/jobs_service.py
Restart=on-failure
RestartSec=10
MemoryMax=256M
CPUQuota=50%
[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable healer-jobs
  systemctl --user restart healer-jobs
  ;;
stop) systemctl --user stop healer-jobs ;;
status) systemctl --user --no-pager status healer-jobs ;;
*) exit 2 ;;
esac
