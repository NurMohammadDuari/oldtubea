#!/bin/bash
# OldTubea keep-alive: run every minute from cron. Idempotent, self-healing.
#   crontab:  * * * * * /home/mint/Desktop/oldtubea/keep-alive.sh >/dev/null 2>&1
#
# Uses a self-expiring stamp file (NOT flock): background children inherit file
# descriptors, which kept a flock held forever and made every later run skip.
SRC=/home/mint/Desktop/oldtubea
RUN=/home/mint/itel-yt-tool
LOG=$RUN/keepalive.log
STAMP=/tmp/oldtubea-keepalive.stamp
SIGFILE=$RUN/.last-run-sig
RESTARTED=$RUN/.last-restart
MAXAGE=150   # a crashed run stops blocking others after this many seconds

ts() { date '+%Y-%m-%d %H:%M:%S'; }
booting() {
  # true if we started the server less than 45s ago (give it time to come up)
  local t; t=$(cat "$RESTARTED" 2>/dev/null || echo 0)
  [ $(( $(date +%s) - t )) -lt 45 ]
}

# --- single-instance guard (self-expires, no inherited fd) ---
if [ -f "$STAMP" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) ))
  [ "$age" -lt "$MAXAGE" ] && exit 0
fi
touch "$STAMP"
trap 'rm -f "$STAMP"' EXIT

# --- 1) newest code + PIN -> runtime copy ---
if [ -f "$SRC/dummy-yt.py" ] && [ "$SRC/dummy-yt.py" -nt "$RUN/dummy-yt.py" ]; then
  cp -f "$SRC/dummy-yt.py" "$RUN/dummy-yt.py" && echo "$(ts) code synced" >> "$LOG"
fi
if [ -f "$SRC/pin.txt" ] && { [ ! -f "$RUN/pin.txt" ] || [ "$SRC/pin.txt" -nt "$RUN/pin.txt" ]; }; then
  cp -f "$SRC/pin.txt" "$RUN/pin.txt" && echo "$(ts) pin synced" >> "$LOG"
fi
rm -f "$RUN/pin.txt" 2>/dev/null
if [ -f "$SRC/pin.txt" ]; then cp -f "$SRC/pin.txt" "$RUN/pin.txt"; fi

# --- 2) do we need a (re)start? ---
SIG=$(cat "$SRC/dummy-yt.py" "$SRC/pin.txt" 2>/dev/null | cksum)
LAST=$(cat "$SIGFILE" 2>/dev/null)
CODE=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/test)
REASON=""
if [ "$CODE" != "200" ]; then
  # only wait if the server process exists and is still booting;
  # if it is actually gone, restart immediately
  if booting && pgrep -f "python3 dummy-yt.py" >/dev/null 2>&1; then
    exit 0
  fi
  REASON="down($CODE)"
elif [ "$SIG" != "$LAST" ]; then
  REASON="code-or-pin-changed"
fi

if [ -n "$REASON" ]; then
  fuser -k 8081/tcp 2>/dev/null
  sleep 1
  cd "$RUN" || exit 0
  setsid nohup python3 dummy-yt.py >> dummy.log 2>&1 < /dev/null &
  disown
  date +%s > "$RESTARTED"
  echo "$SIG" > "$SIGFILE"
  sleep 5
  if curl -s -m 5 -o /dev/null http://127.0.0.1:8081/test; then
    echo "$(ts) server started ($REASON)" >> "$LOG"
  else
    echo "$(ts) server FAILED ($REASON)" >> "$LOG"
  fi
fi

# --- 3) tunnel: only when wanted, only if it died ---
if [ -f "$RUN/.want-tunnel" ] && ! pgrep -x cloudflared >/dev/null; then
  cd "$RUN" || exit 0
  setsid nohup ./cloudflared tunnel --url http://localhost:8081 --no-autoupdate >> tunnel.log 2>&1 < /dev/null &
  disown
  sleep 15
  URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$RUN/tunnel.log" 2>/dev/null | tail -n 1)
  if [ -n "$URL" ]; then
    echo "${URL/https:\/\//http://}" > "$SRC/phone-url.txt"
    echo "$(ts) tunnel started ${URL/https:\/\//http://}" >> "$LOG"
  else
    echo "$(ts) tunnel start: no url yet" >> "$LOG"
  fi
fi
exit 0
