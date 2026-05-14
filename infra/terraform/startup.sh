#!/usr/bin/env bash
# GCE VM startup script. Installs Docker, the Ops Agent, and a placeholder
# systemd unit. The CI deploy job (deploy-vm.yml) drops compose files +
# secrets and runs `systemctl enable --now trading-stack`.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  ca-certificates curl gnupg lsb-release \
  python3 python3-pip \
  jq

# Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list >/dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Ops Agent for Cloud Logging + Monitoring
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
bash add-google-cloud-ops-agent-repo.sh --also-install

# Kernel tuning for latency
cat <<'EOF' >>/etc/sysctl.d/99-trade.conf
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864
net.ipv4.tcp_low_latency = 1
net.ipv4.tcp_no_metrics_save = 1
EOF
sysctl --system

# Disable CPU frequency scaling (keep CPUs at performance governor)
if [ -d /sys/devices/system/cpu/cpu0/cpufreq ]; then
  for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance >"$f" || true
  done
fi

# Working dirs
mkdir -p /opt/trade/{config,secrets,compose}
chown -R root:docker /opt/trade
chmod 750 /opt/trade/secrets

echo "Startup complete. Awaiting CI deploy to drop compose + secrets."
