#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="mojenX Tor Manager"
BIN_NAME="mojen-tor"
REPO_URL="https://github.com/mojenX/mojenx-tor.git"

INSTALL_DIR="$HOME/.local/share/mojenx-tor"
BIN_DIR="$HOME/.local/bin"

GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
CYAN="\033[1;36m"
RESET="\033[0m"

log()  { echo -e "${CYAN}[*]${RESET} $1"; }
ok()   { echo -e "${GREEN}[✔]${RESET} $1"; }
warn() { echo -e "${YELLOW}[!]${RESET} $1"; }
fail() { echo -e "${RED}[✖]${RESET} $1"; exit 1; }

grep -qiE "debian|ubuntu" /etc/os-release || fail "Debian/Ubuntu only"

require() {
    command -v "$1" >/dev/null 2>&1 && return
    warn "Installing missing dependency: $1"
    sudo apt-get update -y
    sudo apt-get install -y "$2"
}

require curl curl
require git git
require python3 python3
require pip3 python3-pip

sudo apt-get install -y tor tor-geoipdb

pip3 install --user --upgrade requests[socks]

mkdir -p "$INSTALL_DIR"
git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || git -C "$INSTALL_DIR" pull

mkdir -p "$BIN_DIR"
chmod +x "$INSTALL_DIR/tor.py"
ln -sf "$INSTALL_DIR/tor.py" "$BIN_DIR/$BIN_NAME"

echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.bashrc

ok "Installed successfully"
echo -e "${GREEN}Run:${RESET} ${CYAN}mojen-tor${RESET}"
