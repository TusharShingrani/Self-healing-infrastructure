#!/usr/bin/env bash
# Bootstrap the dedicated job-service monitor from ~/lab/monitor assets.
# Then run configure_jobs_monitor.py from the healer to install scoped probes
# and the Kubernetes CA. Only the job-service dashboard is provisioned.
set -euo pipefail
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/monitor
[ -f "$SRC/prometheus.yml" ] || { echo "missing $SRC/prometheus.yml" >&2; exit 1; }

# A fresh instance is often still running cloud-init or unattended-upgrades,
# which hold the apt locks for a while after boot. Wait for them instead of
# failing on "Could not get lock" (seen on a template reset).
wait_for_apt () {
    cloud-init status --wait >/dev/null 2>&1 || true   # "degraded done" exits 2
    if command -v fuser >/dev/null; then
        for _ in $(seq 1 120); do
            fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
                  /var/lib/apt/lists/lock >/dev/null 2>&1 || return 0
            sleep 5
        done
        echo "apt is still locked after 10 minutes" >&2
        return 1
    fi
}
APT_WAIT="-o DPkg::Lock::Timeout=600"

echo "==> Prometheus and blackbox exporter (Ubuntu packages)"
wait_for_apt
export DEBIAN_FRONTEND=noninteractive
apt-get $APT_WAIT update -qq
apt-get $APT_WAIT install -y -qq --no-install-recommends prometheus prometheus-blackbox-exporter \
    curl gnupg >/dev/null

install -m 644 "$SRC/prometheus.yml" /etc/prometheus/prometheus.yml
mkdir -p /etc/prometheus/rules
install -m 644 "$SRC"/rules/*.yml /etc/prometheus/rules/
install -m 644 "$SRC/blackbox.yml" /etc/prometheus/blackbox.yml
cat > /etc/default/prometheus <<'CONF'
ARGS="--storage.tsdb.retention.time=30d"
CONF
promtool check config /etc/prometheus/prometheus.yml
systemctl restart prometheus-blackbox-exporter prometheus
systemctl enable prometheus prometheus-blackbox-exporter >/dev/null

echo "==> Grafana (official signed apt repository)"
mkdir -p /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/grafana.gpg ]; then
    curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /etc/apt/keyrings/grafana.gpg
fi
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
    > /etc/apt/sources.list.d/grafana.list
apt-get $APT_WAIT update -qq
apt-get $APT_WAIT install -y -qq grafana >/dev/null

# The admin password is generated here and never leaves this instance.
# Read it with: sudo cat /etc/grafana/admin-password
if [ ! -f /etc/grafana/admin-password ]; then
    head -c 18 /dev/urandom | base64 | tr -d '/+=' > /etc/grafana/admin-password
    chmod 600 /etc/grafana/admin-password
fi
umask 077
cat > /etc/grafana/selfheal.env <<ENV
GF_SECURITY_ADMIN_PASSWORD=$(cat /etc/grafana/admin-password)
ENV
umask 022
mkdir -p /etc/systemd/system/grafana-server.service.d
cat > /etc/systemd/system/grafana-server.service.d/selfheal.conf <<'UNIT'
[Service]
EnvironmentFile=/etc/grafana/selfheal.env
# Anonymous read-only viewing: Grafana is only reachable inside the isolated
# network, through an SSH tunnel. Editing still needs the admin login.
Environment=GF_AUTH_ANONYMOUS_ENABLED=true
Environment=GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
Environment=GF_USERS_ALLOW_SIGN_UP=false
Environment=GF_ANALYTICS_REPORTING_ENABLED=false
Environment=GF_ANALYTICS_CHECK_FOR_UPDATES=false
Environment=GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/jobs.json
UNIT
install -m 644 "$SRC"/grafana/provisioning/datasources/*.yml /etc/grafana/provisioning/datasources/
install -m 644 "$SRC"/grafana/provisioning/dashboards/*.yml /etc/grafana/provisioning/dashboards/
mkdir -p /var/lib/grafana/dashboards
install -m 644 "$SRC"/grafana/dashboards/*.json /var/lib/grafana/dashboards/
chown -R grafana:grafana /var/lib/grafana/dashboards
systemctl daemon-reload
systemctl enable grafana-server >/dev/null
systemctl restart grafana-server

echo "==> verify"
fail=0
check () { if eval "$2"; then echo "   ok    $1"; else echo "   FAIL  $1"; fail=1; fi; }
for i in $(seq 1 30); do curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1 && break; sleep 2; done
sleep 12   # let Prometheus complete at least one scrape of every target
TARGETS=$(curl -fsS http://127.0.0.1:9090/api/v1/targets) || TARGETS=""
check "Prometheus is ready" 'curl -fsS http://127.0.0.1:9090/-/ready >/dev/null'
check "job rules loaded" 'curl -fsS http://127.0.0.1:9090/api/v1/rules | grep -q job-workflow-contract'
check "Grafana is healthy" 'curl -fsS http://127.0.0.1:3000/api/health | grep -q "\"database\": *\"ok\""'
check "job dashboard is provisioned" 'curl -fsS http://127.0.0.1:3000/api/dashboards/uid/selfheal-jobs >/dev/null'
echo "Run tools/configure_jobs_monitor.py on the healer, then verify every active target."
echo "   info  grafana $(dpkg-query -W -f='${Version}' grafana), prometheus $(dpkg-query -W -f='${Version}' prometheus)"
[ "$fail" -eq 0 ] || { echo "monitor install finished with failures" >&2; exit 1; }
echo "==> monitor ready"
