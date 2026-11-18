#!/usr/bin/env bash
# One-time setup for Ubuntu 22.04/24.04 (native, VM, or WSL2).
# Installs: Docker Engine + compose plugin, Nomad, PyYAML, make, jq, curl.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Installing Docker Engine"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "!! Log out and back in (or run 'newgrp docker') so docker works without sudo."
fi

if ! command -v nomad >/dev/null 2>&1; then
  echo ">> Installing Nomad from the HashiCorp apt repo"
  sudo apt-get update -y
  sudo apt-get install -y gnupg lsb-release wget
  wget -qO- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y nomad
fi

echo ">> Installing helpers"
sudo apt-get install -y python3 python3-yaml make jq curl git

echo
echo "Versions:"
docker --version
docker compose version
nomad version
python3 -c "import yaml; print('PyYAML', yaml.__version__)"
echo
echo "All set. Next: make up   (then 'make nomad' in a second terminal)"
