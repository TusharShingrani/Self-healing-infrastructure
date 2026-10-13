#!/usr/bin/env bash
# Tests the host scripts themselves, with mocked system commands.
#
# These are the scripts that decide whether anything destructive may happen on
# a lab instance, so they are tested rather than assumed. Nothing here touches
# a real mount, and no real volume is written.
#
# Run:  bash tools/test_lab_host.sh

set -uo pipefail
export LC_ALL=C

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPTS="$HERE/lab-host"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

passed=0
failed=0

check () {
    if [ "$2" = "$3" ]; then
        printf '  PASS  %s\n' "$1"
        passed=$((passed + 1))
    else
        printf '  FAIL  %s (expected %s, got %s)\n' "$1" "$3" "$2"
        failed=$((failed + 1))
    fi
}

# ---------------------------------------------------------------- mock setup

MOCKS="$WORK/bin"
mkdir -p "$MOCKS"
export PATH="$MOCKS:$PATH"

# findmnt and stat answer from files the tests write, so each case is explicit
cat > "$MOCKS/findmnt" <<'MOCK'
#!/usr/bin/env bash
# args end with: --target <path>
TARGET_PATH=${@: -1}
FIELDS=""
for a in "$@"; do case "$a" in TARGET*|SOURCE|FSTYPE|SIZE) FIELDS=$a;; esac; done
KEY=root; [ "$TARGET_PATH" != "/" ] && KEY=mount
case "$FIELDS" in
    TARGET,SOURCE,FSTYPE,SIZE) cat "$MOCK_STATE/${KEY}.all" ;;
    TARGET) cut -d' ' -f1 "$MOCK_STATE/${KEY}.all" ;;
    SOURCE) cut -d' ' -f2 "$MOCK_STATE/${KEY}.all" ;;
    FSTYPE) cut -d' ' -f3 "$MOCK_STATE/${KEY}.all" ;;
    SIZE)   cut -d' ' -f4 "$MOCK_STATE/${KEY}.all" ;;
esac
MOCK

cat > "$MOCKS/stat" <<'MOCK'
#!/usr/bin/env bash
TARGET_PATH=${@: -1}
if [ "$TARGET_PATH" = "/" ]; then cat "$MOCK_STATE/root.dev"; else cat "$MOCK_STATE/mount.dev"; fi
MOCK

cat > "$MOCKS/losetup" <<'MOCK'
#!/usr/bin/env bash
cat "$MOCK_STATE/backing" 2>/dev/null
MOCK

# df: "free" holds MiB, scaled to bytes for -B1. "df.raw" replaces the output
# verbatim and "df.status" sets the exit code, for malformed and failed reads.
cat > "$MOCKS/df" <<'MOCK'
#!/usr/bin/env bash
if [ -f "$MOCK_STATE/df.raw" ]; then
    cat "$MOCK_STATE/df.raw"
else
    case " $* " in
        *"--output=size"*) echo "1M-blocks"; echo 512 ;;
        *" -B1 "*) echo "Avail"; echo $(( $(cat "$MOCK_STATE/free") * 1048576 + ${MOCK_FREE_EXTRA_BYTES:-0} )) ;;
        *) echo "Avail"; cat "$MOCK_STATE/free" ;;
    esac
fi
exit "$(cat "$MOCK_STATE/df.status" 2>/dev/null || echo 0)"
MOCK

chmod +x "$MOCKS"/*

export MOCK_STATE="$WORK/state"
mkdir -p "$MOCK_STATE"

good_mount () {
    echo "/var/log/nginx /dev/loop0 ext4 $((512 * 1024 * 1024))" > "$MOCK_STATE/mount.all"
    echo "/ /dev/vda1 ext4 $((10 * 1024 * 1024 * 1024))" > "$MOCK_STATE/root.all"
    echo 2305 > "$MOCK_STATE/mount.dev"
    echo 2049 > "$MOCK_STATE/root.dev"
    echo "/var/lib/healer/nginx-logs.img" > "$MOCK_STATE/backing"
    echo 400 > "$MOCK_STATE/free"
    rm -f "$MOCK_STATE/df.raw" "$MOCK_STATE/df.status"
    unset MOCK_FREE_EXTRA_BYTES
}

GUARD="$SCRIPTS/healer-mount-guard"
IMAGE=/var/lib/healer/nginx-logs.img

echo "Host script tests"
echo
echo "mount guard"

good_mount
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "accepts the expected bounded loop volume" $? 0

good_mount; echo "/ /dev/loop0 ext4 $((512 * 1024 * 1024))" > "$MOCK_STATE/mount.all"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses a path that is not its own mount point" $? 1

good_mount; echo 2049 > "$MOCK_STATE/mount.dev"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses a bind mount sharing root's device" $? 1

good_mount; echo "/var/log/nginx /dev/vda1 ext4 $((512 * 1024 * 1024))" > "$MOCK_STATE/mount.all"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses a volume backed by root's source" $? 1

good_mount; echo "/var/log/nginx /dev/loop0 tmpfs $((512 * 1024 * 1024))" > "$MOCK_STATE/mount.all"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses the wrong filesystem type" $? 1

good_mount; echo "/var/log/nginx /dev/loop0 ext4 $((200 * 1024 * 1024 * 1024))" > "$MOCK_STATE/mount.all"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses a volume above the permitted bound" $? 1

good_mount; echo "/var/lib/healer/SOMETHING-ELSE.img" > "$MOCK_STATE/backing"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses a volume backed by an unexpected image" $? 1

good_mount; : > "$MOCK_STATE/backing"
"$GUARD" /var/log/nginx "$IMAGE" 1024 ext4 >/dev/null 2>&1
check "refuses a volume that is not loop backed" $? 1

echo
echo "preflight"

export HEALER_GUARD="$GUARD" HEALER_LOG_MOUNT=/var/log/nginx \
       HEALER_LOG_IMAGE="$IMAGE" HEALER_LOG_MAX_MB=1024

good_mount; echo 400 > "$MOCK_STATE/free"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "passes with ample free space" $? 0

good_mount; echo 3 > "$MOCK_STATE/free"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails when free space is below the requirement" $? 1

good_mount; echo 2049 > "$MOCK_STATE/mount.dev"; echo 400 > "$MOCK_STATE/free"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails when the mount guard refuses, whatever the free space" $? 1

good_mount; echo 25 > "$MOCK_STATE/free"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "passes with exactly 25 MiB free" $? 0

good_mount; echo 25 > "$MOCK_STATE/free"; export MOCK_FREE_EXTRA_BYTES=-1
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails one byte below 25 MiB" $? 1

good_mount; echo 24 > "$MOCK_STATE/free"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails with 24 MiB free" $? 1

good_mount; printf 'Avail\nnot-a-number\n' > "$MOCK_STATE/df.raw"
OUT=$("$SCRIPTS/healer-preflight" 2>&1); R=$?
check "fails on a nonnumeric free-space reading" $R 1
case "$OUT" in *"preflight failed"*) R=0 ;; *) R=1 ;; esac
check "a nonnumeric reading is refused by name, not by a test error" $R 0

good_mount; : > "$MOCK_STATE/df.raw"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails on empty df output" $? 1

good_mount; printf 'Avail\n' > "$MOCK_STATE/df.raw"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails on a header with no reading" $? 1

good_mount; printf 'Avail\n%s\n' $((400 * 1048576)) > "$MOCK_STATE/df.raw"; echo 1 > "$MOCK_STATE/df.status"
"$SCRIPTS/healer-preflight" >/dev/null 2>&1
check "fails when df fails, even with a plausible reading" $? 1

for bad in abc -5 0 "" 2.5; do
    good_mount
    HEALER_PREFLIGHT_MIN_MB="$bad" "$SCRIPTS/healer-preflight" >/dev/null 2>&1
    check "fails on an invalid threshold '${bad}'" $? 1
done
good_mount

echo
echo "fault generator"

good_mount
AUDIT="$WORK/healer-access.audit"
POLICY="$WORK/nginx-healer.logrotate"
export HEALER_AUDIT_LOG="$AUDIT" HEALER_ROTATION_POLICY="$POLICY" HEALER_CHUNK_MB=1
: > "$AUDIT"

# dd mock: behaviour comes from DD_MODE
cat > "$MOCKS/dd" <<'MOCK'
#!/usr/bin/env bash
case "${DD_MODE:-ok}" in
    ok)       head -c 1024 /dev/zero; exit 0 ;;
    enospc)   echo "dd: error writing '/dev/stdout': No space left on device" >&2; exit 1 ;;
    eacces)   echo "dd: failed to open '/dev/stdout': Permission denied" >&2; exit 1 ;;
    eio)      echo "dd: error writing '/dev/stdout': Input/output error" >&2; exit 1 ;;
esac
MOCK
chmod +x "$MOCKS/dd"

rm -f "$POLICY"
DD_MODE=ok "$SCRIPTS/healer-logflood" >/dev/null 2>&1
check "a successful write exits 0" $? 0

DD_MODE=enospc "$SCRIPTS/healer-logflood" >/dev/null 2>&1
check "a full volume is the intended outcome, exits 0" $? 0

OUT=$(DD_MODE=enospc "$SCRIPTS/healer-logflood" 2>&1 >/dev/null)
case "$OUT" in *"intended fault condition"*) R=0 ;; *) R=1 ;; esac
check "a full volume is reported as intended, with a diagnostic" "$R" 0

DD_MODE=eacces "$SCRIPTS/healer-logflood" >/dev/null 2>&1
check "a permission failure is reported distinctly, exits 5" $? 5

OUT=$(DD_MODE=eacces "$SCRIPTS/healer-logflood" 2>&1 >/dev/null)
case "$OUT" in *"Permission denied"*) R=0 ;; *) R=1 ;; esac
check "the permission diagnostic survives to the classifier" "$R" 0

DD_MODE=eio "$SCRIPTS/healer-logflood" >/dev/null 2>&1
check "an unrelated I/O failure exits 5" $? 5

touch "$POLICY"
DD_MODE=ok "$SCRIPTS/healer-logflood" >/dev/null 2>&1
check "the producer stands down while the rotation policy exists" $? 3
rm -f "$POLICY"

echo 2049 > "$MOCK_STATE/mount.dev"
DD_MODE=ok "$SCRIPTS/healer-logflood" >/dev/null 2>&1
check "the producer refuses a target the mount guard rejects" $? 2

echo
echo "installer pre-proof gate"

# The gate is extracted from the installer itself and run with mocked system
# commands, against the real mount guard and the real producer. Passing script
# tests alone did not show that the installer consumed exit 3 correctly.
GATE="$WORK/gate.sh"
sed -n '/^# BEGIN pre-proof gate$/,/^# END pre-proof gate$/p' \
    "$HERE/install_lab_host.sh" > "$GATE"
[ -s "$GATE" ] || { echo "  FAIL  could not extract the gate from the installer"; failed=$((failed + 1)); }

SBIN_T="$WORK/sbin"; REF_T="$WORK/reference"
mkdir -p "$SBIN_T" "$REF_T"
cp "$SCRIPTS/healer-mount-guard" "$SCRIPTS/healer-logflood" "$SBIN_T/"
echo "server {}" > "$REF_T/healer.conf"; cp "$REF_T/healer.conf" "$WORK/healer.conf"
touch "$REF_T/nginx-healer.logrotate"

cat > "$MOCKS/systemctl" <<'MOCK'
#!/usr/bin/env bash
case "$*" in
    "is-active --quiet nginx"|"is-active --quiet healer-logrotate.timer") exit 0 ;;
    "is-active --quiet healer-logflood.timer") exit 3 ;;
    "show nginx -p ExecStartPre") echo "ExecStartPre={ path=/usr/local/sbin/healer-preflight }" ;;
    *) exit 1 ;;
esac
MOCK
cat > "$MOCKS/curl" <<'MOCK'
#!/usr/bin/env bash
echo ok
MOCK
chmod +x "$MOCKS/systemctl" "$MOCKS/curl"

run_gate () {
    LOG_MOUNT=/var/log/nginx LOG_IMAGE="$IMAGE" ROTATION_POLICY="$POLICY" \
    AUDIT_LOG="$AUDIT" SBIN="$SBIN_T" REFERENCE="$REF_T" NGINX_CONF="$WORK/healer.conf" \
    bash -c 'set -euo pipefail; export LC_ALL=C; source "$1"; echo GATE_OPEN' _ "$GATE" 2>&1
}

good_mount; touch "$POLICY"; : > "$AUDIT"
OUT=$(run_gate); R=$?
check "a healthy fresh host passes the whole gate" "$R" 0
case "$OUT" in *GATE_OPEN*) R=0 ;; *) R=1 ;; esac
check "the expected stand-down opens the gate" "$R" 0
[ -s "$AUDIT" ] && R=1 || R=0
check "the gate check does not write to the audit log" "$R" 0

good_mount; touch "$POLICY"; echo 2049 > "$MOCK_STATE/mount.dev"
OUT=$(run_gate); R=$?
check "a guard refusal (exit 2) keeps the gate shut" "$R" 1
case "$OUT" in *"producer exited 2"*) R=0 ;; *) R=1 ;; esac
check "the gate reports the producer's real status" "$R" 0

good_mount; rm -f "$POLICY"; printf '#!/bin/sh\nexit 3\n' > "$SBIN_T/healer-logflood"
run_gate >/dev/null; R=$?
check "exit 3 without the stand-down diagnostic keeps the gate shut" "$R" 1

printf '#!/bin/sh\necho "rotation policy present, producer stands down" >&2; exit 5\n' > "$SBIN_T/healer-logflood"
run_gate >/dev/null; R=$?
check "the stand-down text with a failure status keeps the gate shut" "$R" 1
cp "$SCRIPTS/healer-logflood" "$SBIN_T/"

echo
printf '%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
