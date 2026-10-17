#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] && [ "$(hostname)" = k8s-worker-2 ]
install -d -m 700 /etc/platform-healer /var/lib/platform-healer
install -d -m 755 /run/platform-healer
getent group platform-healer >/dev/null || groupadd --gid 64532 platform-healer
if [ ! -f /etc/platform-healer/node.key ]; then (umask 077; head -c 32 /dev/urandom > /etc/platform-healer/node.key); fi
cat > /etc/systemd/system/platform-healer-broker.service <<'EOF'
[Unit]
Description=Platform healer fixed-operation gateway broker
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
# SYS_ADMIN enters only the pinned owned namespace. SYS_PTRACE permits /proc
# identity inspection of the non-root HAProxy process; no ptrace API is exposed.
# SYS_RESOURCE/SYS_NICE are absent from the gateway release.
CapabilityBoundingSet=CAP_SYS_ADMIN CAP_NET_ADMIN CAP_SYS_PTRACE CAP_CHOWN CAP_DAC_OVERRIDE
MemoryMax=128M
TasksMax=32
CPUQuota=30%
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable platform-healer-broker
