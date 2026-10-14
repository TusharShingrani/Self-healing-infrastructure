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

Learning from failures is not new: published systems such as Narya (OSDI 2020)
already learn. This project is a bounded EduCloud prototype with a reproducible
evaluation of reviewed procedural learning. See the
[research synthesis](docs/research-synthesis.md).

There are two loops on the healer, with separate state:

| Loop | Manages | Service, metrics | Read first |
|---|---|---|---|
| nginx loop | nginx, its config and its bounded log volume on app-1 and app-2 | `healer-loop`, :9105 | this page, [operator workflow](docs/operator-workflow.md) |
| Dependency loop | a synthetic transaction on app-1 that needs DNS and Redis on app-2 | `healer-infrastructure`, :9106 | [broader infrastructure](docs/infrastructure-lab.md) |

Both run with **incident review**. A repair waits for a person's approval until
a narrowly scoped procedure has two verified successes and is explicitly
promoted. The A/B/C results and the 14 October guided demo were measured
before review existed and describe the earlier policy.

**Documents:**
[context report: the problem and the failure scenarios](docs/context-report.md)
· [architecture and design: network, MAPE-K, learning, design decisions](docs/architecture.md)
· [operator workflow: incidents, human repairs, validated procedures](docs/operator-workflow.md)
· [broader infrastructure: DNS, Redis, permissions](docs/infrastructure-lab.md)
· [research synthesis](docs/research-synthesis.md) and [search log](docs/research-search-log.md)
· [results of the A/B/C experiment](docs/results.md)
· [dependency results](evidence/infrastructure-validation-2026-10-14.md)
· [guided live demo](docs/live-demo.md) and [its raw account](evidence/live-demo-2026-10-14.md)
· [design notes](docs/design-notes.md)
· [healer handover: connections, backup, replacing or resizing the healer](docs/healer-handover.md)

## What runs where

```mermaid
flowchart LR
    laptop([Laptop]) -- "VPN + SSH via gateway" --> healer
    subgraph EduCloud project healer-lab, isolated network 10.1.1.0/24
        healer["healer-ubuntu 10.1.1.205<br/>nginx loop, metrics :9105<br/>dependency loop, metrics :9106<br/>Knowledge + incident review (SQLite)<br/>LLM advisor (optional)"]
        monitor["monitor 10.1.1.50<br/>Prometheus :9090<br/>blackbox probes<br/>Grafana :3000"]
        app1["app-1 10.1.1.60<br/>nginx + bounded log volume<br/>transaction :8088 + checkpoint<br/>node / nginx exporters"]
        app2["app-2 10.1.1.61<br/>nginx + bounded log volume<br/>DNS :1053, Redis :6380<br/>node / nginx exporters"]
        monitor -- scrape --> app1 & app2 & healer
        healer -- "M: PromQL" --> monitor
        healer -- "E: SSH effectors<br/>verify with direct probes" --> app1 & app2
        app1 -- "DNS, Redis" --> app2
    end
    healer -- "ownership checks, reboot, rebuild" --> api[(CloudStack API)]
```

| Instance | Role | Size |
|---|---|---|
| healer-ubuntu | Runs both loops, this repository, the evidence | 2 CPUs, 6 GiB |
| monitor | Prometheus, blackbox exporter, Grafana | 1 CPU, 4 GiB |
| app-1, app-2 | The managed infrastructure: nginx serving `/healthz`, plus the dependency stack | 1 CPU, 1 GiB |

Only the healer has a port forward. The app instances and the monitor are
reached over the isolated network. All four are deployed from one private
template, at fixed addresses, by `tools/lab.py`. The template does not contain
the dependency stack; `tools/infrastructure.py install` adds it.

## The MAPE-K loop, stage by stage

This is the nginx loop. The dependency loop reuses the same `Healer` class and
stages; [broader infrastructure](docs/infrastructure-lab.md) explains what it
changes.

| Stage | Code | What it does here |
|---|---|---|
| **Monitor** | `mapek/prometheus.py`, `stages.Monitor` | Reads fresh Prometheus series per node (availability from the blackbox probe, nginx unit state, log volume use and its growth rate, config correctness) and names symptoms. A missing, stale or pre-action sample is not used; that field falls back to a direct SSH probe. A failed probe is unknown, never healthy |
| **Analyse** | `stages.RuleAnalyser` | Turns symptoms into a cause. Knowledge is asked first (a symptom set seen before), then rules from most to least specific, then human-approved LLM advice |
| **Plan** | `stages.Planner` | Picks actions from a fixed catalogue (`mapek/actions.py`) by escalation level: guest repair, then reboot, then rebuild. The planner cannot invent a command |
| **Execute** | `stages.Executor`, `mapek/loop.py`, `mapek/operator.py` | Checks guardrails (cool-down, rate limit), the high-risk gate and the incident review gate, runs the actions over SSH, then **verifies with direct probes**. A repair that does not verify escalates |
| **Knowledge** | `mapek/knowledge.py`, `mapek/operator.py` | SQLite shared by every node: incidents, learned prevention rules, LLM advice, reviewed incident cases, the decision audit and repair procedures |

The whole loop is `Healer.tick()` in `mapek/loop.py`, with the stages marked.
`tools/healer_service.py` runs one loop per app instance every 10 seconds and
publishes what each stage did as metrics.

### How it learns

There are two kinds of learning, and they are kept apart.

**Validated repair procedures** (`mapek/operator.py`). Every proposed repair
opens an incident case with evidence. A person approves it once
(`tools/incidents.py approve`), or performs the repair and records it
(`record-human`). Each verified repair creates a candidate procedure. After two
distinct verified occurrences, a person can promote it. From then on, the same
cause with the same symptoms on the same target, template and reference files
is repaired automatically. A failed verification revokes the procedure.

**Prevention rules from early signs** (`mapek/knowledge.py`). When an incident
is resolved, Knowledge stores the symptoms that were present **before** the
failure (the early signs) and the actions that fixed the cause. The next time
those early signs appear, the loop acts while the service is still healthy.
Knowledge is shared, so a rule learned on app-1 can protect app-2. With review
on, a new rule is stored unapproved (`tools/knowledge.py approve-rule`), and the
preventive action still passes the incident review gate.

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

The live service runs config C with incident review (`HEALER_REVIEW=1`, the
default). The A/B/C experiment in `docs/results.md` ran without review.

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
symptoms appear. It still goes through the guardrails, the incident review gate
and the high-risk gate. Without a key, requests are still recorded, so a person
sees that the loop needed help. To turn it on, get a free key from Google AI
Studio and, on the healer:

```bash
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo; export GEMINI_API_KEY
bash tools/start_loop.sh start C           # passes the key to the service in memory
```

The Gemini call uses the REST API with the Python standard library, so there
is nothing to install. On the free tier Google may use prompts to improve its
products; the prompt holds symptoms and lab metrics only, never credentials.

## Watching it work

Grafana runs on the monitor and is only reachable inside the project network.
Tunnel through the healer from the laptop:

```bash
ssh -N -L 3000:10.1.1.50:3000 <your usual healer login>
# then open http://localhost:3000  (anonymous read-only; admin password:
#   ssh to the monitor and run: sudo cat /etc/grafana/admin-password)
```

The dashboard "Self-healing infrastructure (MAPE-K)"
(`/d/selfheal-mapek`) is laid out along the nginx loop: availability, what
Monitor sees, the current diagnosis and escalation level, actions executed,
time spent in each stage, and what Knowledge has learned. Every loop event is
an annotation on the graphs. The dependency loop has its own dashboard at
`/d/selfheal-infrastructure`.

On the healer:

```bash
python3 tools/lab_shell.py                # a shell with the in-memory credentials
bash tools/start_loop.sh status | logs
python3 tools/incidents.py list           # reviewed incident cases
python3 tools/incidents.py procedures
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
measures `/healthz` itself every second. Results go to `evidence/runs/`. With
review on, the loop opens an incident and waits unless you approve it in time
or a promoted procedure matches. See [the live demo guide](docs/live-demo.md).

## Results

See [`docs/results.md`](docs/results.md) for the live A/B/C experiment, with
every number traceable to a run folder under `evidence/`, and
[the dependency results](evidence/infrastructure-validation-2026-10-14.md) for
the DNS, Redis and permissions faults.

## Rebuilding the lab from nothing

Credentials come from the environment, never from a file:

```bash
export CS_URL=https://educloud.fontysict.nl/client/api   # not secret
read -rs -p 'CloudStack API key: ' CS_KEY; echo
read -rs -p 'CloudStack secret: ' CS_SECRET; echo
export CS_KEY CS_SECRET
export LAB_SSH_KEY=~/.ssh/healer-lab-key                  # keypair healer-lab-key2

python3 tools/lab.py status
python3 tools/lab.py deploy app-1 && bash tools/provision.sh app 10.1.1.60 evidence/provision-app-1.log
python3 tools/lab.py deploy app-2 && bash tools/provision.sh app 10.1.1.61 evidence/provision-app-2.log
python3 tools/lab.py deploy monitor && bash tools/provision.sh monitor 10.1.1.50 evidence/provision-monitor.log
bash tools/start_loop.sh start C
python3 tools/infrastructure.py install                   # dependency stack on app-1 and app-2
bash tools/start_infrastructure.sh start
```

A fresh app instance from the template is ready in about a minute, and
provisioned (packages, bounded volume, fail-closed checks, a real fill proof,
exporters) in under 40 seconds. A fresh monitor already gets the dependency
scrape jobs and dashboard from `monitoring/`. An existing monitor is updated
with `tools/configure_infrastructure_monitor.py`.

## Safety rules the code enforces

- Destructive platform actions only target names in `lab_instances`, never the
  healer or the monitor, and only after the instance's `projectid` is
  positively matched. Missing metadata fails closed.
- `reboot_instance` and `rebuild_instance` need explicit approval
  (`touch state/approve-high-risk`); otherwise the loop records a proposal.
  They can never become automatic procedures.
- Every other repair needs incident approval, or a promoted procedure whose
  scope still matches. Operator notes are never executed.
- Dependency repairs are typed recipes (`config/repair-recipes.json`) made of
  allowlisted operations. The schema refuses shell commands and arbitrary paths.
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
python3 tools/test_safety.py          # loop and guardrails
python3 tools/test_adapter.py         # EduCloud adapter, Prometheus sensor, CLI
python3 tools/test_learning.py        # Knowledge, prevention, the advisor
python3 tools/test_operator.py        # incident review, approval, procedures
python3 tools/test_infrastructure.py  # recipes, dependency loop, investigation
python3 tools/test_transaction.py     # the synthetic transaction
bash    tools/test_lab_host.sh        # host scripts and the installer gate
```

None of them call EduCloud. The simulation (`tools/demo.py`,
`tools/experiment.py`) still runs anywhere and is useful for development. Its
numbers are simulation, not observation.

## Repository layout

```
mapek/            the loop: stages, knowledge, operator review, guardrails,
                  actions, advisor, Prometheus sensor, EduCloud adapter,
                  dependency adapter and recipes, simulation
tools/            lab CLI, provisioning, installers, both loop services,
                  incident CLIs, live runs, experiments, tests
tools/lab-host/   scripts installed on each app instance (nginx experiment)
tools/stack-host/ the synthetic transaction installed on app-1
monitoring/       Prometheus, rules, blackbox, Grafana dashboards (generated)
config/           lab.json (identifiers only, no credentials), repair recipes
evidence/         raw, timestamped output of every live step and run
docs/             design, research, workflows and results
```

## Honest limits

- Two small managed stacks: nginx with three fault types, and one synthetic
  dependency transaction with four. The infrastructure layer only; application
  faults are out of scope.
- The disk failure depends on a declared lab protocol (the startup storage
  preflight), not on stock nginx behaviour.
- Monitor detection depends on scrape intervals (10 s) and a one-minute rate
  window. Detection delay is part of every measured number.
- The A/B/C experiment has three repetitions of A but only two of B and C: the
  healer, then 1 GiB with no swap, ran out of memory
  (`evidence/2026-10-13-incident-healer-memory.md`). It now has 6 GiB and swap.
- The learning demonstrations used scripted operator decisions. They show the
  workflow works, not how well a person or an LLM diagnoses a new failure.
- A host key accepted at first contact is trust on first use. Console
  verification of fingerprints is a manual step.
- EduCloud guarantees neither availability nor backups, and removes projects
  after about six months. This repository and `evidence/` are the record.
