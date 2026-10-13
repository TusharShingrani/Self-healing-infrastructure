# Results: live A/B/C experiment on EduCloud

Source: `evidence/experiment-2026-10-13T161043Z/results.csv`, 13 valid fault runs of 14 recorded. Repetitions with at least one valid run per configuration: A: 3, B: 2, C: 2.

Not every configuration has the same number of repetitions: the experiment stopped before it finished. The experiment log in the source folder records where, and the runs not counted are listed below.

Protocol per block (one configuration, one repetition): app-1 is reset to a fresh instance from the clean template and provisioned, Knowledge starts empty, the loop starts in that configuration, then the disk fault is injected twice (first occurrence, then repeat). In every run the deliberate maintenance restart happens 150 s after injection, whatever the loop is doing. Downtime is measured by the experiment itself, one request to `/healthz` per second, not by the loop.

## Downtime per configuration

| Config | Occurrence | Downtime | Ended down | Prevented | Healed | First loop action after injection | Peak log volume use |
|---|---|---|---|---|---|---|---|
| A | first | 180.0 s (min 180, max 180) | 3/3 | 0/3 | 0/3 | n/a | 100.0 % (min 100, max 100) |
| A | repeat | 180.0 s (min 180, max 180) | 2/2 | 0/2 | 0/2 | n/a | 100.0 % (min 100, max 100) |
| B | first | 9.0 s (min 4, max 14) | 0/2 | 0/2 | 2/2 | 159.4 s (min 154.5, max 164.4) | 100.0 % (min 100, max 100) |
| B | repeat | 15.5 s (min 11, max 20) | 0/2 | 0/2 | 2/2 | 166.9 s (min 162.4, max 171.3) | 100.0 % (min 100, max 100) |
| C | first | 9.0 s (min 3, max 15) | 0/2 | 0/2 | 2/2 | 161.6 s (min 155.1, max 168) | 100.0 % (min 100, max 100) |
| C | repeat | 0.0 s (min 0, max 0) | 0/2 | 2/2 | 0/2 | 131.9 s (min 131.2, max 132.7) | 100.0 % (min 100, max 100) |

In config A the service stays down until the experiment's own clean-up at the end of the measurement window, so its downtime is bounded by the window, not by any recovery.

## Runs not counted

- rep 3 config A repeat: loop was 'loop-not-running' during the run, not config A ([2026-10-13T173113Z-app-1-disk_leak-loop-not-running](../evidence/runs/2026-10-13T173113Z-app-1-disk_leak-loop-not-running))

## Fresh-instance reset (template)

- Template rebuild until SSH answers: 54.8 s (min 48.5, max 61.8)
- Provisioning (installer with fill proof, exporters): 41.3 s (min 34.3, max 46.6)
- Total per reset: 96.0 s (min 91.1, max 101.3)

## Every run

| Rep | Config | Occurrence | Downtime (s) | Restart ok | Prevented | Healed | Counted | Run folder |
|---|---|---|---|---|---|---|---|---|
| 1 | A | first | 180 | False | False | False | yes | [2026-10-13T161308Z-app-1-disk_leak-A](../evidence/runs/2026-10-13T161308Z-app-1-disk_leak-A) |
| 1 | A | repeat | 180 | False | False | False | yes | [2026-10-13T161925Z-app-1-disk_leak-A](../evidence/runs/2026-10-13T161925Z-app-1-disk_leak-A) |
| 1 | B | first | 14 | False | False | True | yes | [2026-10-13T162759Z-app-1-disk_leak-B](../evidence/runs/2026-10-13T162759Z-app-1-disk_leak-B) |
| 1 | B | repeat | 20 | False | False | True | yes | [2026-10-13T163202Z-app-1-disk_leak-B](../evidence/runs/2026-10-13T163202Z-app-1-disk_leak-B) |
| 1 | C | first | 3 | False | False | True | yes | [2026-10-13T163829Z-app-1-disk_leak-C](../evidence/runs/2026-10-13T163829Z-app-1-disk_leak-C) |
| 1 | C | repeat | 0 | True | True | False | yes | [2026-10-13T164222Z-app-1-disk_leak-C](../evidence/runs/2026-10-13T164222Z-app-1-disk_leak-C) |
| 2 | A | first | 180 | False | False | False | yes | [2026-10-13T164837Z-app-1-disk_leak-A](../evidence/runs/2026-10-13T164837Z-app-1-disk_leak-A) |
| 2 | A | repeat | 180 | False | False | False | yes | [2026-10-13T165454Z-app-1-disk_leak-A](../evidence/runs/2026-10-13T165454Z-app-1-disk_leak-A) |
| 2 | B | first | 4 | False | False | True | yes | [2026-10-13T170330Z-app-1-disk_leak-B](../evidence/runs/2026-10-13T170330Z-app-1-disk_leak-B) |
| 2 | B | repeat | 11 | False | False | True | yes | [2026-10-13T170723Z-app-1-disk_leak-B](../evidence/runs/2026-10-13T170723Z-app-1-disk_leak-B) |
| 2 | C | first | 15 | False | False | True | yes | [2026-10-13T171337Z-app-1-disk_leak-C](../evidence/runs/2026-10-13T171337Z-app-1-disk_leak-C) |
| 2 | C | repeat | 0 | True | True | False | yes | [2026-10-13T171744Z-app-1-disk_leak-C](../evidence/runs/2026-10-13T171744Z-app-1-disk_leak-C) |
| 3 | A | first | 180 | False | False | False | yes | [2026-10-13T172351Z-app-1-disk_leak-A](../evidence/runs/2026-10-13T172351Z-app-1-disk_leak-A) |
| 3 | A | repeat | 0 | False | False | False | no | [2026-10-13T173113Z-app-1-disk_leak-loop-not-running](../evidence/runs/2026-10-13T173113Z-app-1-disk_leak-loop-not-running) |
