# Healer handover: how everything connects, and how to replace the healer

This page is for whoever sits at a new healer (a person, or a Claude Code
session that has lost its earlier context). It lists everything that depends
on the healer, everything that lives only on the healer, and the order in
which to bring a new one up. Written on 2026-10-13, after the healer ran out of
memory (`evidence/2026-10-13-incident-healer-memory.md`).

## 1. The healer's identity is fixed, and other parts rely on it

Keep these the same and nothing else needs to change.

| Fixed value | Who relies on it | What breaks if it changes |
|---|---|---|
| Name `healer-ubuntu` | `config/lab.json` `healer_instance`; `tools/lab.py` and `mapek/educloud.py` refuse any deploy or destructive action on this name | The self-protection rule no longer covers the new machine |
| Address `10.1.1.205` | `monitoring/prometheus.yml` (scrape target for the loop's metrics), `tools/live_run.py` (reads the loop config from `10.1.1.205:9105`), `config/lab.json` `healer_guest_ip`, the port forward on the virtual router | The dashboard loses the loop's metrics; every live run is labelled `loop-not-running` and the experiment runner stops |
| Network `healer-isolated` 10.1.1.0/24 | Everything: the apps and the monitor have no port forward, so they are only reachable from inside | Nothing in the lab can be reached |
| Port forward tcp/22 on 10.53.14.225, firewall from one VPN address | The only way in from the laptop | No access at all except the EduCloud console |
| Keypair `healer-lab-key2` | Installed on app-1, app-2 and the monitor at deploy time | Nothing; the keypair only holds the public key. The private key is in section 2 |

The apps do not filter SSH by source address, so a new healer at the same
address with the same private key is accepted straight away.

## 2. What lives only on the healer

The repository is on GitHub, so code, docs and committed evidence are safe.
These are not in the repository, and some cannot be recreated.

| Item | Path | If it is lost |
|---|---|---|
| **Lab private key** | `~/.ssh/healer-lab-key` | **No SSH to app-1, app-2 or the monitor.** Recovery means a new keypair and resetting the key on every instance from CloudStack. Back this up first |
| GitHub deploy key | `~/.ssh/github_selfheal`, `~/.ssh/config` (`Host github.com` uses it) | No push. Recreate: new key, add it to the repository's deploy keys with write access |
| Pinned lab host keys | `~/.ssh/healer-lab-known-hosts/` (one file per address) | The loop re-learns them on first contact (trust on first use again); `tools/provision.sh` refuses until they exist |
| Host registry | `~/.local/state/healer-lab/hosts.json` (address to instance id) | Rebuilt on first contact; an id change is then not explained |
| Loop runtime state | `state/` in the repository (ignored by git): `knowledge.db`, `events.jsonl`, `experiment-console.log` | Knowledge and the loop's own event history are gone. Run evidence under `evidence/` is unaffected |
| `CS_URL` export | last lines of `~/.bashrc` | Re-add: `export CS_URL=https://educloud.fontysict.nl/client/api` |
| User lingering | `loginctl enable-linger ubuntu` | The loop service stops when you log out |
| sysstat | package `sysstat` | No memory history after the next incident |
| Claude Code memory | `~/.claude/projects/-home-ubuntu-projects-selfheal/` | Earlier session notes. Useful, not needed: this page and `CLAUDE.md` hold what matters |

`CS_KEY`, `CS_SECRET` and `GEMINI_API_KEY` are never on disk, so there is
nothing to copy. You type them into the shell that starts the loop.

## 3. First choice: resize in place, do not replace

CloudStack can change the service offering of a stopped instance. The disk,
the address, the port forward and every file in section 2 stay as they are.

1. Stop the loop: `bash tools/start_loop.sh stop`.
2. In the EduCloud console, stop `healer-ubuntu`. Do this by hand. The loop
   and the tools never act on the healer.
3. Change the service offering to `Small Instance +` (1 CPU, 4 GiB), the
   offering the monitor already uses.
4. Start the instance, log in, then section 6.

Back up section 2 anyway before step 2 (section 4, step 1). EduCloud does not
guarantee backups.

## 4. Replacing the healer, if resizing is not possible

The new and the old healer cannot both hold 10.1.1.205, so the old one has to
go first. Back up first.

1. **Back up, from the laptop** (over the VPN, through the port forward):

   ```bash
   ssh <healer login> 'tar czf - .ssh/healer-lab-key .ssh/github_selfheal .ssh/github_selfheal.pub \
       .ssh/config .ssh/healer-lab-known-hosts .local/state/healer-lab \
       projects/selfheal/state .claude/projects/-home-ubuntu-projects-selfheal' > healer-backup.tgz
   tar tzf healer-backup.tgz          # check the lab key is in it
   ```

   Also make sure `git status` on the healer is clean and pushed.
   The archive holds private keys: keep it on the laptop only, never in the
   repository or a shared drive.

2. Stop the loop, then destroy the old healer in the console. Expunge it, so
   that 10.1.1.205 is released.

3. **Deploy the new one in the console:**

   | Setting | Value |
   |---|---|
   | Name | `healer-ubuntu` |
   | Offering | `Small Instance +` (1 CPU, 4 GiB) |
   | Template | Ubuntu 24.04 (the old healer ran 24.04.4) |
   | Network | `healer-isolated`, IP address **10.1.1.205** |
   | Keypair | `healer-lab-key2` |

4. Recreate the port forward on 10.53.14.225 (tcp/22 to the new instance)
   and the firewall rule for your VPN address. The old rule pointed at the old
   instance and is gone with it.

5. **Restore, on the new healer:**

   ```bash
   # from the laptop
   scp healer-backup.tgz <new healer login>:
   # on the healer: keys first, so the clone can use the deploy key
   tar xzf healer-backup.tgz -C ~ --exclude=projects
   chmod 700 ~/.ssh ~/.ssh/healer-lab-known-hosts && chmod 600 ~/.ssh/healer-lab-key ~/.ssh/github_selfheal
   sudo apt-get update && sudo apt-get install -y git sysstat
   loginctl enable-linger ubuntu
   echo 'export CS_URL=https://educloud.fontysict.nl/client/api' >> ~/.bashrc
   mkdir -p ~/projects
   git clone git@github.com:TusharShingrani/Self-healing-infrastructure.git ~/projects/selfheal
   tar xzf healer-backup.tgz -C ~ projects/selfheal/state      # then the loop's state
   rm healer-backup.tgz
   ```

   The loop needs only Python 3 from the standard library, git and ssh. No
   pip install.

## 5. Sizing

| Offering | Verdict |
|---|---|
| 1 CPU, 1 GiB, no swap (old) | Too small. Loop, experiment and an interactive Claude Code session (about 350 MB) together exhausted it |
| **1 CPU, 4 GiB** (`Small Instance +`) | **Recommended.** Same as the monitor, plenty of room |
| 2 GiB | Works for the loop and experiments; tight with Claude Code running |

On any size, a 1 GiB swap file is cheap insurance, so the machine slows down
instead of locking up:

```bash
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 6. Bringing it back, and proving everything is connected

Run these in order. Each line says what it proves.

```bash
cd ~/projects/selfheal
export CS_KEY=... CS_SECRET=... LAB_SSH_KEY=~/.ssh/healer-lab-key

free -h                                              # the new size is there
for t in safety adapter learning; do python3 tools/test_$t.py | tail -1; done
bash tools/test_lab_host.sh | tail -1                # code is intact
python3 tools/lab.py status                          # CloudStack API and keys work
curl -s http://10.1.1.60/healthz; curl -s http://10.1.1.61/healthz      # network: ok ok
ssh -i $LAB_SSH_KEY -o UserKnownHostsFile=~/.ssh/healer-lab-known-hosts/10.1.1.60 \
    -o StrictHostKeyChecking=yes ubuntu@10.1.1.60 true && echo pinned key ok
curl -s -o /dev/null -w '%{http_code}\n' http://10.1.1.50:3000/api/health   # Grafana: 200
bash tools/start_loop.sh start C
curl -s http://10.1.1.205:9105/metrics | grep healer_loop_info               # loop exposes metrics
curl -s 'http://10.1.1.50:9090/api/v1/query?query=up{job="mapek"}'           # Prometheus scrapes it: value 1
python3 tools/knowledge.py events 5                   # loop is ticking
git push --dry-run                                   # deploy key works
```

If the host key check fails for an app, do not delete the file to make it
pass. Check the fingerprint in the EduCloud console first (`CLAUDE.md`, hard
safety rules).

Then write what happened to `evidence/` and commit it.

## 7. Map of the connections, in one place

```
laptop --VPN--> 10.53.14.225:22 --port forward--> healer 10.1.1.205
healer  --SSH :22, key healer-lab-key, pinned host keys--> app-1 10.1.1.60, app-2 10.1.1.61, monitor 10.1.1.50
healer  --HTTP :80 /healthz--> app-1, app-2         (verification after every repair)
healer  --PromQL :9090--> monitor                   (Monitor stage)
monitor --scrape :9100 :9113, probe :80--> app-1, app-2
monitor --scrape :9105--> healer                    (loop metrics on the dashboard)
healer  --HTTPS, signed with CS_KEY/CS_SECRET--> CloudStack API (state, ownership, reboot, rebuild, deploy)
healer  --HTTPS, optional GEMINI_API_KEY--> Gemini API (advice only)
healer  --SSH, deploy key github_selfheal--> GitHub (code and evidence off-platform)
```

Ports and firewall rules in detail: `docs/architecture.md`, section 1.
