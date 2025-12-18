#!/usr/bin/env bash
set -Eeuo pipefail

# ====================== META ======================
APP_NAME="mojenX Tor Manager"
BIN_NAME="mojen-tor"
REPO_URL="https://github.com/mojenX/mojenx-tor.git"

INSTALL_DIR="$HOME/.local/share/mojenx-tor"
BIN_DIR="$HOME/.local/bin"
PY_ENTRY="tor.py"

# ====================== COLORS ======================
C_RESET="\033[0m"
C_RED="\033[1;31m"
C_GREEN="\033[1;32m"
C_YELLOW="\033[1;33m"
C_CYAN="\033[1;36m"

log()   { echo -e "${C_CYAN}[*]${C_RESET} $1"; }
ok()    { echo -e "${C_GREEN}[✔]${C_RESET} $1"; }
warn()  { echo -e "${C_YELLOW}[!]${C_RESET} $1"; }
fail()  { echo -e "${C_RED}[✖]${C_RESET} $1"; exit 1; }

# ====================== OS CHECK ======================
if ! grep -qiE "debian|ubuntu" /etc/os-release; then
    fail "Only Debian / Ubuntu supported"
fi

# ====================== REQUIRE ======================
require() {
    local cmd="$1"
    local pkg="$2"

    if ! command -v "$cmd" >/dev/null 2>&1; then
        warn "Installing dependency: $pkg"
        apt-get update -y
        apt-get install -y "$pkg" || fail "Failed to install $pkg"
    fi
}

# ====================== ROOT CHECK ======================
if [[ $EUID -ne 0 ]]; then
    fail "Run installer as root (sudo)"
fi

# ====================== SYSTEM DEPS ======================
log "Checking system dependencies"
require curl curl
require git git
require python3 python3
require pip3 python3-pip
require tor tor
ok "System dependencies OK"

# ====================== PYTHON DEPS ======================
log "Installing Python dependencies"
python3 -m pip install --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install --user requests[socks] || fail "pip install failed"
ok "Python dependencies OK"

# ====================== INSTALL APP ======================
log "Installing $APP_NAME"

mkdir -p "$INSTALL_DIR"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    warn "Existing install found – updating"
    git -C "$INSTALL_DIR" pull || fail "Git pull failed"
else
    git clone "$REPO_URL" "$INSTALL_DIR" || fail "Git clone failed"
fi

# ====================== PERMISSIONS ======================
chmod +x "$INSTALL_DIR/$PY_ENTRY" || fail "chmod failed"

# ====================== SYMLINK ======================
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/$PY_ENTRY" "$BIN_DIR/$BIN_NAME"

# ====================== PATH ======================
if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    warn "$BIN_DIR not in PATH"
    echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$HOME/.bashrc"
    ok "PATH updated (run: source ~/.bashrc)"
fi

# ====================== TOR ENABLE ======================
log "Enabling Tor service"
systemctl enable tor >/dev/null 2>&1 || true
systemctl start tor >/dev/null 2>&1 || true

# ====================== DONE ======================
ok "$APP_NAME installed successfully"
echo
echo -e "${C_GREEN}Run:${C_RESET} ${C_CYAN}$BIN_NAME${C_RESET}"
