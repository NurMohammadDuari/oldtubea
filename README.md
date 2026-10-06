# OldTubea - real YT-like for dummy phone (Itel 5031)

Looks and works like YouTube, but tiny for 240px screen, 4MB RAM, 1MB free internal.

## What is this?
- `dummy-yt.py` - main. Home + Trending + Search + Watch + Channel link + Related + Description + Play 144p/240p/Audio. No hardcoded videos. You search, you decide.
- `server.py` - old simple version (paste link -> play).
- `sd_make.py` - offline SD maker (not used for live, only if you want SD files).
- `run-dummy.sh` - starts Cloudflare live URL for phone.
- `run.sh` - old simple live URL.

## Your phone - Itel IT5031
- 2.4" 240x320, Unisoc SC6531E Mocor OS, browser XHTML-MP/WML, 3GP/H264 only
- RAM ~4MB browser heap -> youtube.com = low memory
- Internal ~1MB free -> cannot save video, use SD as buffer
- Network 2G GPRS/EDGE 100-200kbps -> need 200-250kbps video
- SD microSD/HC up to 32GB FAT32 -> save target

## Install on Mint (done once)
```
sudo apt install ffmpeg
pip3 install -U yt-dlp --break-system-packages
./get-cloudflared.sh   # downloads cloudflared 39MB
```

## PC realtime - see what code is doing
Open on PC (not phone): `http://localhost:8081/pc`
Auto-refresh 3s. Shows PHONE> taps, YTDLP> search/info/download, FFMPEG> thumb/video, RUN>/DONE< time+result, cache sizes. Log file `pc.log`.

## Run live (every time)
```
cd ~/Desktop/oldtubea
python3 dummy-yt.py
# new terminal:
./run-dummy.sh
# copy https://...trycloudflare.com URL
```
Open that URL on Itel browser -> `/test` must show OK -> Search -> Watch -> Play 144p.

## Rules for 1MB phone
- Pages auto-trim to <18KB in `dummy-yt.py:send_html`
- Thumbs 120px ~2KB in `tcache/`
- Video 256x144 15fps H264 baseline L3.0 250k + AAC mono 48k 22050Hz + faststart, Range support
- 1-min 3GP parts ~1.4MB each. Long videos play part by part, or use Audio only.
- If low memory: use 144p, not 240p. If server error: retry, keep video <5min.

## What you get - real YT-like, no hardcoded
- Home `/` shows YOUR recent watches + categories, no fixed videos. You search, you decide.
- Web `/web?q=` real web search via DuckDuckGo HTML, 8 results with snippet, tiny pages. Nav has Web box next to Go box.
- Trending `/trending` live `ytsearch trending` 8 results.
- Search `/search?q=` 8 real results with thumb 120px ~2KB, duration, channel, views.
- Watch `/watch?v=` title, views, channel, description 200ch, 1-min 3GP Parts for 1MB phone, Part1 prefetches on open so play feels like stream, Up next 3 related.
- Play `/v?v=&q=144&p=` 3GP 320x240 H264 baseline 15fps veryfast 150k + AAC 32k mono, 1-min ~1.4MB parts for near-realtime start on 2G, `video/3gpp` + Range 206. Audio 32K mono.
- PC monitor `/pc` auto-refresh 3s: PHONE taps, YTDLP, FFMPEG, RUN/DONE, cache sizes. Log `pc.log`.
- All phone pages <2.5KB, fits 240px, 4MB RAM, 1MB free. SD is buffer.

## Like the guy?
- Throaty Mumbo Netscape `PGeW-L7UPbM`: proxy PC does TLS/JS work.
- Throaty Mumbo GBC `_GlYnN9JK1k`: host PC yt-dlp + ESP32-C6 + RP2350B streams as fake ROM 160x144.
- Yours: same - PC does yt-dlp+ffmpeg, phone only shows tiny page + progressive MP4 via Cloudflare Tunnel.

## Host on Render.com
Files `Dockerfile.render:1` + `render.yaml:1` added. GitHub repo `NurMohammadDuari/oldtubea`, Render -> New Web Service -> connect that repo -> Docker, free plan ok. Health `/test`, disk 1GB for `cache/`.
Limits: free sleeps on idle (first phone tap slow), ephemeral converts redo after restart, request must return fast - ours does (Working page + background thread). TLS cert is modern ECDSA - same Itel warning as Cloudflare: test `/test` on phone, use `http` fallback if `https` gives server error.

## Troubleshoot
- No URL? run-dummy.sh prints new URL each run, old expires.
- Video stops? SD full/FAT32? Use 144p, 3min parts.
- Search slow? First search 30-60s (yt-dlp), next fast (cache 1h home, 24h info).
