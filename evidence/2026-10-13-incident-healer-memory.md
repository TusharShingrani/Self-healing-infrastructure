# Incident: the healer ran out of memory during experiment rep 3

Date: 2026-10-13. Written from the healer's journal (previous boot) and
sysstat (`/var/log/sysstat/sa13`), read after the reboot.

## What happened

| Time (UTC) | Event |
|---|---|
| 16:10 | Live A/B/C experiment `experiment-2026-10-13T161043Z` starts, three repetitions planned |
| 17:23:51 | Rep 3, config A, first run. Valid: restart fails, 180 s down, clean-up ok |
| 17:28:26 | The loop service is restarted from a second shell with `CS_URL` pasted as `CS_URL=...`. The adapter refuses it (`CS_URL must begin with https://`), the service restarts every 10 s |
| 17:28:59 | The service is restarted again with a correct `CS_URL`, config A |
| 17:30:45 | Memory available drops to about 10 MB. journald reports memory pressure, the metrics endpoint gets broken pipes |
| 17:31:13 | Rep 3 A repeat starts. `live_run.py` cannot read the loop's metrics and labels the run `loop-not-running` |
| 17:34:41 | The deliberate restart never reaches app-1: `ssh timed out`. Name resolution fails for the CloudStack API |
| 17:42 to 17:52 | Thrashing: about 7,000 major page faults per second, available memory under 2 MB. journald killed by its watchdog, the loop service killed on stop |
| 17:48 | app-1 reset and provisioned for rep 3 B (both succeeded, slowly) |
| 17:53 | `start_loop.sh start B` fails: `Reload daemon failed: Connection timed out`. The experiment stops |
| 17:55:47 | Power button from the console. A clean poweroff also times out |
| 17:57:47 | The healer boots again. The loop is not running (credentials were in memory only, as designed) |

sysstat, memory available (kB): 65,480 at 17:10, 43,652 at 17:20,
10,728 at 17:30, 596 at 17:42, 1,816 at 17:52.

## Cause

The healer has 1 GiB of memory and no swap. During the experiment it was
running the loop, the experiment, SSH sessions and an interactive Claude Code
session. After the reboot, the Claude Code process alone used about 350 MB.
That left no room for the page cache, and the machine thrashed instead of
invoking the OOM killer.

The loop itself is small (29 MB peak, from systemd's accounting at 17:28:27).

## Effect on the results

- Rep 3 A repeat (`evidence/runs/2026-10-13T173113Z-app-1-disk_leak-loop-not-running`)
  is invalid. The restart never happened, so its 0 s downtime says nothing
  about self-healing. It is excluded from `docs/results.md`.
- Rep 3 B and C never ran. The experiment has three valid repetitions for A
  and two for B and C.
- No lab instance was harmed. After the reboot app-1 and app-2 answered
  `/healthz` with `ok` and every Prometheus target was up except the loop's
  own metrics, which is correct while the loop is stopped.

## What was changed

- `tools/summarise_experiment.py` only counts a run if the loop that was
  actually running matches the block's configuration, and lists the runs it
  did not count with the reason. Tested in `tools/test_adapter.py`.
- `tools/live_experiment.py` stops the experiment as soon as a run reports a
  different loop configuration, rather than recording it.

## Not changed yet

The healer is still 1 GiB with no swap. Options are a swap file on the healer
or a larger offering, and in any case: do not run an interactive Claude Code
session on the healer while an experiment is running.
