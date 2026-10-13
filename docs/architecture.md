# Architecture and design

Diagrams render on GitHub (Mermaid). Every address, port and rule below was
read from the live EduCloud project on 2026-10-13, not copied from a plan.

1. [Network](#1-network)
2. [Deployment and services](#2-deployment-and-services)
3. [The MAPE-K loop](#3-the-mape-k-loop)
4. [One tick, step by step](#4-one-tick-step-by-step)
5. [How the loop learns](#5-how-the-loop-learns)
6. [Escalation and the human in the loop](#6-escalation-and-the-human-in-the-loop)
7. [Monitoring data flow](#7-monitoring-data-flow)
8. [Building and resetting an instance](#8-building-and-resetting-an-instance)
9. [Design approaches](#9-design-approaches)

## 1. Network

```mermaid
flowchart LR
    subgraph home["Outside EduCloud"]
        laptop["Student laptop<br/>Fontys VPN client"]
    end

    subgraph edu["Fontys EduCloud (Apache CloudStack), project healer-lab"]
        vr["Virtual router<br/>public side 10.53.14.225<br/>source NAT for outbound traffic<br/>port forward tcp/22 to healer<br/>firewall: tcp/22 from one VPN address only"]

        subgraph iso["Isolated network healer-isolated 10.1.1.0/24, gateway 10.1.1.1"]
            healer["healer-ubuntu<br/>10.1.1.205<br/>:22 ssh, :9105 loop metrics"]
            monitor["monitor<br/>10.1.1.50<br/>:9090 Prometheus<br/>:9115 blackbox<br/>:3000 Grafana"]
            app1["app-1<br/>10.1.1.60<br/>:80 nginx, :9100 node<br/>:9113 nginx exporter"]
            app2["app-2<br/>10.1.1.61<br/>:80 nginx, :9100 node<br/>:9113 nginx exporter"]
        end
    end

    api[("CloudStack API<br/>educloud.fontysict.nl<br/>HTTPS, signed requests")]
    pkgs[("Package mirrors<br/>Ubuntu, apt.grafana.com")]
    llm[("Anthropic API<br/>optional, advisor only")]

    laptop -- "VPN, then SSH :22<br/>(and an SSH tunnel to Grafana)" --> vr
    vr -- "tcp/22" --> healer
    healer -- "SSH :22 (effectors, probes)" --> app1 & app2
    healer -- "HTTP :80 /healthz (verification)" --> app1 & app2
    healer -- "PromQL :9090" --> monitor
    monitor -- "scrape :9100 :9113, probe :80" --> app1 & app2
    monitor -- "scrape :9105" --> healer
    healer -. "via NAT" .-> api
    healer -. "via NAT, optional" .-> llm
    iso -. "via NAT, installs only" .-> pkgs
```

| From | To | Port | Purpose |
|---|---|---|---|
| Laptop (one VPN address) | healer | 22 | The only way in. Grafana through `ssh -L 3000:10.1.1.50:3000` |
| healer | app-1, app-2 | 22 | Guest effectors and direct probes, host keys pinned per address |
| healer | app-1, app-2 | 80 | Direct `/healthz` check after every repair |
| healer | monitor | 9090 | The Monitor stage queries Prometheus |
| monitor | app-1, app-2 | 9100, 9113, 80 | Host and nginx metrics, blackbox availability probe |
| monitor | healer | 9105 | The loop's own metrics |
| healer | CloudStack API | 443 | Instance state, ownership checks, reboot, rebuild, deploy |

Nothing in the lab is reachable from outside except SSH to the healer, and that
only from one VPN address. Fault injection and every probe stay inside
10.1.1.0/24.

## 2. Deployment and services

```mermaid
flowchart TB
    subgraph H["healer-ubuntu (1 CPU, 1 GiB)"]
        svc["healer-loop.service (systemd user unit)<br/>tools/healer_service.py"]
        k[("state/knowledge.db<br/>SQLite: incidents, rules, advice")]
        ev[("state/events.jsonl")]
        repo["this repository<br/>tools/lab.py, provision.sh, live_run.py"]
        svc --- k & ev
    end
    subgraph M["monitor (1 CPU, 4 GiB)"]
        prom["prometheus"] --> rules["recording + alert rules<br/>monitoring/rules/healer.yml"]
        bb["prometheus-blackbox-exporter"]
        graf["grafana-server<br/>dashboard: Self-healing infrastructure (MAPE-K)"]
        graf --> prom
        prom --> bb
    end
    subgraph A["app-1 / app-2 (1 CPU, 1 GiB each)"]
        nginx["nginx<br/>/healthz returns ok"]
        pre["ExecStartPre: healer-preflight<br/>needs 25 MiB free"]
        vol[("/var/log/nginx<br/>512 MiB loop-backed ext4")]
        rot["healer-logrotate.timer<br/>every 15 s"]
        flood["healer-logflood.timer<br/>fault generator, off"]
        ne["node_exporter<br/>+ textfile: healer-metrics"]
        nx["nginx exporter"]
        pre --> nginx --> vol
        rot --> vol
        flood -. "only when the fault is injected" .-> vol
    end
    svc -- "PromQL" --> prom
    prom -- "scrape" --> ne & nx & svc
    bb -- "GET /healthz" --> nginx
    svc -- "SSH effectors" --> A
```

## 3. The MAPE-K loop

The reference model (Kephart and Chess, 2003), with what each part is in this
project.

```mermaid
flowchart TB
    subgraph AM["Autonomic manager: healer-ubuntu, one loop per managed instance, every 10 s"]
        direction LR
        M["<b>Monitor</b><br/>mapek/prometheus.py<br/>stages.Monitor<br/>fresh Prometheus series to symptoms:<br/>service_down, disk_high, disk_critical,<br/>disk_growing_fast, config_drift,<br/>unreachable, probe_failed"]
        A["<b>Analyse</b><br/>stages.RuleAnalyser<br/>symptoms to a CAUSE<br/>1 recall from Knowledge<br/>2 rules, most specific first<br/>3 human-approved LLM advice"]
        P["<b>Plan</b><br/>stages.Planner<br/>cause to catalogue actions<br/>by escalation level<br/>(guest, reboot, rebuild)"]
        E["<b>Execute</b><br/>stages.Executor + loop._act<br/>guardrails, approval gate,<br/>run actions over SSH or API,<br/>VERIFY with direct probes"]
        K[("<b>Knowledge</b><br/>mapek/knowledge.py, SQLite<br/>incidents, early signs,<br/>prevention rules, LLM advice,<br/>human decisions<br/>shared by all instances")]
        M --> A --> P --> E
        M <--> K
        A <--> K
        P <--> K
        E <--> K
    end
    subgraph ME["Managed element: app-1, app-2"]
        S["Sensors<br/>node_exporter, nginx exporter,<br/>healer-metrics facts,<br/>blackbox /healthz probe"]
        EF["Effectors<br/>restart_service, clear_logs,<br/>fix_log_rotation, restore_config,<br/>reboot_instance, rebuild_instance"]
    end
    S -- "via Prometheus" --> M
    E -- "SSH / CloudStack API" --> EF
    ADV["LLM advisor (optional)<br/>mapek/advisor.py<br/>advice only, no effectors"] -. "stuck: ask" .- A
    ADV -. "pending advice" .-> K
    HUM(["Operator<br/>tools/knowledge.py<br/>Grafana"]) -. "approve or reject" .-> K
```

| MAPE-K element | Concrete in this project |
|---|---|
| Managed element | nginx on app-1 and app-2, its config, its bounded log volume, the instance itself |
| Sensors | Prometheus exporters and the blackbox probe; direct SSH and HTTP probes as fallback and for verification |
| Effectors | Six named actions in `mapek/actions.py`. The loop cannot run anything else |
| Monitor | Prometheus queries per node, freshness checks, symptom naming |
| Analyse | Symptoms to cause: Knowledge, then rules, then approved advice |
| Plan | Cause to an ordered list of catalogue actions, by escalation level |
| Execute | Guardrails, approval gate, action, verification, record |
| Knowledge | Incident history, learned prevention rules, advice and human decisions |

## 4. One tick, step by step

The first time the disk fault happens (configuration C, empty Knowledge).

```mermaid
sequenceDiagram
    autonumber
    participant L as Loop (healer)
    participant P as Prometheus (monitor)
    participant K as Knowledge
    participant A as app-1
    Note over A: fault: rotation policy removed,<br/>producer fills the log volume
    L->>P: Monitor: query series for app-1
    P-->>L: healthy, log volume growing 40 points/min
    L->>L: symptoms = [disk_growing_fast], service healthy
    L->>K: no prevention rule yet: open incident,<br/>remember the EARLY SIGNS
    Note over A: volume reaches 100 %<br/>maintenance restart fails its preflight<br/>nginx stops, /healthz down
    L->>P: Monitor
    P-->>L: /healthz down, nginx inactive, volume 100 %, growing
    L->>L: symptoms = [service_down, disk_critical, disk_growing_fast]
    L->>K: Analyse: recall? none
    L->>L: rule: service_down_because_disk_full_from_log_growth
    L->>L: Plan level 0: clear_logs, fix_log_rotation, restart_service
    L->>L: guardrails ok, no high-risk action
    L->>A: Execute over SSH
    L->>A: Verify: direct probes, ignore pre-action samples
    A-->>L: active, config ok, /healthz = ok
    L->>K: record incident (resolved),<br/>learn rule: on [disk_growing_fast] run clear_logs + fix_log_rotation
```

The next time, on any instance:

```mermaid
sequenceDiagram
    autonumber
    participant L as Loop (healer)
    participant P as Prometheus
    participant K as Knowledge
    participant A as app-2
    Note over A: same fault, first time on app-2
    L->>P: Monitor
    P-->>L: healthy, log volume growing fast
    L->>K: prevention rule for [disk_growing_fast]?
    K-->>L: yes: clear_logs, fix_log_rotation
    L->>A: Execute while the service is still healthy
    L->>A: Verify
    Note over A: volume never fills,<br/>the later restart succeeds,<br/>no outage
    L->>K: record incident (prevented)
```

## 5. How the loop learns

```mermaid
stateDiagram-v2
    [*] --> Healthy
    Healthy --> EarlySigns: symptoms while still healthy
    EarlySigns --> Prevented: an approved prevention rule matches
    Prevented --> Healthy: verified
    EarlySigns --> Failure: no rule, the error grows into a failure
    Healthy --> Failure: sudden failure, no early signs
    Failure --> Diagnosed: Analyse finds a cause
    Failure --> Stuck: no rule matches
    Diagnosed --> Repaired: Execute + verify passes
    Diagnosed --> Escalated: verify fails, next level
    Escalated --> Diagnosed
    Escalated --> Stuck: levels exhausted
    Repaired --> Learned: Knowledge stores early signs + cause actions
    Learned --> Healthy
    Stuck --> AdvicePending: LLM advisor proposes, nothing runs
    AdvicePending --> Approved: operator approves
    AdvicePending --> Rejected: operator rejects
    Approved --> Diagnosed: next occurrence uses the advice
    Rejected --> [*]
```

Three kinds of memory, all in `state/knowledge.db`:

| Memory | Written when | Used by | Effect |
|---|---|---|---|
| Incident history | Every repair, success or failure | Analyse (recall) | A symptom set seen before is diagnosed from experience |
| Prevention rules | A resolved incident had early signs | The early-signs path | The cause is fixed before the failure happens |
| Approved advice | An operator approves LLM advice | Analyse (last resort) | An unknown failure becomes a known one after one human decision |

`Knowledge(auto_approve=False)` makes learned rules wait for a person too,
for settings where automation may not change its own behaviour unreviewed.

## 6. Escalation and the human in the loop

```mermaid
flowchart TB
    start(["Failure diagnosed"]) --> L0["Level 0: guest repair<br/>e.g. clear_logs, fix_log_rotation, restart_service"]
    L0 -- verified --> done(["Healed, learned"])
    L0 -- not verified --> L1{"Level 1: reboot_instance<br/>HIGH RISK"}
    L1 -- "no approval" --> prop1["Proposal recorded<br/>level is NOT consumed"]
    L1 -- "approved<br/>(state/approve-high-risk)" --> r1["reboot via CloudStack,<br/>ownership proven first"]
    r1 -- verified --> done
    r1 -- not verified --> L2{"Level 2: rebuild_instance<br/>HIGH RISK"}
    L2 -- approved --> r2["destroy + redeploy from template"]
    r2 -- verified --> done
    r2 -- not verified --> stuck(["Levels exhausted"])
    L2 -- "no approval" --> prop2["Proposal recorded"]
    stuck --> adv["LLM advisor: cause + catalogue actions<br/>stored as PENDING"]
    nomatch(["No rule matches"]) --> adv
    adv --> human{"Operator reviews<br/>tools/knowledge.py"}
    human -- approve --> kb[("Knowledge: approved advice")]
    human -- reject --> x(["Discarded"])
    kb -. "next occurrence" .-> start
```

Guardrails apply to every executed plan: a cool-down per action (5 ticks) and
a rate limit (3 actions per 20 ticks). They exist because restart loops and
flapping are the classic way automation makes an outage worse.

## 7. Monitoring data flow

```mermaid
flowchart LR
    subgraph app["app-1, app-2"]
        t["healer-metrics timer, 15 s<br/>config_correct, rotation_policy_present,<br/>log_mount_ok, logflood_active"] --> tf["textfile collector"]
        tf --> ne["node_exporter :9100<br/>filesystems, systemd units"]
        so["nginx stub_status 127.0.0.1:8080"] --> nx["nginx exporter :9113"]
        hz["nginx /healthz :80"]
    end
    subgraph mon["monitor"]
        bb["blackbox :9115<br/>body must be exactly ok"]
        pr["Prometheus, scrape every 10 s<br/>recording rules:<br/>healer:log_volume_used_percent<br/>healer:log_volume_growth_percent_per_minute<br/>healer:nginx_active"]
        gr["Grafana"]
    end
    subgraph hl["healer"]
        lp["MAPE-K loop<br/>Monitor stage"]
        mx["loop metrics :9105<br/>stage timings, symptoms, diagnosis,<br/>actions, events, knowledge counts"]
    end
    ne --> pr
    nx --> pr
    bb -- probe --> hz
    bb --> pr
    mx --> pr
    pr --> gr
    pr -- "instant queries,<br/>max age 30 s,<br/>newer than last action" --> lp
```

Freshness rules for the Monitor stage, each added after a live run showed the
problem:

- a sample older than 30 s is stale, never health
- after the loop acts, samples scraped before the action are ignored
- a rate over a one-minute window is only trusted once the whole window
  starts after the action
- a missing or stale field falls back to a direct SSH probe; if that also
  fails, the field is unknown and the instance is not healthy

## 8. Building and resetting an instance

```mermaid
flowchart LR
    tpl[("Private template<br/>healer-baseline-2026-10-13")] --> dep["lab.py deploy / reset<br/>fixed address, keypair healer-lab-key2,<br/>ownership checked"]
    dep --> ssh["wait until SSH answers<br/>host key pinned per address"]
    ssh --> inst["install_lab_host.sh<br/>wait for cloud-init and apt<br/>nginx, bounded volume, references,<br/>rotation timer, preflight, fault generator (off)"]
    inst --> gate{"pre-proof gate:<br/>12 contract checks"}
    gate -- any fails --> stop(["refuse, nothing destructive"])
    gate -- all pass --> proof["fill proof: fill the volume,<br/>restart fails, /healthz down,<br/>reclaim, recovers"]
    proof --> exp["install_exporters.sh<br/>6 checks"]
    exp --> ready(["ready for the loop"])
```

Measured: a template rebuild until SSH answers takes about one minute, and
provisioning about 40 seconds. Exact figures per reset are in
`docs/results.md`.

## 9. Design approaches

Each decision, why it was made, and what was rejected.

| # | Decision | Why | Alternatives considered |
|---|---|---|---|
| 1 | **MAPE-K as the structure of the code**, one class per stage | The report and the code line up; each stage can be tested and shown on its own | A set of independent watchdog scripts (no shared knowledge, no place for learning); a Kubernetes operator (out of scope, and hides the loop) |
| 2 | **The managed element sits behind one interface** (`observe`, `health`, effectors) | The same loop runs against a simulation and against EduCloud | Writing the loop directly against SSH (untestable without a lab) |
| 3 | **A fixed action catalogue** | The set of possible effects is finite, reviewable and testable; the planner and the LLM can only name actions | Letting rules or an LLM produce shell commands (unbounded, unauditable) |
| 4 | **Repair the cause, not the symptom**, with a fault, error, failure chain | A restart alone brings the same failure back; fixing rotation removes it | Restart-only remediation, which most published systems stop at |
| 5 | **Verify after every action with direct probes**; health means every required probe readable and satisfied | An action that reports success while the service is down is the failure mode that makes automation dangerous | Trusting exit codes, or a unit reported "active" |
| 6 | **Learning as prevention rules from early signs** (case-based, "immune memory") | Explainable, works from one incident, every rule can be read and approved | Training an anomaly model (needs far more incidents than a lab produces, and cannot explain itself) |
| 7 | **Knowledge shared across instances** | One incident protects the whole fleet: learned on app-1, prevented on app-2 | Per-instance memory |
| 8 | **Prometheus as the sensor layer**, with freshness rules and direct-probe fallback | Industry-standard monitoring, one source for the loop and for Grafana | SSH probes only (no history, no dashboards); alerts as the trigger (adds the alert's own delay) |
| 9 | **Guardrails and escalation**: cool-down, rate limit, levels, approval for reboot and rebuild | Prevents restart loops and flapping; a destructive action is always a human decision | Unlimited retries; automatic rebuilds |
| 10 | **Fail closed on safety**: allowlist, positive project ownership, healer and monitor protected | A typo or bad metadata must never destroy the wrong machine | Checking names only in the CLI |
| 11 | **LLM as advisor, not actor**: schema-constrained to the catalogue, stored as pending, human approval | Gives help on unknown failures without giving an LLM control of infrastructure | An autonomous LLM agent with shell tools (unsafe, untestable, not reproducible) |
| 12 | **Deterministic failure through a declared preflight**, triggered by a deliberate restart | Stock nginx keeps serving on a full disk; the lab must show a real outage, honestly labelled | Pretending a full disk stops nginx; killing the process directly (no cause to find) |
| 13 | **Experiment resets from the template**, not snapshot reverts | Each run starts from a known identity and disk; runs cannot contaminate each other | Snapshot revert (faster, but carries state between runs) |
| 14 | **Independent measurement**: the experimenter probes `/healthz` itself every second | The system under test does not grade itself | Using the loop's own downtime counter |
| 15 | **Credentials only in memory**: environment, systemd user manager; never in files | EduCloud keys give control over the whole project | An env file on disk; keys in the repository |
| 16 | **Everything rebuildable from the repository**: fixed addresses, idempotent installers, evidence committed | EduCloud gives no backups and removes projects after about six months | Hand-built servers |
