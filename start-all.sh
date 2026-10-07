#!/bin/bash
# OldTubea one-tap starter: server + Cloudflare live URL + open start pages
cd "$(dirname "$0")"

fuser -k 8081/tcp 2>/dev/null; sleep 1
python3 dummy-yt.py > dummy.log 2>&1 &
sleep 3

# open start pages on PC
xdg-open http://localhost:8081/ 2>/dev/null &
xdg-open http://localhost:8081/pc 2>/dev/null &

# start tunnel, capture the URL it prints
rm -f /tmp/oldtubea-tunnel.log
./cloudflared tunnel --url http://localhost:8081 --no-autoupdate > /tmp/oldtubea-tunnel.log 2>&1 &
CFPID=$!

URL=""
for i in $(seq 1 40); do
  sleep 1
  URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" /tmp/oldtubea-tunnel.log 2>/dev/null | head -n 1)
  [ -n "$URL" ] && break
done

if [ -z "$URL" ]; then
  echo "Tunnel did not start. Log:"
  tail -n 10 /tmp/oldtubea-tunnel.log
  wait $CFPID
  exit 1
fi

PH="${URL/https:\/\//http://}"
echo "$PH" > phone-url.txt
command -v xclip >/dev/null 2>&1 && echo -n "$PH" | xclip -selection clipboard 2>/dev/null

cat <<EOF

============================================================
  PHONE URL (type this EXACTLY, with http:// - NOT https)

       $PH

  Render/https links will NOT open on the Itel.
  Its browser only speaks old TLS / plain http.
============================================================

PC pages:  http://localhost:8081/     (home)
           http://localhost:8081/pc   (realtime monitor)
Press Ctrl+C to stop. New URL every run.
EOF

wait $CFPID
