Moein, [12/27/2025 11:30 AM]
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
mojenX Tor Manager - Ultra (Single File)
Author : mojenX
License: MIT
OS     : Debian / Ubuntu
"""

from future import annotations

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

# ===================== CONSTANTS =====================

APP_NAME = "mojenX Tor Manager"
VERSION = "1.0.0-ultra"

TORRC = Path("/etc/tor/torrc")
BACKUP_DIR = Path("/var/backups/mojenx")
LOG_FILE = Path("/var/log/mojenx/tor.log")
DEFAULT_SOCKS = 9050

VALID_COUNTRIES = {
    "tr","de","us","fr","uk","at","be","ro","ca",
    "sg","jp","ie","fi","es","pl"
}

# ===================== COLORS =====================

class C:
    B = "\033[1m"
    G = "\033[1;32m"
    R = "\033[1;31m"
    Y = "\033[1;33m"
    C = "\033[1;36m"
    D = "\033[2m"
    N = "\033[0m"

# ===================== LOGGING =====================

def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%F %T')}] {msg}\n")

# ===================== UI =====================

def clear():
    os.system("clear")

def hr():
    print(f"{C.D}{'-'*52}{C.N}")

def banner():
    print(C.C + C.B + r"""
               _       _  __
|  \/  | _  _ | |_ ___| |/ /
| |\/| |/ _ \/ _ \| __/ _ \ ' /
| |  | |  / (_) | ||  / . \
|_|  |_|\_|\_/ \\_|_|\_\

       mojenX • tor manager
""" + C.N)

def ok(msg): print(f"{C.G}✔ {msg}{C.N}")
def warn(msg): print(f"{C.Y}⚠ {msg}{C.N}")
def err(msg): print(f"{C.R}✖ {msg}{C.N}")
def pause(): input(f"{C.D}Press Enter to continue...{C.N}")
def ask(msg): return input(f"{C.C}➜ {msg}{C.N} ").strip()

# ===================== SYSTEM =====================

def run(cmd, **kw):
    log("RUN " + " ".join(cmd))
    return subprocess.run(cmd, text=True, **kw)

def is_root():
    return os.geteuid() == 0

def require_root():
    if not is_root():
        err("Run as root (sudo)")
        return False
    return True

def which(x):
    return shutil.which(x)

# ===================== SERVICE =====================

def service_name():
    if which("systemctl"):
        r = run(["systemctl","list-units","--type=service","--no-pager"],
                capture_output=True)
        if "tor@default.service" in r.stdout:
            return "tor@default"
    return "tor"

SERVICE = service_name()

def svc(action):
    if which("systemctl"):
        run(["systemctl", action, SERVICE], check=False)
    else:
        run(["service", SERVICE, action], check=False)

def start(): require_root() and svc("start")
def stop(): require_root() and svc("stop")
def restart(): require_root() and svc("restart")
def reload(): require_root() and svc("reload")

def status():
    r = run(["systemctl","status",SERVICE] if which("systemctl")
            else ["service",SERVICE,"status"], capture_output=True)
    print(r.stdout)

# ===================== TORRC =====================

def backup():
    if TORRC.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(TORRC, BACKUP_DIR / f"torrc.{ts}.bak")

def read_torrc() -> Tuple[int,str,List[str]]:
    socks = DEFAULT_SOCKS
    exitnodes = ""
    if not TORRC.exists():
        return socks, exitnodes, []

    lines = TORRC.read_text().splitlines()
    for l in lines:
        t = l.strip()
        if t.startswith("SocksPort"):
            try: socks = int(t.split()[1])
            except: pass
        elif t.startswith("ExitNodes"):
            exitnodes = t.split(" ",1)[1]
    return socks, exitnodes, lines

def write_torrc(port=None, exitnodes=None):
    socks, ex, lines = read_torrc()
    out = []
    sp = en = False

for l in lines:
        t = l.strip()
        if t.startswith("SocksPort") and port:
            out.append(f"SocksPort {port}")
            sp = True
        elif t.startswith("ExitNodes") and exitnodes:
            out.append(f"ExitNodes {exitnodes}")
            en = True
        else:
            out.append(l)

    if port and not sp:
        out.append(f"SocksPort {port}")
    if exitnodes and not en:
        out.append(f"ExitNodes {exitnodes}")

    backup()
    TORRC.write_text("\n".join(out) + "\n")

# ===================== TOR IP =====================

def tor_ip():
    try:
        import requests
    except ImportError:
        err("python3-requests not installed")
        return

    socks,_,_ = read_torrc()
    proxies = {
        "http": f"socks5h://127.0.0.1:{socks}",
        "https": f"socks5h://127.0.0.1:{socks}",
    }

    try:
        r = requests.get("http://checkip.amazonaws.com/",
                         proxies=proxies, timeout=15)
        ok(f"Tor IP: {r.text.strip()}")
    except Exception as e:
        err(str(e))

# ===================== CRON =====================

def cron(minutes: int):
    if not require_root(): return
    job = f"*/{minutes} * * * * systemctl restart {SERVICE}"
    r = run(["crontab","-l"], capture_output=True, check=False)
    lines = [l for l in r.stdout.splitlines() if SERVICE not in l]
    lines.append(job)

    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write("\n".join(lines)+"\n")

    run(["crontab", f.name])
    os.unlink(f.name)
    ok("Cronjob installed")

# ===================== INSTALL =====================

def install():
    if not require_root(): return
    run(["apt","update"])
    run(["apt","install","-y",
         "tor","tor-geoipdb","python3-requests"])
    ok("Tor installed")

def update():
    require_root() and run(["apt","install","--only-upgrade","-y","tor"])
    ok("Tor updated")

def uninstall():
    require_root() and run(["apt","remove","-y","tor"])
    warn("Tor uninstalled")

# ===================== STATE =====================

@dataclass
class State:
    installed: bool
    socks: int
    exitnodes: str

def state():
    s,e,_ = read_torrc()
    return State(which("tor") is not None, s, e)

# ===================== MENU =====================

def menu():
    while True:
        clear()
        st = state()

        banner()
        hr()
        print(f" Tor status : {C.G if st.installed else C.R}"
              f"{'INSTALLED' if st.installed else 'NOT INSTALLED'}{C.N}")
        print(f" SocksPort  : {C.C}{st.socks}{C.N}")
        print(f" ExitNodes  : {C.C}{st.exitnodes or '(none)'}{C.N}")
        hr()

        print("""
 1) Install tor
 2) Update tor
 3) Uninstall tor
 4) Get tor IP
 5) Cronjob (rotate IP)
 6) Rotate IP (reload + restart)
 7) Change SocksPort
 8) Change ExitNodes
 9) Start tor
10) Stop tor
11) Restart tor
12) Reload tor
13) Status
 0) Exit
""")

        c = ask("Select option")

        if c == "0":
            print("bye 👋")
            return
        elif c == "1": install()
        elif c == "2": update()
        elif c == "3": uninstall()
        elif c == "4": tor_ip()
        elif c == "5":
            m = ask("Rotate every N minutes")
            if m.isdigit(): cron(int(m))
        elif c == "6":
            reload(); restart()
            ok("IP rotated")
        elif c == "7":
            p = ask("New SocksPort")
            if p.isdigit():
                write_torrc(port=int(p))
                restart()
        elif c == "8":
            raw = ask("Country codes (tr,de,...)")
            parts = [x for x in raw.replace(","," ").split()
                     if x in VALID_COUNTRIES]
            if parts:
                write_torrc(exitnodes="".join(f"{{{p}}}" for p in parts))
                restart()
        elif c == "9": start()
        elif c == "10": stop()
        elif c == "11": restart()
        elif c == "12": reload()
        elif c == "13": status()

        pause()

# ===================== ENTRY =====================

if name == "main":
    menu()
