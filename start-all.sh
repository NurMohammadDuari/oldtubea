#!/bin/bash
# OldTubea one-tap starter: server + Cloudflare live URL + open start pages
cd "$(dirname "$0")"
fuser -k 8081/tcp 2>/dev/null; sleep 1
python3 dummy-yt.py > dummy.log 2>&1 &
sleep 3
# open start pages on PC
xdg-open http://localhost:8081/ 2>/dev/null &
xdg-open http://localhost:8081/pc 2>/dev/null &
echo "Phone start page: http://localhost:8081/ (PC) - live URL below:"
./cloudflared tunnel --url http://localhost:8081 --no-autoupdate
