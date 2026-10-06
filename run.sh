#!/bin/bash
# Itel 5031 YT bridge launcher
cd "$(dirname "$0")"
# kill old
pkill -f "[s]erver.py" 2>/dev/null; sleep 1
python3 server.py > server.log 2>&1 &
echo "Local: http://localhost:8080 - test in PC browser first"
echo "Starting Cloudflare live URL..."
./cloudflared tunnel --url http://localhost:8080 --no-autoupdate
