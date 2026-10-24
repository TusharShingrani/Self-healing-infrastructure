# Design diagram gallery

Start with [what breaks and exactly what changes](../worked-example.md), then the [design specification](../design.md). The existing [runtime architecture](../architecture.md#runtime-map) is retained.

Download [the four-page draw.io file](haproxy-system-design.drawio), open it in diagrams.net, and select a page at the bottom. Symbols are original generic vector icons, not official vendor logos. Labels, symbols, boundaries and connectors can be moved separately. SVG previews need no editor.

Arrows identify request initiators; replies use the same channel. The incident and MAPE-K views describe logical progression, not network transport or measured durations.

## Whole solution

![Whole solution](solution.svg)

[SVG](solution.svg) · [Mermaid source](solution.mmd)

```mermaid
flowchart LR
  U([Operator]) -->|SSH tunnel and console session| C
  subgraph K1["Kubernetes: worker-1"]
    C["MAPE-K controller and console"]
    K[("Knowledge: SQLite on PVC")]
    C -->|Read and persist| K
  end
  subgraph W2["worker-2 VM"]
    A["Kubernetes node agent"]
    B["Native root broker and lease journal"]
    subgraph NS["Isolated Linux network namespace"]
      H["HAProxy gateway"] -->|HTTP loopback| T["Synthetic backend"]
    end
    A -->|Unix requests and forwarded intent| B
    B -->|Namespace-only admitted effect| H
  end
  C -->|mTLS GET sample and HMAC POST execute| A
  P["Separate probe VM"] -->|Nonce HTTP request| H
  B -->|Pull observer status over mTLS| P
  M["Prometheus and Grafana"] -.->|Scrape agent| A
  M -.->|Scrape observer| P
  M -.->|Scrape controller| C
  C -.->|Opt-in numeric evidence| G["Gemini advisor"]
  G -.->|Unverified report for UI| K
  classDef service fill:#eff6ff,stroke:#2563eb,color:#0f172a
  classDef effect fill:#fff7ed,stroke:#c2410c,color:#0f172a
  classDef advisory fill:#faf5ff,stroke:#7c3aed,color:#0f172a
  class C,A,M service
  class B effect
  class G advisory
```

## Network and deployment

![Network and deployment](network.svg)

[SVG](network.svg) · [Mermaid source](network.mmd)

```mermaid
flowchart TB
  L["Laptop: OpenVPN and local browser"] -->|SSH to forwarding IP :22| F["10.53.14.225:22"]
  F -->|Port forward| B["healer-ubuntu 10.1.1.205"]
  subgraph LAB["Private EduCloud lab"]
    B -->|SSH local forward to NodePort :30885| C["k8s-control 10.1.1.80"]
    C -->|Controller service to Pod :8085| W1["worker-1 10.1.1.81"]
    W1 -->|In-cluster agent service mTLS :9119| W2["worker-2 10.1.1.82"]
    W2 -->|Broker pulls /status mTLS :9106| P["probe-1 10.1.1.84"]
    P -->|Route /32 via .82; HTTP :18080| H["Namespace frontend 10.203.0.2:18080"]
    W2 ---|veth host .1 and peer .2 on 10.203.0.0/30| H
    H -->|Namespace loopback HTTP| T["127.0.0.1:19080 synthetic backend"]
    M["monitor 10.1.1.50"] -.->|Scrape controller :30885 and agent :30919| C
    M -.->|Scrape mTLS observer :9106| P
  end
  W1 -.->|Optional HTTPS :443| G["External Gemini API"]
  N["Monitoring also scrapes six node exporters :9100 and K3s readiness via blackbox.<br/>Laptop forwards localhost :3000 and :9090 through bastion to monitor."]
```

## MAPE-K and safety

![MAPE-K and safety](mapek.svg)

[SVG](mapek.svg) · [Mermaid source](mapek.mmd)

```mermaid
flowchart LR
  subgraph CT["Controller decision loop"]
    M["MONITOR<br/>Fresh same-identity sample via agent and broker"] --> A["ANALYSE<br/>Correlate failures; confirm twice"]
    A -->|Known eligible cause| P["PLAN<br/>Fixed namespace range, expected value, identity, lease"]
    P --> G{"Mode and permission?"}
    G -->|Watch only| WAIT["Record; do not dispatch"]
    G -->|Reviewed mode: named approval| E["EXECUTE<br/>Persist HMAC operation before dispatch"]
    G -->|Automatic mode: matching qualified scope| E
    E --> V["VERIFY in controller<br/>Fresh bound and three distinct probe successes<br/>At least 2 s within 20 s"]
    V -->|Outcome| K[("KNOWLEDGE<br/>Incidents, audit, procedures, advice, human notes")]
    K -.->|History for next tick| M
    K -.->|Two verified after last failure plus named promotion| G
  end
  A -->|Other cause or unknown| I["Operator investigation; no automatic port repair"]
  E -->|mTLS agent; HMAC intent; Unix socket| B["Root broker<br/>Fresh admission, journal, bounded write"]
  B --> H["HAProxy namespace<br/>32 to 256 source ports"]
  H -.->|Probe-host results relayed by broker and agent| V
  B --> R["Independent lease watchdog<br/>Drain then compare-and-set rollback"]
  V -->|Failure suspends reuse| K
  I -.->|Reported notes; cannot qualify execution| K
```

## One incident, end to end

![One incident, end to end](incident.svg)

[SVG](incident.svg) · [Mermaid source](incident.mmd)

```mermaid
sequenceDiagram
  actor O as Operator
  participant C as Controller
  participant K as Knowledge SQLite
  participant A as Node agent
  participant B as Root broker
  participant H as HAProxy namespace
  participant P as Probe host
  loop Independent client checks
    P->>H: HTTP nonce transaction
    H-->>P: Status and expected body
  end
  loop Fresh controller ticks
    C->>A: GET /sample/gateway-ports over mTLS
    A->>B: Unix socket sample
    B->>H: Read used_ports/range_size, HAProxy errors, local transaction
    B->>P: GET /status over mTLS
    P-->>B: Separate-host result and observation time
    B-->>A: Sample: port use, errno, rising errors, HTTP results, safety
    A-->>C: Relayed evidence
  end
  C->>K: Confirm twice: >=85% ports, errno 99, rising errors, both HTTP checks fail
  O->>C: Approve expand_port_range with name and reason
  C->>K: Store approved state
  Note over C,K: Approval does not directly dispatch a mutation
  C->>K: Later tick: persist exact HMAC operation ID
  C->>A: POST /execute, mTLS controller identity
  A->>B: Forward HMAC intent
  B->>B: Authenticate, validate identity/value/safety, journal first
  B->>H: Namespace ip_local_port_range: 40000-40031 to 40000-40255, lease 30 s
  H-->>B: Readback
  B-->>A: Applied lease
  A-->>C: Applied status
  loop Three distinct successes over at least two seconds
    C->>A: GET operation, sample and verify
    A->>B: Query journal and fresh checks
    B->>P: Pull a fresh independent result
    B-->>A: Range readback, HTTP status/body, distinct probe time
    A-->>C: Evidence for verification
  end
  C->>K: Verified outcome, or failure and suspended reuse
  Note over B,H: Broker watchdog continues if controller stops
  alt Lease expires, identity/value match and connections drained
    B->>H: With zero active connections, restore 40000-40031 if identity/value match
  else Busy, changed value or replaced identity
    B->>B: Deferred rollback or visible conflict, no unsafe write
  end
```

## Maintain these views

Edit the Mermaid files for GitHub-rendered diagrams. Edit `scripts/build_design_diagrams.py` and run `python scripts/build_design_diagrams.py` to regenerate the SVG and draw.io views. The two formats express the same contracts with different layouts. Regeneration overwrites manual draw.io layout edits. Check both after changing an endpoint, identity boundary, approval rule or repair.
