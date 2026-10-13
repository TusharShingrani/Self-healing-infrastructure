#!/usr/bin/env bash
# Metrics agent for a lab instance. Run AFTER install_lab_host.sh:
#   sudo bash install_exporters.sh
#
# What it adds, all scraped by Prometheus on the monitor instance:
#   :9100  node_exporter   CPU, memory, filesystems (including the bounded log
#                          volume), systemd unit state for nginx and the lab units,
#                          and the healer-* facts from the textfile collector
#   :9113  nginx exporter  connections and requests, from stub_status on loopback
set -euo pipefail

echo "==> packages"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq --no-install-recommends \
    prometheus-node-exporter prometheus-nginx-exporter >/dev/null

echo "==> node_exporter: systemd and textfile collectors"
cat > /etc/default/prometheus-node-exporter <<'CONF'
ARGS="--collector.systemd --collector.systemd.unit-include=(nginx|healer-logflood|healer-logrotate)\.(service|timer) --collector.textfile.directory=/var/lib/prometheus/node-exporter"
CONF
systemctl restart prometheus-node-exporter

echo "==> nginx stub_status on loopback only"
# A separate file, so the healer.conf reference comparison is unaffected.
cat > /etc/nginx/conf.d/stub-status.conf <<'CONF'
server {
    listen 127.0.0.1:8080;
    location = /stub_status { stub_status; access_log off; }
}
CONF
nginx -t
systemctl reload nginx
cat > /etc/default/prometheus-nginx-exporter <<'CONF'
ARGS="-nginx.scrape-uri=http://127.0.0.1:8080/stub_status"
CONF
systemctl restart prometheus-nginx-exporter

echo "==> healer facts for the textfile collector, every 15 seconds"
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lab-host
install -m 755 "$SRC/healer-metrics" /usr/local/sbin/healer-metrics
cat > /etc/systemd/system/healer-metrics.service <<'UNIT'
[Unit]
Description=Publish lab facts for node_exporter
[Service]
Type=oneshot
EnvironmentFile=-/etc/systemd/system/healer-lab.env
ExecStart=/usr/local/sbin/healer-metrics
UNIT
cat > /etc/systemd/system/healer-metrics.timer <<'UNIT'
[Unit]
Description=Publish lab facts frequently
[Timer]
OnBootSec=5s
OnUnitActiveSec=15s
AccuracySec=1s
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now healer-metrics.timer
systemctl start healer-metrics.service

echo "==> verify"
fail=0
check () { if eval "$2"; then echo "   ok    $1"; else echo "   FAIL  $1"; fail=1; fi; }
sleep 2
# Fetch once and search the copy. Piping curl into grep -q under pipefail
# fails when grep exits early on a match and curl gets a broken pipe.
NODE=$(curl -fsS http://127.0.0.1:9100/metrics) || NODE=""
NGINX=$(curl -fsS http://127.0.0.1:9113/metrics) || NGINX=""
check "node_exporter answers" '[ -n "$NODE" ]'
check "the log volume is exported" \
      'grep -q "node_filesystem_avail_bytes{.*mountpoint=\"/var/log/nginx\"" <<<"$NODE"'
check "nginx unit state is exported" \
      'grep -q "node_systemd_unit_state{name=\"nginx.service\",state=\"active\".*} 1" <<<"$NODE"'
check "healer facts are exported and good" 'grep -qx "healer_config_correct 1" <<<"$NODE"'
check "nginx exporter answers" 'grep -q "^nginx_up 1" <<<"$NGINX"'
check "health endpoint still answers" 'curl -fsS http://127.0.0.1/healthz | grep -qx ok'
[ "$fail" -eq 0 ] || { echo "exporter install finished with failures" >&2; exit 1; }
echo "==> exporters ready"
