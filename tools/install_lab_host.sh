#!/usr/bin/env bash
# Prepare a lab instance so the healer has something real to look after.
#
# Run on a FRESH instance deployed from the clean template:
#   sudo bash install_lab_host.sh
#
# HOW THE FAILURE IS MADE DETERMINISTIC
#
# Stock nginx does not go down when its log filesystem fills. It keeps serving,
# and a reload with a bad configuration is rolled back so the old one stays
# live. So this lab declares an explicit startup storage requirement: an
# ExecStartPre preflight that refuses to start nginx when the bounded log
# filesystem has less than PREFLIGHT_MIN_MB free.
#
# That makes the chain deterministic and honest:
#
#   fault    rotation policy removed, producer appending to the log volume
#   error    the bounded log filesystem fills
#   failure  the next deliberate RESTART fails its preflight, so nginx stops
#            and /healthz stops answering
#
# The preflight is a lab protocol modelling a real startup storage
# requirement. It must be described as such in the report, never as observed
# nginx behaviour.
#
# What it creates, matching the adapter's contract exactly:
#
#   nginx                                          the infrastructure service
#   /var/log/nginx                                 BOUNDED 512 MiB ext4 volume
#   /etc/nginx/conf.d/healer.conf                  live configuration
#   /opt/healer/reference/healer.conf              known-good reference
#   /etc/logrotate.d/nginx-healer                  live rotation policy
#   /opt/healer/reference/nginx-healer.logrotate   known-good reference
#   /usr/local/sbin/healer-preflight               startup storage requirement
#   healer-logflood.service/.timer                 fault generator, disabled

set -euo pipefail

LOG_MOUNT=/var/log/nginx
LOG_IMAGE=/var/lib/healer/nginx-logs.img
LOG_SIZE_MB=512
PREFLIGHT_MIN_MB=25
REFERENCE=/opt/healer/reference
ROTATION_POLICY=/etc/logrotate.d/nginx-healer
# Audit logs deliberately do not end in .log, so the distribution's own nginx
# rotation policy (/var/log/nginx/*.log) cannot rotate them behind the
# experiment's back and change the result depending on timer timing.
AUDIT_LOG="$LOG_MOUNT/healer-access.audit"
SBIN=/usr/local/sbin
NGINX_CONF=/etc/nginx/conf.d/healer.conf

# A fresh instance is often still running cloud-init or unattended-upgrades,
# which hold the apt locks for a while after boot. Wait for them instead of
# failing on "Could not get lock" (seen on a template reset).
wait_for_apt () {
    cloud-init status --wait >/dev/null 2>&1 || true   # "degraded done" exits 2
    if command -v fuser >/dev/null; then
        for _ in $(seq 1 120); do
            fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
                  /var/lib/apt/lists/lock >/dev/null 2>&1 || return 0
            sleep 5
        done
        echo "apt is still locked after 10 minutes" >&2
        return 1
    fi
}
APT_WAIT="-o DPkg::Lock::Timeout=600"

echo "==> packages"
wait_for_apt
export DEBIAN_FRONTEND=noninteractive
apt-get $APT_WAIT update -qq
apt-get $APT_WAIT install -y -qq nginx logrotate curl findutils util-linux >/dev/null

echo "==> bounded log filesystem (${LOG_SIZE_MB} MiB at ${LOG_MOUNT})"
systemctl stop nginx || true
mkdir -p "$(dirname "$LOG_IMAGE")" "$LOG_MOUNT"

if [ "$(findmnt -no TARGET --target "$LOG_MOUNT")" != "$LOG_MOUNT" ]; then
    if [ ! -f "$LOG_IMAGE" ]; then
        fallocate -l "${LOG_SIZE_MB}M" "$LOG_IMAGE"
        mkfs.ext4 -q -F "$LOG_IMAGE"
    fi
    TMP=$(mktemp -d)
    cp -a "$LOG_MOUNT/." "$TMP/" 2>/dev/null || true
    mount -o loop,noatime "$LOG_IMAGE" "$LOG_MOUNT"
    cp -a "$TMP/." "$LOG_MOUNT/" 2>/dev/null || true
    rm -rf "$TMP"
    grep -q "$LOG_IMAGE" /etc/fstab || \
        echo "$LOG_IMAGE $LOG_MOUNT ext4 loop,noatime 0 0" >> /etc/fstab
fi
chown root:adm "$LOG_MOUNT"
chmod 755 "$LOG_MOUNT"

echo "==> nginx configuration and reference"
mkdir -p "$REFERENCE"
cat > "$REFERENCE/healer.conf" <<CONF
# Lab service. Deliberately simple: the subject is the infrastructure.
server {
    listen 80 default_server;
    server_name _;
    root /var/www/html;

    access_log $AUDIT_LOG;
    error_log  $LOG_MOUNT/healer-error.audit;

    location = /healthz {
        add_header Content-Type text/plain;
        return 200 "ok\\n";
    }
}
CONF
install -m 644 "$REFERENCE/healer.conf" /etc/nginx/conf.d/healer.conf
rm -f /etc/nginx/sites-enabled/default

echo "==> log rotation policy and reference"
cat > "$REFERENCE/nginx-healer.logrotate" <<ROTATE
$LOG_MOUNT/healer-*.audit {
    size 20M
    rotate 3
    missingok
    notifempty
    compress
    copytruncate
}
ROTATE
install -m 644 "$REFERENCE/nginx-healer.logrotate" "$ROTATION_POLICY"

# Rotation is size triggered, so it must be CHECKED often enough for the
# experiment's write rate. The distribution's daily timer is far too slow.
cat > /etc/systemd/system/healer-logrotate.service <<UNIT
[Unit]
Description=Frequent size-triggered rotation for the lab audit logs
ConditionPathExists=$ROTATION_POLICY
[Service]
Type=oneshot
ExecStart=/usr/sbin/logrotate $ROTATION_POLICY
UNIT

cat > /etc/systemd/system/healer-logrotate.timer <<'UNIT'
[Unit]
Description=Check lab audit log size frequently
[Timer]
OnBootSec=15s
OnUnitActiveSec=15s
AccuracySec=1s
[Install]
WantedBy=timers.target
UNIT

echo "==> host scripts (one shared fail-closed mount guard)"
# These live in the repository and are tested by tools/test_lab_host.sh, so the
# installer, the preflight and the fault generator all enforce exactly the same
# rule. A second, weaker copy of that rule is how a root-backed bind mount gets
# written to.
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lab-host
for script in healer-mount-guard healer-preflight healer-logflood; do
    [ -f "$SRC/$script" ] || { echo "missing $SRC/$script" >&2; exit 1; }
    install -m 755 "$SRC/$script" "/usr/local/sbin/$script"
done

cat > /etc/systemd/system/healer-lab.env <<ENV
HEALER_LOG_MOUNT=$LOG_MOUNT
HEALER_LOG_IMAGE=$LOG_IMAGE
HEALER_LOG_MAX_MB=1024
HEALER_PREFLIGHT_MIN_MB=$PREFLIGHT_MIN_MB
HEALER_ROTATION_POLICY=$ROTATION_POLICY
HEALER_AUDIT_LOG=$AUDIT_LOG
HEALER_GUARD=/usr/local/sbin/healer-mount-guard
ENV

mkdir -p /etc/systemd/system/nginx.service.d
cat > /etc/systemd/system/nginx.service.d/healer-preflight.conf <<'UNIT'
[Service]
EnvironmentFile=/etc/systemd/system/healer-lab.env
ExecStartPre=/usr/local/sbin/healer-preflight
UNIT

cat > /etc/systemd/system/healer-logflood.service <<'UNIT'
[Unit]
Description=Lab fault generator: fills the bounded log volume
[Service]
Type=oneshot
EnvironmentFile=/etc/systemd/system/healer-lab.env
ExecStart=/usr/local/sbin/healer-logflood
UNIT

cat > /etc/systemd/system/healer-logflood.timer <<'UNIT'
[Unit]
Description=Lab fault generator schedule
[Timer]
OnActiveSec=5s
OnUnitActiveSec=10s
AccuracySec=1s
[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl disable --now healer-logflood.timer 2>/dev/null || true
systemctl enable --now healer-logrotate.timer

echo "==> start nginx"
nginx -t
systemctl enable --now nginx
systemctl restart nginx

echo "==> verify the contract"
# BEGIN pre-proof gate
# tools/test_lab_host.sh extracts and runs this block with mocked system
# commands, so keep it self-contained between the markers.
fail=0
check () { if eval "$2"; then echo "   ok    $1"; else echo "   FAIL  $1"; fail=1; fi; }

# The producer exits 3 when it stands down. That is the expected answer here,
# so status and diagnostic are checked explicitly. A pipeline into grep under
# pipefail would turn the expected 3 into a failure, and "|| true" would also
# accept a guard refusal (2) or a write failure (4, 5).
producer_stands_down () {
    local out status=0
    out=$(HEALER_LOG_MOUNT="$LOG_MOUNT" HEALER_LOG_IMAGE="$LOG_IMAGE" \
          HEALER_LOG_MAX_MB=1024 HEALER_ROTATION_POLICY="$ROTATION_POLICY" \
          HEALER_AUDIT_LOG="$AUDIT_LOG" HEALER_GUARD="$SBIN/healer-mount-guard" \
          "$SBIN/healer-logflood" 2>&1) || status=$?
    if [ "$status" -ne 3 ]; then
        echo "         producer exited $status, expected 3: ${out:-no diagnostic}"
        return 1
    fi
    case "$out" in
        *"stands down"*) return 0 ;;
        *) echo "         producer exited 3 without the stand-down diagnostic"; return 1 ;;
    esac
}

check "nginx is active"  'systemctl is-active --quiet nginx'
check "health endpoint answers with the expected body" \
      'curl -fsS http://127.0.0.1/healthz | grep -qx ok'
check "log mount is dedicated"  \
      '[ "$(findmnt -no TARGET --target "$LOG_MOUNT")" = "$LOG_MOUNT" ]'
check "log mount is a separate device from root" \
      '[ "$(stat -c %d "$LOG_MOUNT")" != "$(stat -c %d /)" ]'
check "log mount is ext4"  \
      '[ "$(findmnt -no FSTYPE --target "$LOG_MOUNT")" = ext4 ]'
check "log mount is bounded below 1 GiB" \
      '[ "$(df -m --output=size "$LOG_MOUNT" | tail -1 | tr -d " ")" -lt 1024 ]'
check "live config matches reference" \
      'diff -q "$NGINX_CONF" "$REFERENCE/healer.conf" >/dev/null'
check "rotation reference present" '[ -f "$REFERENCE/nginx-healer.logrotate" ]'
check "frequent rotation timer active" 'systemctl is-active --quiet healer-logrotate.timer'
check "preflight is installed in the unit" \
      'systemctl show nginx -p ExecStartPre | grep -q healer-preflight'
check "fault generator present and off" \
      'test -x "$SBIN/healer-logflood" && ! systemctl is-active --quiet healer-logflood.timer'
check "fault generator stands down while the policy exists" 'producer_stands_down'

# Nothing destructive happens while any check above is failing. A failed device
# or capacity check is exactly the situation in which filling a volume is
# dangerous, so the proof is gated behind all of them.
if [ "$fail" -ne 0 ]; then
    echo "safety checks failed, refusing to run the fill proof" >&2
    exit 1
fi
# END pre-proof gate

echo "==> prove the failure mechanism, then undo it"
BALLAST="$LOG_MOUNT/preflight-proof.ballast"
cleanup () { rm -f "$BALLAST"; systemctl start nginx >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

/usr/local/sbin/healer-mount-guard "$LOG_MOUNT" "$LOG_IMAGE" 1024 ext4 >/dev/null \
    || { echo "mount guard refused immediately before the fill, aborting" >&2; exit 1; }

dd if=/dev/zero of="$BALLAST" bs=1M count="$LOG_SIZE_MB" 2>/dev/null || true

FREE=$(df -m --output=avail "$LOG_MOUNT" | tail -1 | tr -d ' ')
check "the volume is actually below the requirement (${FREE} MiB free)" \
      '[ "$FREE" -lt '"$PREFLIGHT_MIN_MB"' ]'

# the preflight itself must be what refuses, not some unrelated restart problem
if /usr/local/sbin/healer-preflight 2>/dev/null; then
    echo "   FAIL  the preflight passes on a full volume"; fail=1
else
    echo "   ok    the preflight refuses on a full volume"
fi

systemctl restart nginx >/dev/null 2>&1 || true
check "nginx is not running after the failed restart" \
      '! systemctl is-active --quiet nginx'
check "the journal names the preflight as the cause" \
      'journalctl -u nginx -n 40 --no-pager | grep -q "preflight failed"'
check "the health endpoint stops answering" \
      '! curl -fsS --max-time 5 http://127.0.0.1/healthz >/dev/null'

rm -f "$BALLAST"
systemctl restart nginx
check "service recovers once space is reclaimed" \
      'curl -fsS --max-time 5 http://127.0.0.1/healthz | grep -qx ok'

trap - EXIT INT TERM

if [ "$fail" -ne 0 ]; then
    echo "installer finished with failures, do not run experiments yet" >&2
    exit 1
fi
echo "==> lab host ready"
