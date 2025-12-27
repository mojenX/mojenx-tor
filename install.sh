#!/usr/bin/env bash
set -e

# ================= CONFIG =================
APP_NAME="mojenX Tor Manager"
CMD_NAME="mojen-tor"
REPO_URL="https://github.com/mojenX/mojenx-tor.git"

INSTALL_DIR="/opt/mojenx-tor"
SCRIPT_NAME="mojen-tor.py"
BIN_PATH="/usr/local/bin/${CMD_NAME}"

# ================= COLORS =================
G="\033[1;32m"; R="\033[1;31m"; Y="\033[1;33m"; C="\033[1;36m"; N="\033[0m"
ok()   { echo -e "${G}[✔️]${N} $1"; }
info() { echo -e "${C}[*]${N} $1"; }
warn() { echo -e "${Y}[!]${N} $1"; }
fail() { echo -e "${R}[✖️]${N} $1"; exit 1; }

# ================= ROOT & OS CHECK =================
[ "$EUID" -ne 0 ] && fail "Run as root (sudo bash install.sh)"
grep -qiE "debian|ubuntu" /etc/os-release || fail "Debian/Ubuntu only"

# Resolve path of this installer (used to copy local mojen-tor.py if needed)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ================= AUTO-DETECT EXISTING INSTALLATION =================
if [ -f "$INSTALL_DIR/$SCRIPT_NAME" ] && [ -x "$INSTALL_DIR/$SCRIPT_NAME" ]; then
    info "Existing installation detected at ${INSTALL_DIR}. Opening ${APP_NAME}..."
    if [ -x "$BIN_PATH" ]; then
        exec "$BIN_PATH"
    else
        # Fallback direct run
        if [ -x "$INSTALL_DIR/.venv/bin/python" ]; then
            exec "$INSTALL_DIR/.venv/bin/python" -u "$INSTALL_DIR/$SCRIPT_NAME"
        else
            exec python3 -u "$INSTALL_DIR/$SCRIPT_NAME"
        fi
    fi
fi

# ================= SYSTEM DEPS =================
info "Installing system dependencies"
apt update -y
apt install -y git curl python3 python3-pip python3-venv tor tor-geoipdb nyx
ok "System dependencies ready"

# ================= FETCH OR PREPARE APP DIR =================
info "Preparing ${APP_NAME} files at ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"

# Try cloning repository; if it fails or does not contain our script, copy local one
if [ ! -d "$INSTALL_DIR/.git" ]; then
    info "Cloning repository (best-effort)"
    if git clone "$REPO_URL" "$INSTALL_DIR"; then
        ok "Repository cloned"
    else
        warn "Clone failed. Proceeding with local files."
    fi
fi

# If mojen-tor.py doesn't exist in INSTALL_DIR, copy from local directory
if [ ! -f "$INSTALL_DIR/$SCRIPT_NAME" ] && [ -f "$SCRIPT_DIR/$SCRIPT_NAME" ]; then
    cp -f "$SCRIPT_DIR/$SCRIPT_NAME" "$INSTALL_DIR/$SCRIPT_NAME"
    ok "Copied ${SCRIPT_NAME} from local directory"
fi

# Normalize line endings just in case
info "Normalizing line endings (CRLF → LF)"
sed -i 's/\r$//' "$INSTALL_DIR/$SCRIPT_NAME" || true

# ================= PYTHON ENV & LIBS =================
info "Setting up Python virtual environment"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    python3 -m venv "$INSTALL_DIR/.venv" || fail "Failed to create venv"
    ok "Virtual environment created"
else
    info "Virtual environment already exists – reusing"
fi

info "Installing Python libraries (rich, requests, stem)"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$INSTALL_DIR/.venv/bin/pip" install -U rich requests stem || fail "Failed to install Python dependencies"
ok "Python libraries installed"

# ================= TOR CONFIG =================
TORRC="/etc/tor/torrc"
TOR_COOKIE="/run/tor/control.authcookie"
if [ -f "$TORRC" ]; then
    info "Configuring Tor ControlPort and CookieAuthentication"
    cp -n "$TORRC" "$TORRC.bak.$(date +%Y%m%d%H%M%S)" || true

    # Ensure ControlPort 9051
    if grep -qE '^\s*ControlPort\b' "$TORRC"; then
        sed -i 's/^\s*#\s*ControlPort.*/ControlPort 9051/' "$TORRC"
        sed -i 's/^\s*ControlPort.*/ControlPort 9051/' "$TORRC"
    else
        echo "ControlPort 9051" >> "$TORRC"
    fi

    # Ensure CookieAuthentication 1
    if grep -qE '^\s*CookieAuthentication\b' "$TORRC"; then
        sed -i 's/^\s*#\s*CookieAuthentication.*/CookieAuthentication 1/' "$TORRC"
        sed -i 's/^\s*CookieAuthentication.*/CookieAuthentication 1/' "$TORRC"
    else
        echo "CookieAuthentication 1" >> "$TORRC"
    fi

    # Ensure cookie is group-readable for debian-tor users
    if ! grep -qE '^\s*CookieAuthFileGroupReadable\b' "$TORRC"; then
        echo "CookieAuthFileGroupReadable 1" >> "$TORRC"
    else
        sed -i 's/^\s*#\s*CookieAuthFileGroupReadable.*/CookieAuthFileGroupReadable 1/' "$TORRC"
        sed -i 's/^\s*CookieAuthFileGroupReadable.*/CookieAuthFileGroupReadable 1/' "$TORRC"
    fi

    # Prefer default cookie path but enforce if missing
    if ! grep -qE '^\s*CookieAuthFile\b' "$TORRC"; then
        echo "CookieAuthFile ${TOR_COOKIE}" >> "$TORRC"
    fi

    ok "Tor configuration updated"
else
    warn "Tor configuration file not found at ${TORRC}"
fi

info "Managing Tor service (systemd optional)"
if command -v systemctl >/dev/null 2>&1; then
    systemctl enable tor >/dev/null 2>&1 || true
    systemctl restart tor || warn "Failed to restart Tor via systemctl (the Manager can manage it)"
    if systemctl is-active --quiet tor; then
        ok "Tor service is active"
    else
        warn "Tor service not active (interactive Manager can manage it)"
    fi
else
    warn "systemctl not available. Skipping service management. The interactive Manager can start/stop Tor directly."
fi

# ================= PERMISSIONS & GROUP =================
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
if id -nG "$TARGET_USER" 2>/dev/null | grep -qw debian-tor; then
    info "User '${TARGET_USER}' is already in the 'debian-tor' group"
else
    info "Adding user '${TARGET_USER}' to 'debian-tor' group"
    usermod -aG debian-tor "$TARGET_USER" || warn "Failed to add '${TARGET_USER}' to 'debian-tor' (you may add manually)"
    ok "Group membership updated for '${TARGET_USER}'"
    warn "You may need to log out and back in for group changes to take effect"
fi

# Try to make the cookie group-readable immediately
if [ -f "$TOR_COOKIE" ]; then
    chgrp debian-tor "$TOR_COOKIE" >/dev/null 2>&1 || true
    chmod g+r "$TOR_COOKIE" >/dev/null 2>&1 || true
fi

chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

# ================= LAUNCHER & LINK =================
info "Creating launcher at ${BIN_PATH}"
WRAPPER="$BIN_PATH"
cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/mojenx-tor"
SCRIPT="$APP_DIR/mojen-tor.py"
VENV_PY="$APP_DIR/.venv/bin/python"

# Diagnostics to avoid silent failures
if [ ! -f "$SCRIPT" ]; then
    echo "[ERROR] $SCRIPT not found. Verify the repository contents in $APP_DIR."
    exit 1
fi

# Prefer venv Python, else fall back to system python
if [ -x "$VENV_PY" ]; then
    exec "$VENV_PY" -u "$SCRIPT" "$@"
else
    command -v python3 >/dev/null 2>&1 || { echo "[ERROR] python3 not found in PATH"; exit 1; }
    exec python3 -u "$SCRIPT" "$@"
fi
EOF

chmod +x "$WRAPPER"
ok "Launcher installed at ${BIN_PATH}"

# ================= DONE — OPEN UI =================
echo
ok "${APP_NAME} installed successfully"
echo -e "${G}Run:${N} ${C}${CMD_NAME}${N}"
echo -e "${Y}Note:${N} If this is your first install or you were added to 'debian-tor', log out/in for group changes to take effect."
echo
info "Opening ${APP_NAME}..."
exec "$WRAPPER"
