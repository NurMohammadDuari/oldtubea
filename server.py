#!/usr/bin/env python3
"""Itel 5031 YouTube bridge - OLD simple version. Use dummy-yt.py for full YT-like.
Kept for paste-link fallback. Has no parts splitting, use dummy for long videos.
"""
import http.server, urllib.parse, subprocess, os, hashlib, time, shutil, mimetypes

PORT = 8080
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
YTDLP = "python3 -m yt_dlp"

HEADER = b"Content-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\n"

def page(title, body):
    # ultra-light, XHTML-MP friendly
    html = f"""<html><head><meta charset="utf-8"/><meta name="viewport" content="width=240"/><title>{title}</title></head><body><h3>{title}</h3>{body}<hr/><small>Itel-bridge | &lt;8MB | 240p max</small></body></html>"""
    return html.encode("utf-8")

def run(cmd, timeout=120):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_html(self, data):
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/" or u.path == "/index":
            body = """<form action="/watch" method="get">Paste YT link:<br/><input name="url" size="20"/><br/><input type="submit" value="Get video"/></form><p><a href="/test">Test phone</a></p><p>Tip: keep video &lt;5 min.</p>"""
            return self.send_html(page("YT for Itel 5031", body))
        if u.path == "/test":
            return self.send_html(page("OK", "<p>Phone OK. If you see this, bridge works.</p><p><a href='/'>Back</a></p>"))
        if u.path == "/watch":
            yt = q.get("url",[""])[0].strip()
            if not yt:
                return self.send_html(page("Error", "<p>No URL. <a href='/'>Back</a></p>"))
            # short id for links
            enc = urllib.parse.quote(yt, safe="")
            # get title quickly
            try:
                r = run(f"python3 -m yt_dlp --no-playlist --print title --js-runtimes node \"{yt}\"", timeout=25)
                title = (r.stdout.strip()[:60] or "Video") if r.returncode==0 else "Video"
            except Exception:
                title = "Video"
            title_e = title.replace("<","").replace(">","")
            body = f"""<p>{title_e}</p><p><a href="/v?url={enc}&q=144">1. Play 144p (~3MB)</a></p><p><a href="/v?url={enc}&q=240">2. Play 240p (~6MB)</a></p><p><a href="/v?url={enc}&q=audio">3. Audio only (~1MB)</a></p><p>Click one, wait 30-90s, then phone player opens.</p><p><a href="/">Back</a></p>"""
            return self.send_html(page("Choose", body))
        if u.path == "/v":
            yt = q.get("url",[""])[0]
            quality = q.get("q",["144"])[0]
            if not yt:
                return self.send_html(page("Error","<p>Missing URL</p>"))
            vid = hashlib.md5((yt+quality).encode()).hexdigest()[:12]
            if quality == "audio":
                out = os.path.join(CACHE_DIR, vid+".mp3")
                exists = os.path.exists(out)
                if not exists:
                    self.send_html(page("Working","<p>Converting audio, wait 60s then refresh...<br/><a href='"+self.path+"'>Refresh</a></p>"))
                    # placeholder to avoid double-convert? just convert now
                    try:
                        run(f"python3 -m yt_dlp --no-playlist --js-runtimes node -x --audio-format mp3 --audio-quality 64K -o \"{out}.%(ext)s\" \"{yt}\"", timeout=180)
                        # find file
                        for f in os.listdir(CACHE_DIR):
                            if f.startswith(vid):
                                if f != vid+".mp3":
                                    shutil.move(os.path.join(CACHE_DIR,f), out)
                                break
                    except Exception as e:
                        return self.send_html(page("Fail", f"<p>Fail: {e}</p>"))
                return self.serve_file(out, "audio/mpeg")
            else:
                # video: merge low video+audio then shrink to 320x240 baseline for SC6531E
                out = os.path.join(CACHE_DIR, vid+".mp4")
                if not os.path.exists(out):
                    # send waiting page first? No - convert synchronously, phone will wait/timeout.
                    # Use quick format selection to keep fast.
                    if quality == "144":
                        fmt = "best[height<=144]/bestvideo[height<=144]+bestaudio/best[height<=240]/best"
                        vf = "scale=256:144"
                    else:
                        fmt = "best[height<=240]/bestvideo[height<=240]+bestaudio/best"
                        vf = "scale=320:240"
                    tmp = os.path.join(CACHE_DIR, vid+"_src.%(ext)s")
                    try:
                        # 1. download <12MB
                        r1 = run(f"python3 -m yt_dlp --no-playlist --js-runtimes node -f \"{fmt}\" --max-filesize 25M -o \"{tmp}\" \"{yt}\"", timeout=180)
                        if r1.returncode != 0:
                            return self.send_html(page("Fail", f"<p>Download failed. Try shorter video or Audio only.</p><pre>{(r1.stderr[-500:] if r1.stderr else '')}</pre><p><a href='/'>Back</a></p>"))
                        # find src
                        src = None
                        for f in os.listdir(CACHE_DIR):
                            if f.startswith(vid+"_src"):
                                src = os.path.join(CACHE_DIR, f)
                                break
                        if not src:
                            return self.send_html(page("Fail","<p>No file. Try audio.</p>"))
                        # 2. transcode to phone-safe: H264 baseline, aac, 15fps
                        r2 = run(f"ffmpeg -y -i \"{src}\" -vf \"{vf}\" -r 15 -c:v libx264 -profile:v baseline -level 3.0 -b:v 300k -c:a aac -b:a 64k -ac 1 -ar 22050 -movflags +faststart \"{out}\"", timeout=180)
                        try: os.remove(src)
                        except: pass
                        if r2.returncode != 0 or not os.path.exists(out):
                            return self.send_html(page("Fail","<p>Convert failed. Try Audio only.</p>"))
                        # size guard
                        if os.path.getsize(out) > 20*1024*1024:
                            os.remove(out)
                            return self.send_html(page("Too big","<p>File &gt;20MB, phone cannot play. Try Audio only or shorter video.</p>"))
                    except subprocess.TimeoutExpired:
                        return self.send_html(page("Timeout","<p>Took too long. Try shorter (&lt;3min) or Audio only.</p>"))
                return self.serve_file(out, "video/mp4")
        # fallback: serve cache directly /cache/...
        if u.path.startswith("/cache/"):
            fp = os.path.join(CACHE_DIR, os.path.basename(u.path))
            if os.path.exists(fp):
                mt, _ = mimetypes.guess_type(fp)
                return self.serve_file(fp, mt or "application/octet-stream")
            self.send_response(404); self.end_headers(); return
        self.send_response(404); self.end_headers()
        self.wfile.write(b"not found <a href='/'>home</a>")

    def serve_file(self, fp, ctype):
        if not os.path.exists(fp):
            return self.send_html(page("Gone","<p>File gone. <a href='/'>Retry</a></p>"))
        size = os.path.getsize(fp)
        # Range support (phone players need it)
        rng = self.headers.get("Range")
        try:
            if rng:
                # bytes=start-end
                s = rng.strip().split("=")[-1].split("-")[0]
                start = int(s) if s else 0
                if start >= size: start = 0
                length = size - start
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges","bytes")
                self.send_header("Content-Range", f"bytes {start}-{size-1}/{size}")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                with open(fp,"rb") as f:
                    f.seek(start)
                    shutil.copyfileobj(f, self.wfile)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges","bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(fp,"rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

if __name__ == "__main__":
    print(f"Serving on http://0.0.0.0:{PORT} cache={CACHE_DIR}")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
