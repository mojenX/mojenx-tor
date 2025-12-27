

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import time
import shutil
import socket
import tempfile
import subprocess
import threading
import select
import binascii
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional

# Constants
APP_NAME = "mojenX Tor Manager"
VERSION = "2.0.0-pro"

TORRC = Path("/etc/tor/torrc")
BACKUP_DIR = Path("/var/backups/mojenx")
LOG_FILE = Path("/var/log/mojenx/tor.log")
DEFAULT_SOCKS = 9050
DEFAULT_CONTROL = 9051

VALID_COUNTRIES = {
    "tr","de","us","fr","gb","uk","at","be","ro","ca","sg","jp","ie","fi","es","pl","nl","se","ch","it"
}

ICANHAZIP = "http://icanhazip.com/"

# Graceful optional rich import
try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.align import Align
    from rich.text import Text
except Exception:
    Console = None

# ===================== Utilities =====================

def log(msg: str):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%F %T')}] {msg}\n")
    except Exception:
        pass

def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    log("RUN " + " ".join(cmd))
    return subprocess.run(cmd, text=True, **kw)

def which(x: str) -> Optional[str]:
    return shutil.which(x)

def is_root() -> bool:
    return os.geteuid() == 0

def require_root() -> bool:
    if not is_root():
        print("Error: please run as root (sudo).")
        return False
    return True

def detect_service_name() -> str:
    # Prefer systemctl detection
    if which("systemctl"):
        r = run(["systemctl","list-units","--type=service","--no-pager"], capture_output=True, check=False)
        if "tor@default.service" in r.stdout:
            return "tor@default"
        return "tor"
    return "tor"

# ===================== Tor Manager =====================

@dataclass
class TorState:
    installed: bool
    running: bool
    socks: int
    control: int
    exitnodes: str
    use_bridges: bool

class TorManager:
    def __init__(self):
        self.service = detect_service_name()
        self.console = Console() if Console else None
        self._auto_rotate_interval_min: Optional[int] = None
        self._auto_rotate_thread: Optional[threading.Thread] = None
        self._auto_rotate_stop = threading.Event()
        self._last_ip: Optional[str] = None
        self._last_latency_ms: Optional[int] = None

    # --------------------- System / Service ---------------------

    def install(self):
        if not require_root(): return
        run(["apt","update"], check=False)
        run(["apt","install","-y","tor","tor-geoipdb","python3-requests","python3-pysocks"], check=False)
        print("Tor installed.")
        self.ensure_control_port()
        self.restart()

    def update(self):
        if not require_root(): return
        run(["apt","install","--only-upgrade","-y","tor"], check=False)
        print("Tor updated.")

    def uninstall(self):
        if not require_root(): return
        run(["apt","remove","-y","tor"], check=False)
        print("Tor uninstalled.")

    def svc(self, action: str):
        if which("systemctl"):
            run(["systemctl", action, self.service], check=False)
        else:
            run(["service", self.service, action], check=False)

    def start(self):
        if not require_root(): return
        self.svc("start")

    def stop(self):
        if not require_root(): return
        self.svc("stop")

    def restart(self):
        if not require_root(): return
        self.svc("restart")

    def reload(self):
        if not require_root(): return
        self.svc("reload")

    def status_text(self) -> str:
        if which("systemctl"):
            r = run(["systemctl","status",self.service,"--no-pager"], capture_output=True, check=False)
            return r.stdout
        else:
            r = run(["service",self.service,"status"], capture_output=True, check=False)
            return r.stdout

    def is_installed(self) -> bool:
        return which("tor") is not None

    def is_running(self) -> bool:
        if which("systemctl"):
            r = run(["systemctl","is-active",self.service], capture_output=True, check=False)
            return r.stdout.strip() == "active"
        else:
            r = run(["service",self.service,"status"], capture_output=True, check=False)
            return "running" in r.stdout.lower()

    # --------------------- torrc I/O ---------------------

    def backup_torrc(self):
        try:
            if TORRC.exists():
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                ts = time.strftime("%Y%m%d-%H%M%S")
                shutil.copy2(TORRC, BACKUP_DIR / f"torrc.{ts}.bak")
        except Exception as e:
            log(f"backup_torrc error: {e}")

    def read_torrc(self) -> Tuple[int,int,str,bool,List[str]]:
        socks = DEFAULT_SOCKS
        control = DEFAULT_CONTROL
        exitnodes = ""
        use_bridges = False
        if not TORRC.exists():
            return socks, control, exitnodes, use_bridges, []

        try:
            lines = TORRC.read_text().splitlines()
        except Exception:
            lines = []

        for raw in lines:
            t = raw.strip()
            if t.lower().startswith("socksport"):
                parts = t.split()
                if len(parts) >= 2:
                    try:
                        socks = int(parts[1])
                    except:
                        pass
            elif t.lower().startswith("controlport"):
                parts = t.split()
                if len(parts) >= 2:
                    try:
                        control = int(parts[1])
                    except:
                        pass
            elif t.startswith("ExitNodes"):
                exitnodes = t.split(" ",1)[1] if " " in t else ""
            elif t.lower().startswith("usebridges"):
                # Form: UseBridges 1
                parts = t.split()
                if len(parts) >= 2:
                    use_bridges = parts[1] in ("1","true","yes","on")
        return socks, control, exitnodes, use_bridges, lines

    def write_torrc(self,
                    port: Optional[int] = None,
                    exitnodes: Optional[str] = None,
                    control_port: Optional[int] = None,
                    cookie_auth: Optional[bool] = None,
                    cookie_file: Optional[str] = None,
                    strict_nodes: Optional[bool] = None,
                    use_bridges: Optional[bool] = None,
                    bridges: Optional[List[str]] = None,
                    optimizations: bool = False):
        socks, control, ex, use_b, lines = self.read_torrc()
        out: List[str] = []
        replaced_keys = set()

        def emit(k: str, v: str):
            out.append(f"{k} {v}")
            replaced_keys.add(k.lower())

        # First pass: filter existing lines, replacing known keys if provided
        for raw in lines:
            t = raw.strip()
            tl = t.lower()
            key = tl.split()[0] if tl else ""
            if key in ("socksport","exitnodes","controlport","cookieauthentication","cookieauthfile",
                       "strictnodes","usebridges","clientpreferipv6or","clientuseipv6","avoiddiskwrites",
                       "bridge","clienttransportplugin"):
                # Skip existing lines; they will be emitted from new values
                continue
            out.append(raw)

        # Now append new/updated configuration
        if port:
            emit("SocksPort", str(port))
        else:
            emit("SocksPort", str(socks))

        if control_port:
            emit("ControlPort", str(control_port))
        else:
            emit("ControlPort", str(control))

        if cookie_auth is not None:
            emit("CookieAuthentication", "1" if cookie_auth else "0")

        if cookie_file:
            emit("CookieAuthFile", cookie_file)

        if exitnodes is not None:
            emit("ExitNodes", exitnodes)

        if strict_nodes is not None:
            emit("StrictNodes", "1" if strict_nodes else "0")

        if use_bridges is not None:
            emit("UseBridges", "1" if use_bridges else "0")
        else:
            emit("UseBridges", "1" if use_b else "0")

        if bridges:
            for b in bridges:
                # Expect lines like: Bridge obfs4 <fingerprint> cert=... iat-mode=...
                out.append(f"Bridge {b}")

        if optimizations:
            # Valid, safe optimizations
            emit("AvoidDiskWrites", "1")
            emit("ClientUseIPv6", "1")
            emit("ClientPreferIPv6OR", "1")

        self.backup_torrc()
        try:
            TORRC.write_text("\n".join(out) + "\n")
        except Exception as e:
            log(f"write_torrc error: {e}")

    # --------------------- ControlPort / NEWNYM ---------------------

    def _find_cookie_file(self) -> Optional[str]:
        # Common cookie paths on Debian-based systems
        candidates = [
            "/run/tor/control.authcookie",
            "/run/tor/control_auth_cookie",
            "/var/lib/tor/control_auth_cookie",
            "/var/lib/tor/control.authcookie",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def ensure_control_port(self):
        # Configure control port + cookie auth safely
        if not require_root():
            print("Skipping control port configuration (needs root).")
            return
        cookie_file = self._find_cookie_file() or "/run/tor/control.authcookie"
        self.write_torrc(
            control_port=DEFAULT_CONTROL,
            cookie_auth=True,
            cookie_file=cookie_file,
            strict_nodes=True,
            optimizations=True
        )
        self.reload()
        time.sleep(1)

    def _auth_control(self, control_port: int) -> Optional[socket.socket]:
        # Cookie authentication
        cookie_file = self._find_cookie_file()
        if not cookie_file or not os.path.exists(cookie_file):
            return None
        try:
            with open(cookie_file, "rb") as f:
                cookie = f.read()
            cookie_hex = binascii.hexlify(cookie).decode("ascii")

            s = socket.create_connection(("127.0.0.1", control_port), timeout=5)
            s.sendall(f'AUTHENTICATE {cookie_hex}\r\n'.encode())
            resp = s.recv(1024).decode(errors="ignore")
            if "250 OK" not in resp:
                s.close()
                return None
            return s
        except Exception as e:
            log(f"_auth_control error: {e}")
            return None

    def send_newnym(self) -> bool:
        _, control, _, _, _ = self.read_torrc()
        s = self._auth_control(control)
        if not s:
            return False
        try:
            s.sendall(b"SIGNAL NEWNYM\r\n")
            resp = s.recv(1024).decode(errors="ignore")
            s.close()
            return "250 OK" in resp
        except Exception as e:
            log(f"send_newnym error: {e}")
            try: s.close()
            except: pass
            return False

    def start_auto_rotation(self, minutes: int):
        self._auto_rotate_interval_min = minutes
        self._auto_rotate_stop.clear()
        if self._auto_rotate_thread and self._auto_rotate_thread.is_alive():
            return
        self._auto_rotate_thread = threading.Thread(target=self._auto_rotate_loop, daemon=True)
        self._auto_rotate_thread.start()

    def stop_auto_rotation(self):
        self._auto_rotate_stop.set()

    def _auto_rotate_loop(self):
        while not self._auto_rotate_stop.is_set():
            if self.send_newnym():
                log("NEWNYM signal sent (auto)")
            else:
                log("NEWNYM signal failed (auto)")
            interval = self._auto_rotate_interval_min or 5
            for _ in range(interval * 60):
                if self._auto_rotate_stop.is_set():
                    break
                time.sleep(1)

    # --------------------- Monitoring ---------------------

    def get_tor_ip(self, timeout: int = 20) -> Tuple[Optional[str], Optional[int]]:
        try:
            import requests
        except ImportError:
            print("python3-requests is not installed. Please install it.")
            return None, None

        socks, _, _, _, _ = self.read_torrc()
        proxies = {
            "http": f"socks5h://127.0.0.1:{socks}",
            "https": f"socks5h://127.0.0.1:{socks}",
        }
        t0 = time.time()
        try:
            r = requests.get(ICANHAZIP, proxies=proxies, timeout=timeout)
            ip = r.text.strip()
            latency_ms = int((time.time() - t0) * 1000)
            self._last_ip = ip
            self._last_latency_ms = latency_ms
            return ip, latency_ms
        except Exception as e:
            log(f"get_tor_ip error: {e}")
            return None, None

    def heartbeat(self, timeout: int = 10) -> Optional[int]:
        # Measure latency to icanhazip.com via Tor proxies
        _, l = self.get_tor_ip(timeout=timeout)
        return l

    # --------------------- ExitNodes / Bridges ---------------------

    def set_exitnodes(self, codes: List[str]):
        good = [c.lower() for c in codes if c.lower() in VALID_COUNTRIES]
        if not good:
            print("No valid country codes.")
            return
        s = "".join(f"{{{c}}}" for c in good)
        self.write_torrc(exitnodes=s)
        self.restart()

    def random_country(self):
        import random
        code = random.choice(list(VALID_COUNTRIES))
        self.set_exitnodes([code])

    def fastest_country(self, sample: Optional[List[str]] = None, timeout: int = 20):
        import random
        pool = sample or ["us","de","nl","gb","fr","ca","se","ch","fi","pl","es"]
        pool = [c for c in pool if c in VALID_COUNTRIES]
        if not pool:
            print("No valid countries in sample.")
            return
        best = None
        best_latency = None
        for c in pool:
            print(f"Testing {c}...")
            self.write_torrc(exitnodes=f"{{{c}}}")
            self.reload()
            time.sleep(3)
            ip, lat = self.get_tor_ip(timeout=timeout)
            if lat is not None:
                print(f"  -> {c} latency: {lat} ms (IP: {ip or 'N/A'})")
                if best_latency is None or lat < best_latency:
                    best_latency = lat
                    best = c
        if best:
            print(f"Fastest country: {best} ({best_latency} ms). Applying...")
            self.set_exitnodes([best])
        else:
            print("Could not determine fastest country.")

    def set_socks_port(self, port: int):
        self.write_torrc(port=port)
        self.restart()

    def enable_bridges(self, bridges: List[str]):
        # Expect obfs4 bridges copied from a provider
        self.write_torrc(use_bridges=True, bridges=bridges)
        self.restart()

    def disable_bridges(self):
        self.write_torrc(use_bridges=False)
        self.restart()

    # --------------------- State ---------------------

    def state(self) -> TorState:
        socks, control, exitnodes, use_bridges, _ = self.read_torrc()
        st = TorState(
            installed=self.is_installed(),
            running=self.is_running(),
            socks=socks,
            control=control,
            exitnodes=exitnodes,
            use_bridges=use_bridges
        )
        return st

    # --------------------- Rich Dashboard ---------------------

    def _render_header(self) -> Panel:
        header = Text(justify="center")
        header.append("\n", style="bold cyan")
        header.append("  ___       ___  __   __   _  _   \n", style="bold cyan")
        header.append(" |__ \\     / _ \\ \\ \\ / /  | || |  \n", style="bold cyan")
        header.append("    ) |   | | | | \\ V /   | || |_ \n", style="bold cyan")
        header.append("   / /    | | | |  > <    |__   _|\n", style="bold cyan")
        header.append("  / /_    | |_| | / . \\      | |  \n", style="bold cyan")
        header.append(" |____|    \\___/ /_/ \\_\\     |_|  \n", style="bold cyan")
        header.append("\n      mojenX • Tor Manager Pro\n", style="bold magenta")
        header.append(f"      v{VERSION}\n")
        return Panel(header, title="mojenX Tor", border_style="cyan", box=box.ROUNDED)

    def _render_status_table(self, st: TorState) -> Table:
        tbl = Table(title="Service & Config", box=box.SIMPLE_HEAVY)
        tbl.add_column("Key", style="bold")
        tbl.add_column("Value")

        tbl.add_row("Installed", "Yes" if st.installed else "No")
        tbl.add_row("Running", "Yes" if st.running else "No")
        tbl.add_row("Service", self.service)
        tbl.add_row("SocksPort", str(st.socks))
        tbl.add_row("ControlPort", str(st.control))
        tbl.add_row("ExitNodes", st.exitnodes or "(none)")
        tbl.add_row("Bridges", "Enabled" if st.use_bridges else "Disabled")
        tbl.add_row("Auto NEWNYM", f"{self._auto_rotate_interval_min} min" if self._auto_rotate_interval_min else "Off")
        tbl.add

