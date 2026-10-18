#!/bin/bash
# Explicit administrator bootstrap on the owned lab canary only.
set -euo pipefail
[ "$(id -u)" = 0 ] && [ "$(hostname)" = k8s-worker-2 ]
bash /opt/platform-healer/host/install-broker.sh
[ "$(sysctl -n net.ipv4.ip_forward)" = 1 ] || { echo 'Existing platform forwarding capability required'; exit 1; }
if ! command -v haproxy >/dev/null; then
    apt-get -o DPkg::Lock::Timeout=120 update -qq
    DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=120 install -y -qq haproxy
    systemctl disable --now haproxy
fi
install -d -m 700 /etc/platform-healer /var/lib/platform-healer
install -d -m 755 /run/platform-healer /etc/platform-gateway
install -d -m 770 -o haproxy -g haproxy /run/platform-healer/gateway
getent group platform-healer >/dev/null || groupadd --gid 64532 platform-healer
if [ ! -f /etc/platform-healer/node.key ]; then (umask 077; head -c 32 /dev/urandom > /etc/platform-healer/node.key); fi
if ! ip netns list | awk '{print $1}' | grep -qx platform-healer-gateway; then
    ! ip link show ph-gw-host >/dev/null 2>&1 || { echo 'Interface name conflict'; exit 1; }
    ip netns add platform-healer-gateway
    ip link add ph-gw-host type veth peer name ph-gw-peer
    ip link set ph-gw-peer netns platform-healer-gateway
    ip addr add 10.203.0.1/30 dev ph-gw-host
    ip -n platform-healer-gateway addr add 10.203.0.2/30 dev ph-gw-peer
    ip netns exec platform-healer-gateway sysctl -qw net.ipv4.ip_local_port_range='40000 40031'
fi
[ "$(ip netns exec platform-healer-gateway sysctl -n net.ipv4.ip_local_port_range | xargs)" = '40000 40031' ] || { echo 'Drain load and reconcile the existing lease to baseline before provisioning gateway identity'; exit 1; }
[ "$(ip -n platform-healer-gateway -j addr show ph-gw-peer | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["addr_info"][0]["local"])')" = 10.203.0.2 ]
ip link set ph-gw-host up
ip -n platform-healer-gateway link set ph-gw-peer up
ip -n platform-healer-gateway link set lo up
ip -n platform-healer-gateway route replace 10.1.1.84/32 via 10.203.0.1
# Dedicated chain affects only packets to/from this owned veth; never flush CNI rules.
iptables -N PLATFORM-GATEWAY 2>/dev/null || true
iptables -C PLATFORM-GATEWAY -s 10.1.1.84/32 -d 10.203.0.2/32 -p tcp --dport 18080 -j ACCEPT 2>/dev/null || iptables -A PLATFORM-GATEWAY -s 10.1.1.84/32 -d 10.203.0.2/32 -p tcp --dport 18080 -j ACCEPT
iptables -C PLATFORM-GATEWAY -s 10.203.0.2/32 -d 10.1.1.84/32 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || iptables -A PLATFORM-GATEWAY -s 10.203.0.2/32 -d 10.1.1.84/32 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -C PLATFORM-GATEWAY -j REJECT 2>/dev/null || iptables -A PLATFORM-GATEWAY -j REJECT
for direction in in out; do
    if [ "$direction" = in ]; then flag=-i; else flag=-o; fi
    iptables -C FORWARD "$flag" ph-gw-host -j PLATFORM-GATEWAY 2>/dev/null || iptables -I FORWARD 1 "$flag" ph-gw-host -j PLATFORM-GATEWAY
done
cat > /etc/platform-gateway/gateway.cfg <<'EOF'
global
    maxconn 128
    nbthread 1
    stats socket /run/platform-healer/gateway/haproxy.sock mode 600 level user
defaults
    mode http
    timeout connect 500ms
    timeout client 50s
    timeout server 50s
    retries 0
    option http-server-close
    option abortonclose
frontend gateway
    bind 10.203.0.2:18080
    bind /run/platform-healer/gateway/frontend.sock mode 660
    default_backend upstream
backend upstream
    http-reuse never
    server responder 127.0.0.1:19080 maxconn 100
EOF
haproxy -c -f /etc/platform-gateway/gateway.cfg
for kind in upstream proxy; do
    if [ "$kind" = upstream ]; then name=platform-gateway-upstream; command='/usr/bin/python3 -m platform_healer.gateway_upstream'; else name=platform-gateway; command='/usr/sbin/haproxy -db -f /etc/platform-gateway/gateway.cfg'; fi
    cat > "/etc/systemd/system/$name.service" <<EOF
[Unit]
Description=Owned HAProxy gateway $kind
After=network.target
[Service]
Type=simple
User=haproxy
Group=haproxy
NetworkNamespacePath=/run/netns/platform-healer-gateway
Environment=PYTHONPATH=/opt/platform-healer/src
ExecStart=$command
Restart=on-failure
RestartSec=2
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/run/platform-healer/gateway
MemoryMax=192M
TasksMax=160
CPUQuota=30%
LimitNOFILE=4096
EOF
done
systemctl daemon-reload
systemctl start platform-gateway-upstream platform-gateway
sleep 1
python3 - <<'PY'
import hashlib,json,os,pwd,subprocess
from pathlib import Path
pid=int(subprocess.check_output(['systemctl','show','platform-gateway','-p','MainPID','--value']))
assert pid>1
start=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
registry=Path('/run/platform-healer/gateway-identity.json')
registry.write_text(json.dumps({'pid':pid,'start_time':start}))
os.chown(registry,0,0);registry.chmod(0o600)
spec={'id':'gateway-ports','kind':'gateway_ports','namespace':'platform-healer-gateway',
 'namespace_inode':os.stat('/run/netns/platform-healer-gateway').st_ino,'uid':pwd.getpwnam('haproxy').pw_uid,
 'baseline':[40000,40031],'expanded':[40000,40255], 'minimum_memory_bytes':268435456,
 'minimum_memory_ratio':.15,'cooldown_seconds':5,
 'executable_sha256':hashlib.sha256(Path('/usr/sbin/haproxy').read_bytes()).hexdigest(),
 'config_sha256':hashlib.sha256(Path('/etc/platform-gateway/gateway.cfg').read_bytes()).hexdigest()}
policy=Path('/etc/platform-healer/policy.json');policy.write_text(json.dumps({'targets':[spec]}));policy.chmod(0o600)
PY
systemctl restart platform-healer-broker
cat > /etc/systemd/system/platform-gateway-bootstrap.service <<'EOF'
[Unit]
Description=Recreate owned gateway namespace and pinned identity after boot
Wants=network-online.target
After=network-online.target k3s-agent.service
[Service]
Type=oneshot
ExecStart=/bin/bash /opt/platform-healer/host/bootstrap-gateway.sh --boot
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable platform-gateway-bootstrap
echo 'Owned HAProxy gateway and fixed namespace policy ready'
