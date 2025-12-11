#!/bin/bash
set -euo pipefail

WORKDIR="/tmp/mojenx_install_$(date +%s)"
BIN="/usr/local/bin/mojenx-tor"
ENV_FILE="/etc/default/mojenx-tor"
SERVICE="/etc/systemd/system/mojenx-tor.service"
REPO_RAW_BASE="https://raw.githubusercontent.com/mojenX/mojenx-tor/main"

echo ">>> mojenX automated installer"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

if ! command -v go >/dev/null 2>&1; then
  echo ">>> Installing Go..."
  apt-get update -y
  apt-get install -y golang-go ca-certificates curl openssl xxd build-essential
fi

echo ">>> Downloading source..."
curl -fsSL "$REPO_RAW_BASE/main.go" -o main.go
curl -fsSL "$REPO_RAW_BASE/go.mod" -o go.mod

echo ">>> Building..."
export GOPROXY=https://proxy.golang.org
go mod tidy >/dev/null
go build -o mojenx-tor main.go

echo ">>> Installing binary..."
mv mojenx-tor "$BIN"
chmod 755 "$BIN"

TOKEN=$(openssl rand -hex 16 2>/dev/null || head -c16 /dev/urandom | xxd -p)
mkdir -p /etc/default
cat > "$ENV_FILE" <<EOF
MOJENX_TOKEN=$TOKEN
EOF
chmod 600 "$ENV_FILE"

echo ">>> Installing service..."
curl -fsSL "$REPO_RAW_BASE/mojenx-tor.service" -o "$SERVICE"
chmod 644 "$SERVICE"

systemctl daemon-reload
systemctl enable --now mojenx-tor.service

echo
echo ">>> Installation complete!"
echo "API token stored in $ENV_FILE (permissions 600)"
echo
echo "Service status (brief):"
systemctl status mojenx-tor.service --no-pager
echo
echo "Example usage:"
echo "  curl -H \"Authorization: Bearer $TOKEN\" http://127.0.0.1:8080/api/v1/status"
echo
rm -rf "$WORKDIR"
