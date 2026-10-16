#!/usr/bin/env bash
# Run only on a positively identified new node through tools/expansion.py.
set -euo pipefail
ROLE=${1:?role}; VERSION=${2:-v1.36.5+k3s1}
case "$ROLE" in control) EXPECT=10.1.1.80;; worker-1) EXPECT=10.1.1.81;; worker-2) EXPECT=10.1.1.82;; database) EXPECT=10.1.1.83;; observer) EXPECT=10.1.1.84;; *) exit 2;; esac
ip -4 address show | grep -q "inet $EXPECT/" || { echo 'Unexpected guest address'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=600 update -qq
apt-get -o DPkg::Lock::Timeout=600 install -y -qq curl ca-certificates prometheus-node-exporter python3 python3-psycopg2 >/dev/null
cat > /etc/default/prometheus-node-exporter <<'EOF'
ARGS="--collector.systemd --collector.systemd.unit-include=(k3s|k3s-agent|postgresql.*|job-.*)\.service"
EOF
systemctl restart prometheus-node-exporter
install -d -m 755 /opt/healer-jobs
install -d -m 700 /etc/healer-jobs
HERE=$(cd "$(dirname "$0")" && pwd)
if [ "$ROLE" = control ]; then
  install -d -m 700 /etc/rancher/k3s
  cat > /etc/rancher/k3s/audit-policy.yaml <<'EOF'
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: Metadata
EOF
  cat > /etc/rancher/k3s/config.yaml <<EOF
node-name: k8s-control
node-ip: 10.1.1.80
tls-san:
  - 10.1.1.80
write-kubeconfig-mode: "0600"
secrets-encryption: true
disable:
  - traefik
  - servicelb
node-taint:
  - node-role.kubernetes.io/control-plane=true:NoSchedule
kube-apiserver-arg:
  - audit-policy-file=/etc/rancher/k3s/audit-policy.yaml
  - audit-log-path=/var/lib/rancher/k3s/server/logs/audit.log
  - audit-log-maxage=3
  - audit-log-maxbackup=2
  - audit-log-maxsize=10
EOF
  curl -fsSL https://get.k3s.io -o /tmp/healer-k3s-install.sh
  INSTALL_K3S_VERSION="$VERSION" bash /tmp/healer-k3s-install.sh >/var/log/healer-k3s-install.log 2>&1
  k3s kubectl wait --for=condition=Ready node/k8s-control --timeout=180s
elif [[ "$ROLE" = worker-* ]]; then
  test -s /etc/rancher/k3s/config.yaml || { echo 'Missing private join configuration'; exit 1; }
  curl -fsSL https://get.k3s.io -o /tmp/healer-k3s-install.sh
  INSTALL_K3S_VERSION="$VERSION" INSTALL_K3S_EXEC=agent bash /tmp/healer-k3s-install.sh >/var/log/healer-k3s-install.log 2>&1
  if [ "$ROLE" = worker-1 ]; then
    apt-get -o DPkg::Lock::Timeout=600 install -y -qq docker.io >/dev/null
  fi
elif [ "$ROLE" = database ]; then
  apt-get -o DPkg::Lock::Timeout=600 install -y -qq postgresql >/dev/null
  python3 - <<'PY'
import json,secrets,os,subprocess
from pathlib import Path
p=Path('/etc/healer-jobs/secrets.json')
if not p.exists():p.write_text(json.dumps({'api_token':secrets.token_hex(32)}));os.chmod(p,0o600)
existing=subprocess.check_output(['sudo','-u','postgres','psql','-Atc',"SELECT 1 FROM pg_database WHERE datname='jobs_lab'"],text=True)
if existing.strip()!='1':subprocess.run(['sudo','-u','postgres','createdb','jobs_lab'],check=True)

PY
  PGVERSION=$(pg_lsclusters --no-header | awk 'NR==1 {print $1}')
  CONF="/etc/postgresql/$PGVERSION/main"
  cat > "$CONF/conf.d/healer-jobs.conf" <<'EOF'
listen_addresses = '127.0.0.1,10.1.1.83'
max_connections = 40
shared_buffers = '128MB'
password_encryption = 'scram-sha-256'
EOF
  systemctl restart "postgresql@$PGVERSION-main"
  install -m 755 "$HERE/job-host/db_metrics.py" /opt/healer-jobs/db_metrics.py
  cat > /etc/systemd/system/job-db-metrics.service <<'EOF'
[Unit]
Description=Read-only statement database contract metrics
After=postgresql.service
[Service]
User=postgres
ExecStart=/usr/bin/python3 /opt/healer-jobs/db_metrics.py
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
MemoryMax=96M
CPUQuota=20%
[Install]
WantedBy=multi-user.target
EOF
  # Banking records have no synthetic-job deletion schedule. Preserve any old
  # hashing cleanup as a disabled rollback artifact, never run it for statements.
  if [ -f /etc/cron.daily/healer-job-retention ]; then
    install -d -m 700 /var/lib/healer-archive
    mv /etc/cron.daily/healer-job-retention /var/lib/healer-archive/healer-job-retention.disabled
  fi
  systemctl daemon-reload;systemctl enable job-db-metrics;systemctl restart job-db-metrics
  READY=0
  for _ in $(seq 1 30); do
    if sudo -u postgres pg_isready -q -d jobs_lab; then READY=1;break;fi
    sleep 1
  done
  test "$READY" = 1 || { echo 'PostgreSQL did not become ready; banking schema is prepared in the next phase'; exit 1; }
else
  id job-probe >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin job-probe
  chown root:job-probe /etc/healer-jobs;chmod 750 /etc/healer-jobs
  test -s /etc/healer-jobs/client.json || { echo 'Missing restricted API client credential'; exit 1; }
  chown root:job-probe /etc/healer-jobs/client.json;chmod 640 /etc/healer-jobs/client.json
  install -m 755 "$HERE/job-host/probe.py" /opt/healer-jobs/probe.py
  install -m 644 "$HERE/job-host/bank-oracle.json" /opt/healer-jobs/bank-oracle.json
  install -d -o job-probe -g job-probe -m 750 /var/lib/job-probe
  cat > /etc/systemd/system/job-client.service <<'EOF'
[Unit]
Description=Independent statement reconciliation observer
After=network-online.target
[Service]
User=job-probe
ExecStart=/usr/bin/python3 -u /opt/healer-jobs/probe.py
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/job-probe
MemoryMax=64M
CPUQuota=20%
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload;systemctl enable job-client;systemctl restart job-client
fi
echo "Expansion host ready: $ROLE $EXPECT"
