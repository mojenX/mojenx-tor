#!/usr/bin/env bash
set -e

# ================= CONFIG =================
APP_NAME="mojenX Tor Manager"
CMD_NAME="mojen-tor"
REPO_URL="https://github.com/mojenX/mojenx-tor.git"

INSTALL_DIR="/opt/mojenx-tor"
BIN_PATH="/usr/local/bin/${CMD_NAME}"

# ================= COLORS =================
G="\033[1;32m"; R="\033[1;31m"; Y="\033[1;33m"; C="\033[1;36m"; N="\033[0m"
ok()   { echo -e "${G}[✔️]${N} $1"; }
info() { echo -e "${C}[*]${N} $1"; }
warn() { echo -e "${Y}[!]${N} $1"; }
fail() { echo -e "${R}[✖️]${N} $1"; exit 1; }

# ================= ROOT CHECK =================
[ "$EUID" -ne 0 ] && fail "Run as root (sudo bash install.sh)"

# ================= OS CHECK =================
grep -qiE "debian|ubuntu" /etc/os-release || fail "Debian/Ubuntu only"

# ================= SYSTEM DEPS =================
info "Installing system dependencies"
apt update -y
apt install -y git curl python3 python3-pip python3-venv tor tor-geoipdb nyx
ok "System dependencies ready"

# ================= INSTALL / UPDATE PROMPT =================
info "Preparing ${APP_NAME}"
if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Existing installation found at ${INSTALL_DIR}"
    echo -e "${C}Choose action:${N} [U]pdate / [R]einstall / [C]ancel"
    read -r -p "Action (U/r/c): " _choice
    _choice="$(echo "${_choice:-U}" | tr '[:upper:]' '[:lower:]')"

    case "$_choice" in
        u|"")
            info "Updating existing installation"
            git -C "$INSTALL_DIR" pull --ff-only || fail "Git update failed"
            ;;
        r)
            info "Reinstalling fresh copy"
            rm -rf "$INSTALL_DIR"
            git clone "$REPO_URL" "$INSTALL_DIR" || fail "Clone failed"
            ;;
        c)
            warn "Installation cancelled by user"
            exit 0
            ;;
        *)
            fail "Invalid choice"
            ;;
    esac
else
    info "Cloning repository"
    git clone "$REPO_URL" "$INSTALL_DIR" || fail "Clone failed"
fi

# ================= CRLF FIX =================
info "Normalizing line endings (CRLF → LF)"
sed -i 's/\r$//' "$INSTALL_DIR/tor.py" || true

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

    ok "Tor configuration updated"
else
    warn "Tor configuration file not found at ${TORRC}"
fi

info "Restarting Tor service"
systemctl enable tor >/dev/null 2>&1 || true
systemctl restart tor || fail "Failed to restart Tor"
systemctl is-active --quiet tor && ok "Tor service is active" || fail "Tor service not active"

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

chmod +x "$INSTALL_DIR/tor.py"

# ================= LAUNCHER & LINK =================
info "Creating launcher"
WRAPPER="$INSTALL_DIR/${CMD_NAME}"
cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/.venv/bin/python" "$DIR/tor.py" "$@"
EOF

chmod +x "$WRAPPER"
ln -sf "$WRAPPER" "$BIN_PATH"
chmod +x "$BIN_PATH"
ok "Launcher installed at ${BIN_PATH}"

# ================= DONE =================
echo
ok "${APP_NAME} installed successfully"
echo -e "${G}Run:${N} ${C}${CMD_NAME}${N}"
echo -e "${Y}Note:${N} If this is your first install or you were added to 'debian-tor', log out/in for group changes to take effect."
