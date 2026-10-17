#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] && [ "$(hostname)" = probe-1 ]
install -d -m 755 /usr/local/libexec
cat > /usr/local/libexec/platform-gateway-route <<'EOF'
#!/bin/bash
set -euo pipefail
existing=$(ip -4 route show exact 10.203.0.2/32)
if [ -z "$existing" ]; then ip route add 10.203.0.2/32 via 10.1.1.82
else
    [ "$(ip -j -4 route show exact 10.203.0.2/32 | python3 -c 'import json,sys; print(json.load(sys.stdin)[0].get("gateway",""))')" = 10.1.1.82 ] || { echo 'Route conflict'; exit 1; }
fi
EOF
chmod 755 /usr/local/libexec/platform-gateway-route
cat > /etc/systemd/system/platform-gateway-route.service <<'EOF'
[Unit]
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/libexec/platform-gateway-route
RemainAfterExit=yes
EOF
cat > /etc/systemd/system/platform-gateway-observer.service <<'EOF'
[Unit]
Description=Independent nonce-checked HTTP client for the owned gateway
Requires=platform-gateway-route.service
After=platform-gateway-route.service
[Service]
Type=simple
User=ubuntu
Environment=PYTHONPATH=/opt/platform-healer/src
ExecStart=/usr/bin/python3 -m platform_healer.gateway_observer
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectHome=yes
ProtectSystem=strict
MemoryMax=64M
TasksMax=24
CPUQuota=15%
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now platform-gateway-observer
