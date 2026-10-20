# Hard restart versus targeted repair — 18 October 2026

> Historical release record. PR #15 supersedes the earlier UI descriptions. The current dashboard has four trend panels and seven queries. Live acceptance passed on 19 and 20 October 2026. Dated results below remain unchanged. See [current acceptance](validation.md#current-console-release--19-and-20-october-2026).


## Answer

In this controlled source-port exhaustion experiment, hard restarting HAProxy did **not** provide sustained client recovery under continuing load. Targeted capacity repair recovered in all three paired trials, without interrupting requests that were already pending. This supports choosing the targeted action for this particular diagnosed constraint; it does not establish universal superiority over restarting or justify an entire platform solely to correct a known static setting.

## Protocol

Three pairs, ordered restart/repair, repair/restart, restart/repair. Each trial began with a healthy idle gateway and namespace range 40000-40031. The same independent VM ran 64 retrying load workers for 24 seconds. Both actions followed the same controller-confirmed exhaustion signature, with no deliberate approval delay. The load process and the independent nonce-checking client continued during the action.

- Restart: administrator hard restart of only platform-gateway.service. Effective SIGTERM (15) semantics were checked, the PID changed, and the namespace range stayed at 32 port numbers. No VM, Kubernetes node or upstream was restarted.
- Repair: scripted operator approval through the existing API for the bounded namespace expansion to 256 port numbers. Gateway identity stayed unchanged. This compares repair actions, not human reaction time or a new autonomous restart capability.
- Recovery: first of three consecutive successful independent HTTP checks after the action trigger and before load shutdown. Outcomes are measured by the separate client, not by whether the healer accepts a changed PID.
- Interruption: a request sent before intervention returned a transport error before planned load shutdown. Planned cancellation, HTTP error responses and requests first sent after intervention are excluded from this count.

## Results (qualification excluded)

| Treatment | Sustained recoveries under load | Failed independent client checks | Median recovery after action trigger | Pre-existing test requests interrupted |
|---|---:|---:|---:|---:|
| Hard restart | 0/3 | 63/63 | None observed | 96 total (32 per trial) |
| Targeted repair | 3/3 | 17/64 | 4.213 s | 0 |

Repair recovery intervals after the trigger were 4.229, 4.032 and 4.213 seconds. None of those trials showed a subsequent independent-client failure after sustained recovery while load continued. All recorded independent client checks in the restart trials failed. The restart control request returned in a median 0.284 seconds including SSH/unit management, but that was not recovered service. Each restart had at least 20.3 seconds of continuing load after the control request returned. Timing of the approval response is not the time the kernel mutation completed; compare the common trigger-to-client-recovery metric.

Per-trial numeric data are in [restart-comparison.json](restart-comparison.json). Detailed timelines and histories remain private on the laptop.

## Interpretation and fairness

Restarting replaced the process but did not enlarge its namespace's source-port pool. Expanding the pool restored real independent requests while the same bounded connection demand continued. That is the measured operational advantage here: successful forwarding with less disruption, not merely a fast control command or a green process status.

The restart intentionally invalidated the healer's process pin. This does **not** block HAProxy forwarding: the independent client connects directly to the gateway and remained the outcome measure. Repinning happened only after each restart trial's load had drained. Post-restart kernel errors were not attributed individually through the stale pinned agent; the confirmed pre-action signature, unchanged range and independent HTTP outcomes are the evidence. Extra identity maintenance time is excluded from recovery comparisons.

An additional reviewed repair occurrence qualified the final process scope alongside its last comparison repair. The operator explicitly promoted that scope and restored automatic mode. This qualification occurrence is excluded from the table. Final acceptance passed 11 healthy scrape targets, all 12 dashboard queries, baseline rollback and current scoped automatic eligibility. Private recovery archives were refreshed and copied off-platform.

## Limits and assessor conclusion

This is a small, single-environment, alternating-order comparison, not a statistical or production-capacity claim. Remaining TIME_WAIT and environmental variation can differ despite baseline checks. The pool is deliberately small and backend reuse disabled. The 25-second held GETs maintain pressure through the 24-second test window and are cancelled at its end; their completion is not demonstrated and their interruption is not evidence of financial loss. Useful recovery is demonstrated separately by nonce HTTP requests. One-second probes cannot rule out a brief unsampled recovery. No sustained restart recovery was observed within the bounded follow-up, rather than proved impossible forever.

Graceful reload, redundant load balancers, admission control and better connection pooling were not compared. Correct static capacity configuration is still the simpler choice when the required limit is already known. The result supports diagnosis, bounded runtime adaptation and verification for this fault; it does not prove that every service needs this healer or that restarting is always wrong.
