# Review of selfheal-educloud(4)

> **Historical.** An external review of an early snapshot, before the lab was
> built. Both gaps below have since been fixed, with tests:
> `tools/install_lab_host.sh` checks the producer's stand-down status and
> diagnostic explicitly (`producer_stands_down`), and
> `tools/lab-host/healer-preflight` refuses a failed, empty or non-numeric
> free-space reading and an invalid threshold. `tools/test_lab_host.sh` covers
> both. The installer, fresh deployment and fill proof have since been run live
> (`evidence/`). Test counts below are from that snapshot.

Reviewed C:\Users\tusha\Downloads\selfheal-educloud(4)\selfheal. Source unchanged; no live EduCloud changes.

19 host-script tests, 38 adapter tests, and 18 safety tests passed: 75 in total. The simulation still reproduces A 20/40, B 1/1, C 1/0 first/repeat disk-fault downtime ticks. Windows test temporary files and host-registry defaults were redirected into the workspace. Installer shell syntax passes.

The four previous fixes are present: stdout/stderr ordering preserves dd's errors; production HTTP probing uses exact trimmed body equality; the fill proof is gated and checks the preflight/outage/recovery sequence; host scripts share the loop-image mount validator.

## Two reproduced integration gaps

### P1: Expected stand-down prevents installer completion

tools/lab-host/healer-logflood deliberately returns exit 3 when the rotation policy exists. tools/install_lab_host.sh:211-212 checks that path using `healer-logflood 2>&1 | grep -q "stands down"`, with pipefail enabled. Although grep succeeds, the producer's exit 3 makes the pipeline fail. The installer sets fail=1 and exits at its safety gate, before the fill proof. This occurs in the intended fresh-host configuration because the installer has just installed the policy.

Reproduction with the same pipeline and a mocked producer: pipeline status 3, installer check FAIL. The host tests assert exit 3 correctly but do not run the installer check that consumes it.

Fix: capture both output and status explicitly, then require status exactly 3 and the stand-down diagnostic. Do not append a blanket `|| true`, since that could accept real guard/write failures. Add an installer integration test covering the complete healthy pre-proof gate.

### P2: Unreadable free space makes the preflight pass

tools/lab-host/healer-preflight:21-22 does not check the df pipeline's status or validate that FREE and MIN_MB are numeric. With FREE=not-a-number, the integer comparison errors; because it occurs in an if condition and the script does not explicitly refuse it, the script exits 0. This violates the declared fail-closed startup requirement.

Reproduced against the actual healer-preflight script with a passing mocked mount guard and df returning an unreadable free-space value: diagnostic 'integer expression expected', exit 0.

Fix: refuse an unsuccessful df pipeline, empty or nonnumeric output, and invalid/negative thresholds before the comparison. Add tests for malformed output, command failure with plausible partial stdout, empty output, and the exact 25 MiB boundary. A required measurement failure must prevent service start.

## Evidence boundary

The installer, fresh app-1 deployment, adapter's live API operations, the manual flood/restart outage, and recovery timing remain untested. Capture those results off-platform after correcting the deterministic installer gate failure. Passing individual script tests does not prove their integration in the installer.
