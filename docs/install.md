# Installation: qualified EduCloud lab

This is an administrator-installed research prototype, not a universal production installer. Tested prerequisites: Ubuntu 24.04, Python 3.12, Linux 6.8, K3s 1.36, working network-policy enforcement, local-path PVC provisioner, Docker on worker-1, Prometheus/node-exporter and Grafana on the monitor.

## Nodes and responsibilities

| Node | Address | Purpose |
|---|---|---|
| healer-ubuntu | 10.1.1.205 | Administrator bastion, private backup/experiment runner and console tunnel |
| monitor | 10.1.1.50 | Prometheus, alerts and Grafana |
| k8s-control | 10.1.1.80 | K3s server; discovered SQLite datastore; never a load-injection target |
| k8s-worker-1 | 10.1.1.81 | Image builder and non-root controller with Knowledge PVC |
| k8s-worker-2 | 10.1.1.82 | Non-root DaemonSet agent, native broker and real isolated HAProxy gateway |
| probe-1 | 10.1.1.84 | Independent HTTP observer and bounded gateway load runner |

No banking API, statement worker, PostgreSQL VM, old nginx application VM or LLM account is required.

## Administrator deployment

On the bastion, place this source at `~/projects/platform-tuning-engine`. Configure `config/educloud.json` to reference your **existing private SSH key and pinned known_hosts files**. Do not commit keys. Verify changed SSH fingerprints through the cloud console; never disable strict verification.

Run `python3 -m unittest discover -s tests -v`, then `python3 scripts/deploy_lab.py --bootstrap-gateway`.

The explicit bootstrap flag installs the real HAProxy gateway, dedicated namespace/veth/filter, bounded upstream, root policy/signing key and broker on worker-2, plus the exact route and independent mTLS observer on probe-1. It refuses another hostname. The two containers have no administrator SSH key, Kubernetes token or CloudStack credential. Subsequent source/image updates use `python3 scripts/deploy_lab.py` after draining demand and checking baseline restoration.

The image base is pinned by digest. Source is allowlisted into a package, built on worker-1 and imported into both worker runtimes; there is no registry credential. The renderer is the declared source of Kubernetes objects. It generates service accounts without tokens or RBAC grants, namespace policy, resource bounds, a PVC, Deployment, DaemonSet, Services and NetworkPolicies. Root-generated node key and operator token are applied separately through SSH stdin, never command arguments or Git.

The active root policy enables only gateway-ports. Retained fixture scripts are regression tools; bootstrap-canary.sh refuses to overwrite an installed gateway. Do not run legacy native_workflow.py against this profile. Use experiments/gateway_study.py for the real-gateway study.

Deployment creates a private Ed25519 CA and separate role certificates under ~/.config/platform-healer/pki (outside Git), verifies expiry, and delivers secrets only through SSH stdin. Agent and observer APIs require mTLS; monitor certificates cannot submit effects. Keep the private CA and keys off-platform, plan renewal, and never upload them. The agent's plain health port exposes only /healthz for kubelet probes.

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

Before changing source, stop the owned gateway load, confirm zero active backend connections and isolated range 40000–40031. Run experiments/acceptance.py after deployment and drain. Preserve the native journal, root policy/signing key, controller Knowledge PVC, operator token, source revision, pinned host keys and administrator access off-platform. Back up SQLite with its online backup API rather than copying an active database file. Kubernetes Secret export is private material.

The controller's Recreate strategy avoids two simultaneous SQLite writers. Restart recovery reconciles the same persisted operation ID instead of issuing another mutation. A broker restart attempts compare-and-set rollback; busy targets defer visibly. Conflicts and changed identities require operator review.

Gateway reboot reconstruction is installed as a host bootstrap service. A replaced HAProxy process/configuration or recreated namespace invalidates its pinned identity and automatic procedure scope. Inspect service/journal status and the exact gateway process through administrator SSH, drain the owned load and confirm baseline before explicitly reprovisioning with `--bootstrap-gateway`. The bootstrap refuses a non-baseline range. Requalification is required; do not copy an old registry onto a replacement process. Boot reconstruction is provisioned, but a full VM reboot/disaster-restore drill is not part of the recovery comparison.

Do not destroy the management VM or K3s server as an experiment. EduCloud VM lifecycle administration is outside the runtime repair catalogue.
