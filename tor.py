#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
mojenX Tor Manager
Debian / Ubuntu VPS
Author: mojenX
License: MIT
"""

from __future__ import annotations

import os
import sys
import time
import shutil
import socket
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

try:
    import requests
except Exception:
    requests = None

# ========================= CONSTANTS =========================

TORRC = Path("/etc/tor/torrc")
BACKUP_DIR = Path("/var/backups/mojenx")
DEFAULT_SOCKS = 9050

VALID_COUNTRY_CODES = {
    "tr": "Turkey",
    "de": "Germany",
    "us": "United States",
    "fr": "France",
    "uk": "United Kingdom",
    "at": "Austria",
    "be": "Belgium",
    "ro": "Romania",
    "ca": "Canada",
    "sg": "Singapore",
    "jp": "Japan",
    "ie": "Ireland",
    "fi": "Finland",
    "es": "Spain",
    "pl": "Poland",
}

# ========================= COLORS =========================

class C:
    B = "\033[1m"
    G = "\033[1;32m"
    Y = "\033[1;33m"
    R = "\033[1;31m"
    C = "\033[1;36m"
    D = "\033[2m"
    N = "\033[0m"

# ========================= UI =========================

def hr():
    print(f"{C.D}{'-' * 46}{C.N}")

def ok(msg):
    print(f"{C.G}✔ {msg}{C.N}")

def warn(msg):
    print(f"{C.Y}⚠ {msg}{C.N}")

def err(msg):
    print(f"{C.R}✖ {msg}{C.N}")

def prompt(msg):
    return input(f"{C.C}➜ {msg}{C.N} ").strip()

def pause():
    input(f"{C.D}Press Enter to continue...{C.N}")

def banner():
    print(
        C.C + C.B + r"""
                      _           _  __
   ____ ___  ____    (_)__  ____ | |/ /
  / __ `__ \/ __ \  / / _ \/ __ \|   /
 / / / / / / /_/ / / /  __/ / / /   |
/_/ /_/ /_/\____/_/ /\___/_/ /_/_/|_|
               /___/

            mojenX · tor manager
""" + C.N
    )

# ========================= UTILS =========================

def run(cmd, **kw):
    return subprocess.run(cmd, text=True, **kw)

def which(cmd):
    return shutil.which(cmd)

def is_root():
    return os.geteuid() == 0

def require_root():
    if not is_root():
        warn("Run as root (sudo required)")
        return False
    return True

# ========================= SERVICE =========================

def tor_service_name():
    if which("systemctl"):
        r = run(
            ["systemctl", "list-units", "--type=service", "--no-pager"],
            capture_output=True,
        )
        if "tor@default.service" in r.stdout:
            return "tor@default"
    return "tor"

SERVICE = tor_service_name()

def svc(action):
    if which("systemctl"):
        run(["systemctl", action, SERVICE], check=False)
    else:
        run(["service", SERVICE, action], check=False)

def start():
    require_root() and svc("start")

def stop():
    require_root() and svc("stop")

def restart():
    require_root() and svc("restart")

def reload():
    require_root() and svc("reload")

def status():
    r = run(
        ["systemctl", "status", SERVICE]
        if which("systemctl")
        else ["service", SERVICE, "status"],
        capture_output=True,
    )
    print(r.stdout)

# ========================= TORRC =========================

def backup(path: Path):
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, BACKUP_DIR / f"{path.name}.{ts}.bak")

def atomic_write(path: Path, lines: List[str]):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    if path.exists():
        backup(path)
        os.chmod(tmp, path.stat().st_mode)
    os.replace(tmp, path)

def read_torrc() -> Tuple[int, str, List[str]]:
    socks = DEFAULT_SOCKS
    exitnodes = ""
    try:
        lines = TORRC.read_text().splitlines()
    except FileNotFoundError:
        return socks, exitnodes, []

    for l in lines:
        t = l.strip()
        if t.startswith("SocksPort"):
            try:
                socks = int(t.split()[1])
            except Exception:
                pass
        elif t.startswith("ExitNodes"):
            exitnodes = t.split(" ", 1)[1]

    return socks, exitnodes, lines

def write_torrc(port=None, exitnodes=None):
    socks, ex, lines = read_torrc()
    out = []
    sp = en = False

    for l in lines:
        t = l.strip()
        if t.startswith("SocksPort") and port is not None:
            out.append(f"SocksPort {port}")
            sp = True
        elif t.startswith("ExitNodes") and exitnodes is not None:
            out.append(f"ExitNodes {exitnodes}")
            en = True
        else:
            out.append(l)

    if port is not None and not sp:
        out.append(f"SocksPort {port}")
    if exitnodes is not None and not en:
        out.append(f"ExitNodes {exitnodes}")

    atomic_write(TORRC, out)

# ========================= TOR IP =========================

def ensure_tor():
    if which("systemctl"):
        r = run(["systemctl", "is-active", SERVICE], capture_output=True)
        if r.stdout.strip() != "active":
            start()
            time.sleep(3)

def tor_ip():
    if requests is None:
        err("requests[socks] not installed")
        return

    ensure_tor()
    socks, _, _ = read_torrc()

    proxies = {
        "http": f"socks5h://127.0.0.1:{socks}",
        "https": f"socks5h://127.0.0.1:{socks}",
    }

    try:
        r = requests.get(
            "http://checkip.amazonaws.com/",
            proxies=proxies,
            timeout=15,
        )
        ok(f"Tor IP: {r.text.strip()}")
    except Exception as e:
        err(str(e))

# ========================= CRON =========================

def cron(minutes: int):
    if not require_root() or minutes <= 0:
        return

    job = f"*/{minutes} * * * * /usr/bin/systemctl restart {SERVICE}"
    r = run(["crontab", "-l"], capture_output=True, check=False)

    lines = [l for l in r.stdout.splitlines() if SERVICE not in l]
    lines.append(job)

    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write("\n".join(lines) + "\n")

    run(["crontab", f.name])
    os.unlink(f.name)
    ok("Cronjob installed")

# ========================= INSTALL =========================

def install():
    if not require_root():
        return
    run(["apt", "update"])
    run(["apt", "install", "-y", "tor", "tor-geoipdb", "python3-pip"])
    run([sys.executable, "-m", "pip", "install", "requests[socks]"], check=False)
    ok("Tor installed")

def update():
    require_root() and run(["apt", "install", "--only-upgrade", "-y", "tor"])
    ok("Tor updated")

def uninstall():
    require_root() and run(["apt", "remove", "-y", "tor"])
    warn("Tor uninstalled")

# ========================= STATE =========================

@dataclass
class State:
    installed: bool
    socks: int
    exitnodes: str

def build_state():
    s, e, _ = read_torrc()
    return State(which("tor") is not None, s, e)

# ========================= MENU =========================

def menu():
    while True:
        os.system("clear")
        st = build_state()

        banner()
        hr()
        print(f" Tor status : {C.G if st.installed else C.R}{'INSTALLED' if st.installed else 'NOT INSTALLED'}{C.N}")
        print(f" SocksPort  : {C.C}{st.socks}{C.N}")
        print(f" ExitNodes  : {C.C}{st.exitnodes or '(none)'}{C.N}")
        hr()

        print(
            " 1) Install tor\n"
            " 2) Update tor\n"
            " 3) Uninstall tor\n"
            " 4) Get tor IP\n"
            " 5) Cronjob (rotate IP)\n"
            " 6) Rotate IP (reload + restart)\n"
            " 7) Change SocksPort\n"
            " 8) Change ExitNodes\n"
            " 9) Start tor\n"
            "10) Stop tor\n"
            "11) Restart tor\n"
            "12) Reload tor\n"
            "13) Status\n"
            " 0) Exit"
        )

        c = prompt("Select option")

        if c == "0":
            print("\nbye 👋")
            return
        elif c == "1":
            install()
        elif c == "2":
            update()
        elif c == "3":
            uninstall()
        elif c == "4":
            tor_ip()
        elif c == "5":
            m = prompt("Rotate every N minutes")
            if m.isdigit():
                cron(int(m))
        elif c == "6":
            reload()
            restart()
        elif c == "7":
            p = prompt("New SocksPort")
            if p.isdigit() and int(p) > 0:
                write_torrc(port=int(p))
                restart()
                ok("SocksPort updated")
        elif c == "8":
            print(f"{C.D}Valid codes: {', '.join(VALID_COUNTRY_CODES)}{C.N}")
            raw = prompt("Country codes")
            parts = [
                x for x in raw.replace(",", " ").split()
                if x in VALID_COUNTRY_CODES
            ]
            if parts:
                write_torrc(exitnodes="".join(f"{{{p}}}" for p in parts))
                restart()
                ok("ExitNodes updated")
        elif c == "9":
            start()
        elif c == "10":
            stop()
        elif c == "11":
            restart()
        elif c == "12":
            reload()
        elif c == "13":
            status()

        pause()

# ========================= ENTRY =========================

if __name__ == "__main__":
    menu()
