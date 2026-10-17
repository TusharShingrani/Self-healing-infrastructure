#!/bin/bash
# Explicit lab-only bootstrap: execute on the positively identified worker-2.
set -euo pipefail
[ "$(id -u)" = 0 ]
[ "$(hostname)" = k8s-worker-2 ] || { echo 'Refusing non-canary host'; exit 1; }
[ -f /opt/platform-healer/src/platform_healer/broker.py ]
command -v ip >/dev/null
install -d -m 700 /etc/platform-healer /var/lib/platform-healer
install -d -m 755 /run/platform-healer
getent group platform-healer >/dev/null || groupadd --gid 64532 platform-healer
if [ ! -f /etc/platform-healer/node.key ]; then
    umask 077
    head -c 32 /dev/urandom > /etc/platform-healer/node.key
fi
# Never alter the host network namespace. This namespace has loopback only.
if ! ip netns list | awk '{print $1}' | grep -qx platform-healer-ports; then
    ip netns add platform-healer-ports
    ip netns exec platform-healer-ports sysctl -qw net.ipv4.ip_local_port_range='40000 40031'
else
    [ "$(ip netns exec platform-healer-ports sysctl -n net.ipv4.ip_local_port_range | xargs)" = '40000 40031' ] || { echo 'Drain and roll back the existing experiment first'; exit 1; }
fi
ip -n platform-healer-ports link set lo up
python3 - <<'PY'
import json,os
from pathlib import Path
policy={'targets':[
 {'id':'ports-canary','kind':'ports','namespace':'platform-healer-ports',
  'namespace_inode':os.stat('/run/netns/platform-healer-ports').st_ino,
  'baseline':[40000,40031],'expanded':[40000,40255]},
 {'id':'descriptors-canary','kind':'descriptors','baseline':64,'expanded':256,'hard_ceiling':512}]}
p=Path('/etc/platform-healer/policy.json');p.write_text(json.dumps(policy));p.chmod(0o600)
PY
for kind in ports descriptors; do
    prefix=''
    [ "$kind" != ports ] || prefix='/usr/sbin/ip netns exec platform-healer-ports '
    cat > "/etc/systemd/system/platform-fixture-$kind.service" <<EOF
[Unit]
Description=Bounded platform healer $kind infrastructure fixture
After=network.target
[Service]
Type=simple
Environment=PYTHONPATH=/opt/platform-healer/src
ExecStart=${prefix}/usr/bin/python3 -m platform_healer.fixtures $kind --seconds 900 --persistent
Restart=no
MemoryMax=128M
TasksMax=32
CPUQuota=15%
NoNewPrivileges=yes
EOF
done
cat > /etc/systemd/system/platform-healer-broker.service <<'EOF'
[Unit]
Description=Platform healer fixed-operation canary broker (lab only)
After=network.target
[Service]
Type=simple
Environment=PYTHONPATH=/opt/platform-healer/src
ExecStart=/usr/bin/python3 -m platform_healer.broker
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/run/platform-healer /var/lib/platform-healer
# SYS_ADMIN is necessary for setns into the isolated lab network namespace.
# This is explicitly not a production general-purpose privilege grant.
CapabilityBoundingSet=CAP_SYS_ADMIN CAP_SYS_RESOURCE CAP_NET_ADMIN CAP_CHOWN CAP_DAC_OVERRIDE
MemoryMax=128M
TasksMax=32
CPUQuota=20%
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl start platform-fixture-ports platform-fixture-descriptors
systemctl enable --now platform-healer-broker
systemctl is-active platform-healer-broker platform-fixture-ports platform-fixture-descriptors
