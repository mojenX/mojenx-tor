# mojenx-tor
# mojenX - Tor Manager

mojenX — small, safe and simple Tor manager.

Provides interactive CLI and a tiny HTTP API (token-auth) for panel integration.

## Features
- Atomic edits + backups of /etc/tor/torrc
- Change SocksPort
- Set ExitNodes countries
- Get Tor public IP (via Tor)
- Reload & restart Tor
- HTTP API with Bearer token
- Interactive CLI

---

## One-line Install

`bash
bash <(curl -Ls https://raw.githubusercontent.com/mojenX/mojenx-tor/main/install.sh)
