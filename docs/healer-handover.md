# Current lab handover and recovery

Read [the architecture](architecture.md) and [repository audit](repository-audit.md)
before changes. This runbook covers both loops and their persistent incident
state. An older backup containing only Knowledge is incomplete.

## Identity and access

Healer name `healer-ubuntu` and address 10.1.1.205 are protected and relied on by
monitoring and gateway SSH. app-1 is 10.1.1.60, app-2 10.1.1.61 and monitor
10.1.1.50. The isolated network is 10.1.1.0/24. Only TCP 22 at 10.53.14.225 is
forwarded to the healer. Its cloud keypair was originally `healer-lab-key`;
the managed app keypair resource is `healer-lab-key2`.

The Downloads copy `healer-lab-key2.key` was previously verified to match the
healer's internal private key `~/.ssh/healer-lab-key`. Do not infer identity from
filenames alone. Use the right private key for the healer login; the Ubuntu
account is `ubuntu`, with SSH-key authentication rather than a shared password.

Approved VPN source rules have included 172.16.16.2/32, .15/32 and .19/32. Check
the actual portal rules against your assigned address before adding a rule.
Do not assume the whole VPN subnet is permitted. Never remove a changed SSH pin
without verifying the instance identity and fingerprint through its console.
First contact is trust on first use; deleting registry/pins loses that history.

## Discover active code and state

```bash
systemctl --user show healer-loop healer-infrastructure -p WorkingDirectory -p ExecStart
```

Historically nginx ran from `~/projects/selfheal` and dependencies from
`~/projects/broader-infrastructure`. Use the live service configuration and audit
deployment record to identify current paths. A GitHub merge does not upgrade a
running service. Check `git rev-parse HEAD` and `git status --short` in both active
directories. Avoid editing inactive checkouts while expecting live changes.

| State | Why preserve it |
|---|---|
| nginx state/knowledge.db | Incident outcomes, prevention candidates and advice |
| nginx state/operator.db | Approvals, human repairs, verified cases and procedures |
| infrastructure state/infrastructure/ | Separate Knowledge, incidents, investigations, procedures and events |
| ~/.local/state/healer-lab/hosts.json | Address to CloudStack instance identity |
| ~/.ssh/healer-lab-known-hosts/ | Per-address host pins |
| ~/.ssh/healer-lab-key | Internal app/monitor login private key |
| GitHub deploy key and SSH config | Repository access |
| /etc/healer-stack/ generated credentials on app VMs | Redis admin and restricted transaction credentials |
| Raw evidence in all active checkouts | Research samples and failed trials |

## Back up consistently before upgrade or replacement

Stop **both user loop services** before copying their SQLite databases. Direct
service stops preserve the credential manager environment; `start_loop.sh stop`
deliberately removes its secret variables, which also affects the other loop.

```bash
systemctl --user stop healer-loop healer-infrastructure
```

From the laptop, archive the actual state paths identified above together with
lab/GitHub keys, SSH configuration, host identity, user unit files and optional
Claude memory. Store the archive privately on the laptop: it contains private
keys. Check its member list and checksum. Do not commit it or paste its contents.
Use stopped-state copies or SQLite's backup API; a tar of a writing database is
not a guaranteed consistent backup. Restart the services after the backup if
not continuing an upgrade. Keep generated Redis credentials private or regenerate
them with the infrastructure installer on a clean replacement of the app pair.

## Credentials after reboot

CloudStack/Gemini credentials are kept in process/user-manager memory. They
must be entered again after a reboot. In the active checkout:

```bash
export CS_URL=https://educloud.fontysict.nl/client/api
read -rs -p 'CloudStack API key: ' CS_KEY; echo
read -rs -p 'CloudStack secret: ' CS_SECRET; echo
export CS_KEY CS_SECRET
export LAB_SSH_KEY="$HOME/.ssh/healer-lab-key"
# Optional advisor:
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
python3 tools/lab.py status
bash tools/start_loop.sh start C
bash tools/start_infrastructure.sh start
```

Never print the complete user-manager environment or put secret values in shell
history. `python3 tools/lab_shell.py` opens a shell with existing manager values
without printing them. An external SSH command does not automatically inherit
those variables. User lingering keeps services alive after logout.

## Resize, replace and restore

The healer already has 2 CPUs, 6 GiB RAM and a configured 1 GiB swapfile.
Check `free -h`, `swapon --show` and root disk use before changing resources.
Do not recreate an existing swapfile or append duplicate fstab entries.

Prefer resize in place when needed, after backup and stopping both loops.
Stopping the healer VM ends SSH/assistant sessions and clears memory-only
credentials. It is a separate operator cloud action; the automated healer must
never target itself. Preserve its name, address and key-based access.

For replacement, positively identify the old VM, back up first, preserve the
fixed network address and recreate the gateway SSH forward and approved VPN
source rule. Restore private keys, verified host identity files, all runtime
state and user unit configuration. Re-establish credentials, then run the
checks below before restarting action loops. A baseline template is plain Ubuntu.
App replacements need nginx/exporter provisioning **and** the dependency
installer, with app-2 installed before app-1. Monitor replacement needs its
Prometheus/blackbox/Grafana configuration. Do not claim restore complete merely
because SSH works. New app VM ids invalidate composite procedure scope and
require investigation/repair revalidation before automatic use.

## Reconnect checklist

From the active checkout with credentials available:

```bash
bash tools/test_all.sh
python3 tools/lab.py status
python3 tools/infrastructure.py status
python3 tools/incidents.py procedures
python3 tools/infrastructure.py procedures
curl -fsS http://10.1.1.60/healthz
curl -fsS http://10.1.1.61/healthz
curl -fsS http://10.1.1.60:8088/healthz
systemctl --user is-active healer-loop healer-infrastructure
curl -fsS http://10.1.1.205:9105/metrics
curl -fsS http://10.1.1.205:9106/metrics
```

Check fresh tick timestamps, zero unexpected errors, all required transaction
checks true, and all ten Prometheus targets up. An HTTP exporter returning 200
does not mean its underlying probe succeeded. Check blackbox `probe_success` too.
View both Grafana dashboards through an authenticated SSH tunnel. Verify GitHub
access without publishing a change merely as a connection check. Review candidate,
validated/revoked procedures and scope before demonstrating automatic repairs.
Keep post-upgrade validation and restore evidence off-platform.
