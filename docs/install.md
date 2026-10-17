# Installation: qualified EduCloud lab

This is an administrator-installed research prototype, not a universal production installer. Tested prerequisites: Ubuntu 24.04, Python 3.12, Linux 6.8, K3s 1.36, working network-policy enforcement, local-path PVC provisioner, Docker on worker-1, Prometheus/node-exporter and Grafana on the monitor.

## Nodes and responsibilities

| Node | Address | Purpose |
|---|---|---|
| healer-ubuntu | 10.1.1.205 | Administrator bastion, private backup/experiment runner and console tunnel |
| monitor | 10.1.1.50 | Prometheus, alerts and Grafana |
| k8s-control | 10.1.1.80 | K3s server; discovered SQLite datastore; never a load-injection target |
| k8s-worker-1 | 10.1.1.81 | Image builder and non-root controller with Knowledge PVC |
| k8s-worker-2 | 10.1.1.82 | Non-root DaemonSet agent, native broker and isolated resource fixtures |
| probe-1 | 10.1.1.84 | Independent benchmark runner for the bounded I/O comparison |

No banking API, statement worker, PostgreSQL VM, old nginx application VM or LLM account is required.

## Administrator deployment

On the bastion, place this source at `~/projects/platform-tuning-engine`. Configure `config/educloud.json` to reference your **existing private SSH key and pinned known_hosts files**. Do not commit keys. Verify changed SSH fingerprints through the cloud console; never disable strict verification.

Run `python3 -m unittest discover -s tests -v`, then `python3 scripts/deploy_lab.py --bootstrap-canary`.

The explicit bootstrap flag installs the fixed lab host policy, private node signing key, root broker unit and bounded fixture services on worker-2. It refuses another hostname. The two containers have no administrator SSH key, Kubernetes token or CloudStack credential. Subsequent source/image updates use `python3 scripts/deploy_lab.py` after draining demand and checking baseline restoration.

The image base is pinned by digest. Source is allowlisted into a package, built on worker-1 and imported into both worker runtimes; there is no registry credential. The renderer is the declared source of Kubernetes objects. It generates service accounts without tokens or RBAC grants, namespace policy, resource bounds, a PVC, Deployment, DaemonSet, Services and NetworkPolicies. Root-generated node key and operator token are applied separately through SSH stdin, never command arguments or Git.

The idle fixture processes remain available for demonstrations. Each load burst drains automatically after 120 seconds; held descriptors/connections are capped at 128. One-shot CLI fixtures also support a 10–900 second total lifetime. Restarting a fixture changes its identity and invalidates learned reuse for the replacement process.

Run `python3 monitoring/build.py` and `python3 scripts/configure_monitor.py` on the bastion. The latter validates Prometheus configuration before restart and keeps rollback copies of changed dashboard/configuration files. It expects the existing monitor packages and Grafana Prometheus datasource UID `prometheus`.

## Console access

The controller listens on a private Kubernetes NodePort. Reach it through the management SSH tunnel; no public web port is required. The bastion's `platform-console-tunnel` user service forwards its localhost port 8085 to the private controller. From your VPN-connected laptop, forward local 8085 to the bastion's localhost 8085, and local 3000/9090 to the monitor's Grafana/Prometheus.

Install that lab tunnel on the bastion once:

```sh
install -D -m 644 host/platform-console-tunnel.service ~/.config/systemd/user/platform-console-tunnel.service
systemctl --user daemon-reload
systemctl --user enable --now platform-console-tunnel
```

The supplied unit is specifically for the Ubuntu EduCloud inventory. Review its user, private address and key paths when adapting the lab.

Open `http://127.0.0.1:8085`. Obtain the private operator token from the administrator's `~/.config/platform-healer/operator.token` file or its private laptop backup. You can paste it into the console or select that private token file in its sign-in form. Do not paste it into chat, a URL or Git. Browser origins are explicitly limited to localhost/127.0.0.1:8085. Corporate deployment needs HTTPS/mTLS and enterprise identity integration before use outside this lab.

## Recovery and upgrade

Before changing source, drain both desired-demand files to zero and confirm descriptor soft limit 64 and isolated range 40000–40031. Preserve the native journal, root policy/signing key, controller Knowledge PVC, operator token, source revision, pinned host keys and administrator access off-platform. Back up SQLite with its online backup API rather than copying an active database file. Kubernetes Secret export is private material.

The controller's Recreate strategy avoids two simultaneous SQLite writers. Restart recovery reconciles the same persisted operation ID instead of issuing another mutation. A broker restart attempts compare-and-set rollback; busy targets defer visibly. Conflicts and changed identities require operator review.

Do not destroy the management VM or K3s server as an experiment. EduCloud VM lifecycle administration is outside the runtime repair catalogue.
