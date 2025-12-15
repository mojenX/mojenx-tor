#!/usr/bin/env bash
set -euo pipefail

# ================= CONFIG =================
PROJECT_NAME="mojenX Tor Manager"
BIN_NAME="mojenx-tor"
REPO_URL="https://github.com/mojenX/mojenx-tor.git"

INSTALL_DIR="$HOME/.local/share/mojenx-tor"
BIN_DIR="$HOME/.local/bin"

# ================= COLORS =================
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
CYAN="\033[1;36m"
RESET="\033[0m"

log()  { echo -e "${CYAN}[+]${RESET} $1"; }
ok()   { echo -e "${GREEN}[✔]${RESET} $1"; }
warn() { echo -e "${YELLOW}[!]${RESET} $1"; }
fail() { echo -e "${RED}[✖]${RESET} $1"; exit 1; }

# ================= OS CHECK =================
if ! grep -qiE "debian|ubuntu" /etc/os-release; then
    fail "Unsupported OS. Debian / Ubuntu only."
fi

# ================= REQUIREMENTS =================
for cmd in git python3 pip3 curl; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done

# ================= SYSTEM DEPS =================
log "Installing system dependencies (tor, python)"
sudo apt update -y || fail "apt update failed"
sudo apt install -y tor tor-geoipdb python3 python3-pip || fail "apt install failed"
ok "System dependencies installed"

# ================= PYTHON DEPS =================
log "Installing Python dependencies"
pip3 install --user --upgrade requests[socks] || fail "pip install failed"
ok "Python dependencies installed"

# ================= PROJECT INSTALL =================
log "Installing $PROJECT_NAME"

mkdir -p "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Existing installation found — updating"
    git -C "$INSTALL_DIR" pull || fail "git pull failed"
else
    git clone "$REPO_URL" "$INSTALL_DIR" || fail "git clone failed"
fi

# ================= COMMAND SETUP =================
mkdir -p "$BIN_DIR"
chmod +x "$INSTALL_DIR/goz.py"
ln -sf "$INSTALL_DIR/goz.py" "$BIN_DIR/$BIN_NAME"

# ================= PATH SETUP =================
if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    warn "$BIN_DIR not in PATH"
    echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$HOME/.bashrc"
    ok "PATH updated (restart shell or run: source ~/.bashrc)"
fi

# ================= DONE =================
ok "$PROJECT_NAME installed successfully"
echo
echo -e "${GREEN}Run:${RESET} ${CYAN}mojenx${RESET}"
