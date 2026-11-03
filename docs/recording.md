# Record a failure and its repair

The story is: **working request -> connection failure -> diagnosed incident -> your approval -> verified recovery -> reviewed knowledge -> repeat failure repaired without a new approval**. This is a gateway-availability experiment motivated by banking, not a banking application or payment demo.

## Install the optional presentation page

On the management checkout, install the page as the existing Ubuntu user:

```sh
install -D -m 644 host/platform-demo-page.service ~/.config/systemd/user/platform-demo-page.service
systemctl --user daemon-reload
systemctl --user enable --now platform-demo-page
```

The management checkout must contain `src/platform_healer/demo_service.py`. Deploy the updated `gateway_observer.py` to `/opt/platform-healer/src/platform_healer/` on **probe-1 only** and restart `platform-gateway-observer` while no experiment is active. This adds the read-only mTLS `/check` route; it does not replace the namespace, root policy, identity registry or gateway process. Keep rollback copies of source files. The page uses the existing management `~/.config/platform-healer/pki/monitor.crt`, `monitor.key` and `ca.crt`. No new API key is required.

Add SSH forwards for local 8086 -> management 127.0.0.1:8086, local 8085 -> management 127.0.0.1:8085, and local 3000 -> monitor 10.1.1.50:3000. Bind the laptop ports to loopback only. On this Windows laptop IPv6 loopback forwarding (`-L [::1]:8086:127.0.0.1:8086`) works with `http://localhost:8086`; IPv4 localhost has previously timed out. Keep the VPN and tunnel connected.

Open these pages in Edge:

- **Service check:** http://localhost:8086/
- **Healer:** http://localhost:8085/ (select the private operator.token file)
- **Monitoring:** http://localhost:3000/d/platform-mapek

The service page sends a fresh request from probe-1 through HAProxy for each check. It displays real HTTP codes or no response, verifies the expected nonce response and bounds recent history. It shows “Cannot check” when the probe/measurement path is unavailable; that is not proof the gateway is down.

## Before recording

1. Keep the service-check page and healer Overview side by side. Keep Grafana in another tab. Leave automatic checks enabled on the service page.
2. On the management host, open the checkout in a terminal: `cd ~/projects/platform-tuning-engine`.
3. Confirm requests pass, the namespace range is 32, and active connections are zero. Do not run another load experiment at the same time.
4. Check Knowledge. Two verified occurrences after the last failure and a named review are required for automatic reuse. Existing records must be described as existing qualification evidence. Do not delete history to pretend this is a new system.
5. Rehearse opening a pending incident and typing the approval fields. Each load lasts 30 seconds; aim to approve within the first 15 seconds so verification can complete under continuing load. If you are too late, let the load drain and repeat honestly. The runner fails rather than counting a late recovery as success.

## Record the reviewed run

Start your screen recorder yourself. Show the design for about 20 seconds, then the passing service page. Say: “A separate client checks real requests through the gateway. The healer watches a specific outgoing-port constraint.”

Run on the management host:

```sh
python3 experiments/video_demo.py reviewed --actor Tushar
```

The runner changes to reviewed mode, checks a fresh healthy baseline and starts 64 bounded workers on probe-1. It **never approves** the incident. Show failing service requests and the healer's saturated 32-port pool. Open the new pending incident, explain the healthy backend plus allocation/error evidence, enter your name and a reason, then select **Approve the fixed port-range repair** and confirm.

Watch the service page recover while background connections remain active. Show **Repair verified** in the incident. The terminal must finish with PASS, confirming recovery under continuing load, unchanged gateway identity and baseline rollback. If it reports failure, keep the log and investigate; do not present it as a successful run. HTTP checks and background held requests are different traffic; cancellation of test holds is not a lost payment.

## Review the knowledge and repeat

Open Knowledge and show the verified records for the **current identity**. If fewer than two are eligible, repeat the reviewed run. Enter your name and use **Qualify this scoped procedure** only after reviewing the outcomes. A suspended procedure also needs explicit requalification; count alone never grants permission.

Run the same load again:

```sh
python3 experiments/video_demo.py automatic --actor Tushar
```

Do not press Approve. The runner refuses to inject load if the current exact-scope procedure is not validated. Show a repeat failure and recovery without a new incident approval. The CLI verifies that the automatic incident has no new approval actor and that recovery occurred while connections were still active. It never qualifies the procedure itself. Both runs restore the prior control mode when finished; leases reconcile independently.

Finish with the saved incident ledger and Grafana's port-range/error/connection history. Say: “The system remembers when a reviewed repair may be reused. It does not train the language model or invent arbitrary fixes. Unknown failures still require investigation, and failed verification suspends reuse.”

## Evidence and boundaries

The runner prints UTC timestamps and saves a private JSON record under `~/.local/state/platform-healer/evidence/video-*.json`. Copy recordings, logs and histories off-platform. Keep private keys, operator tokens and detailed histories out of Git. Shared reviewer names are audit labels, not enterprise identity proof. The page adds a small number of read-only checks; do not add these demonstration runs to the original comparison dataset.
