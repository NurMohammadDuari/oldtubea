#!/bin/bash
# OldTubea keep-alive: run every minute from cron. Idempotent, self-healing.
#   crontab:  * * * * * /home/mint/Desktop/oldtubea/keep-alive.sh >/dev/null 2>&1
SRC=/home/mint/Desktop/oldtubea
RUN=/home/mint/itel-yt-tool
LOG=$RUN/keepalive.log
LOCK=/tmp/oldtubea-keepalive.lock

exec 9>"$LOCK"; flock -n 9 || exit 0   # never overlap with a previous run

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 1) newest code -> runtime copy
if [ -f "$SRC/dummy-yt.py" ] && [ "$SRC/dummy-yt.py" -nt "$RUN/dummy-yt.py" ]; then
  cp -f "$SRC/dummy-yt.py" "$RUN/dummy-yt.py" && echo "$(ts) code synced" >> "$LOG"
fi

# 2) server: start if not answering
if ! curl -s -m 5 -o /dev/null http://127.0.0.1:8081/test; then
  fuser -k 8081/tcp 2>/dev/null
  sleep 1
  cd "$RUN" && setsid nohup python3 dummy-yt.py >> dummy.log 2>&1 < /dev/null &
  sleep 4
  if curl -s -m 5 -o /dev/null http://127.0.0.1:8081/test; then
    echo "$(ts) server started" >> "$LOG"
  else
    echo "$(ts) server FAILED to start" >> "$LOG"
  fi
fi

# 3) tunnel: only when wanted, and only if it died
if [ -f "$RUN/.want-tunnel" ] && ! pgrep -x cloudflared >/dev/null; then
  cd "$RUN" && setsid nohup ./cloudflared tunnel --url http://localhost:8081 --no-autoupdate >> tunnel.log 2>&1 < /dev/null &
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
