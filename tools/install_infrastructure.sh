#!/usr/bin/env bash
# Dedicated lab services only. Never changes system DNS or distribution Redis.
set -euo pipefail
ROLE=${1:?usage: install_infrastructure.sh app-1|app-2}
HERE=$(cd "$(dirname "$0")" && pwd)
case "$ROLE" in app-1|app-2) ;; *) exit 2 ;; esac
IP=$(hostname -I)
case "$ROLE:$IP" in app-1:*10.1.1.60*|app-2:*10.1.1.61*) ;; *) echo 'Unexpected guest address' >&2; exit 1 ;; esac
sudo install -d -m 755 /etc/healer-stack /opt/healer-stack/reference
if [ "$ROLE" = app-2 ]; then
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends redis-server dnsmasq-base
  id healer-dns >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin healer-dns
  # Credentials are generated on the VM, never in the repository or output.
  sudo python3 - <<'PY'
import grp,json,os,secrets
from pathlib import Path
root=Path('/etc/healer-stack')
admin=root/'cache-admin-password';client=root/'cache-client.json'
if not admin.exists():admin.write_text(secrets.token_hex(32))
if not client.exists():client.write_text(json.dumps({'username':'canary','password':secrets.token_hex(32)}))
os.chmod(admin,0o600);os.chmod(client,0o600)
acl=root/'users.acl'
acl.write_text('user default on >'+admin.read_text().strip()+' ~* +@all\nuser canary on >'+json.loads(client.read_text())['password']+' ~healer:* +get +set +ping\n')
os.chown(acl,0,grp.getgrnam('redis').gr_gid);os.chmod(acl,0o640)
PY
  # A separate Redis instance, with no persistence and a strict memory bound.
  cat <<'EOF' | sudo tee /etc/healer-stack/redis.conf >/dev/null
bind 127.0.0.1 10.1.1.61
port 6380
protected-mode yes
aclfile /etc/healer-stack/users.acl
daemonize no
save ""
appendonly no
maxmemory 64mb
maxmemory-policy noeviction
EOF
  cat <<'EOF' | sudo tee /etc/healer-stack/dns.conf >/dev/null
port=1053
listen-address=127.0.0.1,10.1.1.61
bind-interfaces
no-resolv
no-hosts
address=/cache.lab.test/10.1.1.61
EOF
  sudo cp /etc/healer-stack/{dns,redis}.conf /opt/healer-stack/reference/
  for component in redis dns; do
    if [ "$component" = redis ]; then
      EXEC='/usr/bin/redis-server /etc/healer-stack/redis.conf'; USER=redis
    else
      EXEC='/usr/sbin/dnsmasq --keep-in-foreground --conf-file=/etc/healer-stack/dns.conf'; USER=healer-dns
    fi
    cat <<EOF | sudo tee /etc/systemd/system/healer-stack-$component.service >/dev/null
[Unit]
Description=Isolated self-healing experiment $component
After=network-online.target
[Service]
User=$USER
ExecStart=$EXEC
Restart=no
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
MemoryMax=160M
CPUQuota=30%
TasksMax=32
[Install]
WantedBy=multi-user.target
EOF
  done
  sudo systemctl daemon-reload
  sudo systemctl enable healer-stack-redis healer-stack-dns
  sudo systemctl restart healer-stack-redis healer-stack-dns
  ready=0
  for _ in $(seq 1 20); do
    if REDISCLI_AUTH=$(sudo cat /etc/healer-stack/cache-admin-password) redis-cli -h 127.0.0.1 -p 6380 PING 2>/dev/null | grep -qx PONG; then ready=1; break; fi
    sleep .2
  done
  [ "$ready" = 1 ] || { echo 'Redis did not become ready' >&2; exit 1; }
else
  id healer-stack >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin healer-stack
  sudo chown root:healer-stack /etc/healer-stack/cache-client.json
  sudo chmod 640 /etc/healer-stack/cache-client.json
  sudo install -d -o healer-stack -g healer-stack -m 750 /var/lib/healer-stack
  sudo touch /var/lib/healer-stack/checkpoint
  sudo chown healer-stack:healer-stack /var/lib/healer-stack/checkpoint
  sudo chmod 640 /var/lib/healer-stack/checkpoint
  sudo install -m 755 "$HERE/stack-host/transaction.py" /opt/healer-stack/transaction.py
  cat <<'EOF' | sudo tee /etc/systemd/system/healer-stack-transaction.service >/dev/null
[Unit]
Description=DNS Redis checkpoint synthetic transaction
After=network-online.target
[Service]
User=healer-stack
ExecStart=/usr/bin/python3 /opt/healer-stack/transaction.py
Restart=no
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/healer-stack
MemoryMax=96M
CPUQuota=30%
TasksMax=64
[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable healer-stack-transaction
  sudo systemctl restart healer-stack-transaction
  ready=0
  for _ in $(seq 1 20); do
    if curl --fail --max-time 5 http://10.1.1.60:8088/healthz; then ready=1; break; fi
    sleep .2
  done
  [ "$ready" = 1 ] || { echo 'Transaction did not become ready' >&2; exit 1; }
fi
echo "Infrastructure installed and checked on $ROLE"
