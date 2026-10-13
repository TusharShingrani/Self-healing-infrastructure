#!/usr/bin/env bash
# Provision a freshly deployed instance from the healer, and log everything.
#
#   bash tools/provision.sh app <ip> [logfile]       install_lab_host.sh + install_exporters.sh
#   bash tools/provision.sh monitor <ip> [logfile]   install_monitor.sh
#
# Host keys are checked against the lab known_hosts file, never disabled. The
# first contact is recorded by lab.py deploy (accept-new); after that a changed
# key stops this script.
set -uo pipefail
ROLE=${1:?role: app or monitor}; IP=${2:?ip address}; LOG=${3:-/dev/null}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
KEY=${LAB_SSH_KEY:?LAB_SSH_KEY must point at the lab private key}
SSHO=(-o BatchMode=yes -o StrictHostKeyChecking=yes
      -o UserKnownHostsFile="$HOME/.ssh/known_hosts_healer_lab"
      -i "$KEY" -o IdentitiesOnly=yes -o ConnectTimeout=20)

case "$ROLE" in
    app)     FILES=("$HERE/install_lab_host.sh" "$HERE/install_exporters.sh")
             RUN='sudo bash ~/lab/install_lab_host.sh && sudo bash ~/lab/install_exporters.sh' ;;
    monitor) FILES=("$HERE/install_monitor.sh")
             RUN='sudo bash ~/lab/install_monitor.sh' ;;
    *)       echo "unknown role $ROLE" >&2; exit 2 ;;
esac

{
echo "provision $ROLE at $IP"
echo "start $(date -u +%FT%TZ)"
START=$(date +%s)
ssh "${SSHO[@]}" "ubuntu@$IP" 'rm -rf ~/lab && mkdir -p ~/lab/lab-host ~/lab/monitor' &&
scp -q "${SSHO[@]}" "${FILES[@]}" "ubuntu@$IP:lab/" &&
scp -q "${SSHO[@]}" "$HERE"/lab-host/* "ubuntu@$IP:lab/lab-host/" &&
scp -q -r "${SSHO[@]}" "$HERE"/../monitoring/. "ubuntu@$IP:lab/monitor/" 2>/dev/null
ssh "${SSHO[@]}" "ubuntu@$IP" "$RUN"
RC=$?
echo "exit=$RC"
echo "end $(date -u +%FT%TZ) wall=$(( $(date +%s) - START ))s"
exit $RC
} 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
