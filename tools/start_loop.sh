#!/usr/bin/env bash
# Run the MAPE-K loop as a systemd user service on the healer.
#
#   bash tools/start_loop.sh start [A|B|C]    default C
#   bash tools/start_loop.sh stop
#   bash tools/start_loop.sh status
#   bash tools/start_loop.sh logs
#
# Credentials are handed to the user service manager in memory with
# import-environment. They are never written to a file, and they are gone
# after a reboot of the healer, when this script must be run again from a
# shell that has CS_KEY and CS_SECRET exported.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UNIT=healer-loop.service
CMD=${1:-status}

case "$CMD" in
start)
    CONFIG=${2:-C}
    case "$CONFIG" in A|B|C) ;; *) echo "config must be A, B or C" >&2; exit 2 ;; esac
    for v in CS_URL CS_KEY CS_SECRET LAB_SSH_KEY; do
        [ -n "${!v:-}" ] || { echo "$v is not set in this shell" >&2; exit 1; }
    done
    mkdir -p ~/.config/systemd/user
    cat > ~/.config/systemd/user/$UNIT <<UNITFILE
[Unit]
Description=MAPE-K self-healing loop (selfheal)
After=network-online.target

[Service]
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 -u $REPO/tools/healer_service.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
UNITFILE
    export HEALER_CONFIG=$CONFIG
    export HEALER_NODES=${HEALER_NODES:-app-1,app-2}
    export HEALER_REVIEW=${HEALER_REVIEW:-1}
    systemctl --user import-environment CS_URL CS_KEY CS_SECRET LAB_SSH_KEY HEALER_CONFIG HEALER_NODES HEALER_REVIEW
    # optional LLM advisor (Google Gemini), in memory like the other secrets
    for v in GEMINI_API_KEY HEALER_GEMINI_MODEL; do
        if [ -n "${!v:-}" ]; then
            systemctl --user import-environment $v
        else
            systemctl --user unset-environment $v
        fi
    done
    systemctl --user daemon-reload
    systemctl --user restart $UNIT
    sleep 3
    systemctl --user --no-pager status $UNIT | head -5
    ;;
stop)
    systemctl --user stop $UNIT || true
    systemctl --user unset-environment CS_KEY CS_SECRET GEMINI_API_KEY
    echo "stopped, credentials removed from the user manager"
    ;;
status) systemctl --user --no-pager status $UNIT ;;
logs)   journalctl --user -u $UNIT -n "${2:-50}" --no-pager ;;
*)      echo "usage: $0 start [A|B|C] | stop | status | logs" >&2; exit 2 ;;
esac
