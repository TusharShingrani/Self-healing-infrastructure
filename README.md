# Self-healing infrastructure with a MAPE-K loop

A graduation project (HBO ICT, Fontys). Infrastructure on Fontys EduCloud that
detects a failure, repairs the cause rather than the symptom, verifies the
repair, and learns verified procedures for later recovery. Prevention is measured
separately where an early warning is available.

The loop follows the MAPE-K reference model (Kephart and Chess, 2003):
Monitor, Analyse, Plan, Execute, over shared Knowledge. Every stage is a
separate piece of code, every stage is visible in Grafana, and every claim in
the results below comes from a measured live run on EduCloud, not from the
simulation.

**Broader infrastructure:** [DNS, Redis, permissions and investigated learning](docs/infrastructure-lab.md).
[Research synthesis answering all four subquestions](docs/research-synthesis.md).
The new dependency loop has separate state and a read-only Grafana dashboard.
[Measured outcomes and retained implementation findings](evidence/infrastructure-validation-2026-10-14.md).

**Current operator workflow:** [incident diagnosis, human repairs and validated procedures](docs/operator-workflow.md).
New live repairs now require incident approval until a narrowly scoped procedure
has two verified successes and explicit promotion. Earlier demo and A/B/C
results describe the previous execution policy.

**Try it yourself:** [guided live demo and approval walkthrough](docs/live-demo.md).
The 14 October demo includes a live cross-instance prevention result and a
rate-limit pacing finding; [raw demo account](evidence/live-demo-2026-10-14.md).

**Documents:** [context report: the problem and the failure scenarios](docs/context-report.md)
Ãƒâ€šÃ‚Â· [architecture and design: network, MAPE-K, learning, design decisions](docs/architecture.md)
Ãƒâ€šÃ‚Â· [results](docs/results.md) Ãƒâ€šÃ‚Â· [design notes](docs/design-notes.md)
Ãƒâ€šÃ‚Â· [healer handover: connections, backup, replacing or resizing the healer](docs/healer-handover.md)

## What runs where

```mermaid
flowchart LR
    laptop([Laptop]) -- "VPN + SSH via gateway" --> healer
    subgraph EduCloud project healer-lab, isolated network 10.1.1.0/24
        healer["healer-ubuntu 10.1.1.205<br/>MAPE-K loop service<br/>Knowledge (SQLite)<br/>LLM advisor (optional)<br/>metrics :9105"]
        monitor["monitor 10.1.1.50<br/>Prometheus :9090<br/>blackbox /healthz probe<br/>Grafana :3000"]
        app1["app-1 10.1.1.60<br/>nginx + bounded log volume<br/>node / nginx exporters"]
        app2["app-2 10.1.1.61<br/>nginx + bounded log volume<br/>node / nginx exporters"]
        monitor -- scrape --> app1 & app2 & healer
        healer -- "M: PromQL" --> monitor
        healer -- "E: SSH effectors<br/>verify with direct probes" --> app1 & app2
    end
    healer -- "platform actions (reboot, rebuild)" --> api[(CloudStack API)]
```

| Instance | Role | Size |
|---|---|---|
| healer-ubuntu | Runs the loop, this repository, the evidence | 2 CPUs, 6 GiB |
| monitor | Prometheus, blackbox exporter, Grafana | 1 CPU, 4 GiB |
| app-1, app-2 | The managed infrastructure: nginx serving `/healthz` | 1 CPU, 1 GiB |

Only the healer has a port forward. The app instances and the monitor are
reached over the isolated network. All four are deployed from one private
template, at fixed addresses, by `tools/lab.py`.

## The MAPE-K loop, stage by stage

| Stage | Code | What it does here |
|---|---|---|
| **Monitor** | `mapek/prometheus.py`, `stages.Monitor` | Reads fresh Prometheus series per node (availability from the blackbox probe, nginx unit state, log volume use and its growth rate, config correctness) and names symptoms. A missing, stale or pre-action sample is not used; that field falls back to a direct SSH probe. A failed probe is unknown, never healthy |
| **Analyse** | `stages.RuleAnalyser` | Turns symptoms into a cause. Knowledge is asked first (a symptom set seen before), then rules from most to least specific, then human-approved LLM advice |
| **Plan** | `stages.Planner` | Picks actions from a fixed catalogue (`mapek/actions.py`) by escalation level: guest repair, then reboot, then rebuild. The planner cannot invent a command |
| **Execute** | `stages.Executor`, `mapek/loop.py` | Checks guardrails (cool-down, rate limit) and the approval gate for high-risk actions, runs the actions over SSH, then **verifies with direct probes**. A repair that does not verify escalates |
| **Knowledge** | `mapek/knowledge.py` | SQLite shared by every node: incidents, learned prevention rules, LLM advice and human decisions |

The whole loop is `Healer.tick()` in `mapek/loop.py`, about thirty lines, with
the stages marked. `tools/healer_service.py` runs one loop per app instance
every 10 seconds and publishes what each stage did as metrics.

### How it learns

When an incident is resolved, Knowledge stores the symptoms that were present
**before** the failure (the early signs) and the actions that fixed the cause.
That becomes a prevention rule. The next time those early signs appear, the
loop runs the rule while the service is still healthy, so the failure never
happens. Knowledge is shared, so a rule learned on app-1 protects app-2.

For the disk fault the chain is:

```
fault    the log rotation policy is removed, a producer fills the log volume
error    the bounded 512 MiB log volume fills up
failure  the next deliberate restart fails its storage preflight, nginx stops
```

Restarting nginx treats the failure. Clearing the volume treats the error. Only
restoring rotation treats the fault. The learned rule acts at the error stage,
on the early sign `disk_growing_fast`, with `clear_logs` and
`fix_log_rotation`.

The preflight is a declared lab protocol: stock nginx does not refuse to start
on a full log volume. See `docs/design-notes.md` for why, and how it is proven
on every fresh instance.

### Three configurations

| Config | Has | Question it answers |
|---|---|---|
| A | Monitor and record only | The baseline |
| B | Detect, diagnose, repair, verify, escalate | What is reactive self-healing worth? |
| C | B plus Knowledge: recall, prevention, approved advice | Does learning help? |

### The LLM advisor, a human in the loop (optional)

When the loop is stuck (no rule matches, a repair does not verify, or every
escalation level is used up) it asks `mapek/advisor.py` for advice. The
advisor asks Google Gemini (free tier, default model `gemini-3.5-flash-lite`,
override with `HEALER_GEMINI_MODEL`) for a cause and a plan. Gemini's
structured output (`responseSchema`) restricts the actions to the catalogue,
and the loop checks them again. The advice is stored as **pending**. Nothing runs.

A person reviews it:

```bash
python3 tools/knowledge.py advice pending
python3 tools/knowledge.py approve-advice 3      # or reject-advice 3
```

Approved advice becomes a diagnosis the loop may use the next time the same
symptoms appear, still through the guardrails and the high-risk approval gate.
Without a key, requests are still recorded, so a person sees that the loop
needed help. To turn it on, get a free key from Google AI Studio and, on the
healer:

```bash
export GEMINI_API_KEY=...                  # never in a file in this repository
bash tools/start_loop.sh start C           # passes the key to the service in memory
```

The Gemini call uses the REST API with the Python standard library, so there
is nothing to install. On the free tier Google may use prompts to improve its
products; the prompt holds symptoms and lab metrics only, never credentials.

## Watching it work

Grafana runs on the monitor and is only reachable inside the project network.
Tunnel through the healer from the laptop:

```bash
ssh -L 3000:10.1.1.50:3000 <your usual healer login>
# then open http://localhost:3000  (anonymous read-only; admin password:
#   ssh to the monitor and run: sudo cat /etc/grafana/admin-password)
```

The dashboard "Self-healing infrastructure (MAPE-K)" is laid out along the
loop: availability, what Monitor sees, the current diagnosis and escalation
level, actions executed, time spent in each stage, and what Knowledge has
learned. Every loop event is an annotation on the graphs.

On the healer:

```bash
bash tools/start_loop.sh status | logs
python3 tools/knowledge.py events 20      # the loop's own story
python3 tools/knowledge.py incidents
python3 tools/knowledge.py rules
```

## Running a fault by hand

```bash
python3 tools/live_run.py app-1 disk_leak       # also: config_drift, service_stop
```

`live_run.py` is the experimenter, not the healer. It injects the fault,
performs the maintenance restart at a fixed time whatever the loop does, and
measures `/healthz` itself every second. Results go to `evidence/runs/`.

## Results

See [`docs/results.md`](docs/results.md) for the live A/B/C experiment, with
every number traceable to a run folder under `evidence/`.

## Rebuilding the lab from nothing

Credentials come from the environment, never from a file:

```bash
export CS_URL=https://educloud.fontysict.nl/client/api   # not secret
export CS_KEY=...  CS_SECRET=...                          # secret
export LAB_SSH_KEY=~/.ssh/healer-lab-key                  # keypair healer-lab-key2

python3 tools/lab.py status
python3 tools/lab.py deploy app-1 && bash tools/provision.sh app 10.1.1.60 evidence/provision-app-1.log
python3 tools/lab.py deploy app-2 && bash tools/provision.sh app 10.1.1.61 evidence/provision-app-2.log
python3 tools/lab.py deploy monitor && bash tools/provision.sh monitor 10.1.1.50 evidence/provision-monitor.log
bash tools/start_loop.sh start C
```

A fresh app instance from the template is ready in about a minute, and
provisioned (packages, bounded volume, fail-closed checks, a real fill proof,
exporters) in under 40 seconds.

## Safety rules the code enforces

- Destructive platform actions only target names in `lab_instances`, never the
  healer or the monitor, and only after the instance's `projectid` is
  positively matched. Missing metadata fails closed.
- `reboot_instance` and `rebuild_instance` need explicit approval
  (`touch state/approve-high-risk`); otherwise the loop records a proposal.
- The disk fault only writes to a bounded loop-backed volume, checked by one
  fail-closed mount guard used by the installer, the preflight and the fault
  generator.
- Host key checking is never disabled. An unexplained key change stops the
  loop for that host until a person verifies it through the console.
- The tests never touch the healer's real host identity state, and use RFC
  5737 documentation addresses.
- The LLM advisor has no effectors, and its API key travels in a request
  header, never in a URL or a file.

## Tests

```bash
python3 tools/test_safety.py      # loop and guardrails
python3 tools/test_adapter.py     # EduCloud adapter, Prometheus sensor, CLI
python3 tools/test_learning.py    # Knowledge, prevention, the advisor
bash    tools/test_lab_host.sh    # host scripts and the installer gate
```

The simulation (`tools/demo.py`, `tools/experiment.py`) still runs anywhere and
is useful for development. Its numbers are simulation, not observation.

## Repository layout

```
mapek/          the loop: stages, knowledge, guardrails, actions, advisor,
                Prometheus sensor, EduCloud adapter, simulation
tools/          lab CLI, provisioning, installers, loop service, live runs,
                experiment, tests
tools/lab-host/ scripts installed on each app instance
monitoring/     Prometheus, rules, blackbox, Grafana dashboard (generated)
config/         lab.json: identifiers only, no credentials
evidence/       raw, timestamped output of every live step and run
docs/           design notes and results
```

## Honest limits

- One managed service type (nginx) and three fault types. The infrastructure
  layer only; application faults are out of scope.
- The disk failure depends on a declared lab protocol (the startup storage
  preflight), not on stock nginx behaviour.
- Monitor detection depends on scrape intervals (10 s) and a one-minute rate
  window. Detection delay is part of every measured number.
- The healer had 1 GiB of memory and no swap. During the experiment it ran
  out of memory and stopped, so B and C have two repetitions, not three
  (`evidence/2026-10-13-incident-healer-memory.md`). Do not run heavy
  interactive tools on the healer during an experiment.
- A host key accepted at first contact is trust on first use. Console
  verification of fingerprints is a manual step.
- EduCloud guarantees neither availability nor backups, and removes projects
  after about six months. This repository and `evidence/` are the record.
