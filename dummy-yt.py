#!/usr/bin/env python3
"""DummyTube full YT-like for Itel 5031 - 240px, <15KB pages, 1MB free.
Home feed + Search + Watch + Channel + Related + Description, real via yt-dlp.
"""
import http.server, urllib.parse, urllib.request, subprocess, os, hashlib, glob, shutil, json, re, time, collections, threading, shlex, concurrent.futures

PORT = int(os.environ.get("PORT", "8081"))
BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
TCACHE = os.path.join(BASE, "tcache")
os.makedirs(CACHE, exist_ok=True); os.makedirs(TCACHE, exist_ok=True)
LOGS = collections.deque(maxlen=80)
LOCK = threading.Lock()
TPOOL = concurrent.futures.ThreadPoolExecutor(max_workers=6)
JOBS = {}
SEARCH_CACHE = {}

def blog(step, detail=""):
    ts = time.strftime("%H:%M:%S")
    with LOCK:
        LOGS.appendleft(f"{ts} {step} {detail}"[:200])
    try:
        with open(os.path.join(BASE, "pc.log"), "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {step} {detail}\n")
    except: pass

def run(cmd, timeout=60):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

def run_logged(label, cmd, timeout=300):
    blog("RUN>", f"{label}: {cmd[:120]}")
    t0 = time.time()
    p = run(cmd, timeout)
    blog("DONE<", f"{label} rc={p.returncode} {time.time()-t0:.1f}s err={(p.stderr or '')[-120:]}")
    return p

def esc(s, n=80):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")[:n]

def fmt_views(v):
    try:
        v=int(v)
        if v>=1000000: return f"{v/1000000:.1f}M views"
        if v>=1000: return f"{v/1000:.1f}K views"
        return f"{v} views"
    except: return ""

def nav():
    return """<center><b><font color="red">Dummy</font>Tube</b><br/><small>[<a href="/">Home</a>] [<a href="/trending">Trending</a>] [<a href="/web?q=news">Web</a>] [<a href="/pc">PC</a>] [<a href="/test">Test</a>]<br/>[<a href="/search?q=music">Music</a>] [<a href="/search?q=news">News</a>] [<a href="/search?q=waz">Waz</a>] [<a href="/search?q=drama">Drama</a>] [<a href="/search?q=cricket">Cricket</a>]</small><form action="/search" method="get"><input name="q" size="12"/><input type="submit" value="Go"/></form><form action="/web" method="get"><input name="q" size="12"/><input type="submit" value="Web"/></form></center><hr/>"""

def page(title, body, refresh=0):
    mr = f'<meta http-equiv="refresh" content="{refresh}"/>' if refresh else ""
    h = f"""<html><head><meta charset="utf-8"/><meta name="viewport" content="width=240"/>{mr}<title>{esc(title,40)}</title></head><body>{nav()}{body}<hr/><small><a href="/">Home</a> | <a href="/pc">PC</a> | 144p Itel</small></body></html>"""
    return h.encode("utf-8")

def converting_page(msg, url):
    b = f"<p><b>Working...</b><br/><small>{esc(msg,100)}</small></p><p>Phone wait, auto refresh 5s...</p><p><a href='{url}'>Refresh now</a> | <a href='/pc'>PC status</a></p>"
    return page("Working", b, refresh=5)

def prefetch_part(vid, qual="144", part=0):
    try:
        url = f"https://youtu.be/{vid}"
        key = hashlib.md5((vid+qual+str(part)).encode()).hexdigest()[:10]
        out = os.path.join(CACHE, f"{vid}_{qual}_p{part}.3gp")
        lock = os.path.join(CACHE, key+".lock")
        if os.path.exists(out) or os.path.exists(lock) or key in JOBS:
            return
        try: open(lock,"w").write("1")
        except: return
        JOBS[key] = True
        threading.Thread(target=do_video, args=(vid, qual, part, url, out, key, lock), daemon=True).start()
        blog("PREFETCH>", f"{vid} p{part} started on watch open")
    except Exception as e:
        blog("FAIL<", f"prefetch {vid} {e}")

def thumb_small(vid, turl):
    out = os.path.join(TCACHE, vid+".jpg")
    if os.path.exists(out) and os.path.getsize(out) > 500:
        return True
    try:
        tmp = out+".tmp"
        req = urllib.request.Request(turl, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r, open(tmp,"wb") as f:
            f.write(r.read(300000))
        run_logged("ffmpeg-thumb", f'ffmpeg -y -v error -i {shlex.quote(tmp)} -vf scale=144:-1:flags=lanczos,unsharp=5:5:0.8 -q:v 8 {shlex.quote(out)}', 15)
        try: os.remove(tmp)
        except: pass
        return os.path.exists(out)
    except: return False

def ysearch(query, n=8):
    ck = f"{query}|{n}"
    ce = SEARCH_CACHE.get(ck)
    if ce and time.time()-ce[0] < 900:
        blog("CACHE>", f"search '{query}' hit")
        return ce[1]
    blog("YTDLP>", f"search '{query}' n={n}")
    try:
        qs = shlex.quote(f"ytsearch{n}:{query}")
        r = run_logged("ytsearch", f'python3 -m yt_dlp --skip-download --no-playlist --no-warnings --socket-timeout 10 --retries 2 --js-runtimes node --flat-playlist -J {qs}', 50)
        data = json.loads(r.stdout or "{}")
        entries = data.get("entries", [])[:n]
        # parallel thumbs - seamless, no serial wait
        def _t(e):
            try:
                vid = e.get("id","")
                th = e.get("thumbnails") or []
                turl = th[-1].get("url","") if th and isinstance(th[-1],dict) else (f"https://i.ytimg.com/vi/{vid}/default.jpg" if vid else "")
                if vid and turl: thumb_small(vid, turl)
            except: pass
        list(TPOOL.map(_t, entries))
        SEARCH_CACHE[ck] = (time.time(), entries)
        return entries
    except: return []

def vinfo(vid):
    fp = os.path.join(CACHE, f"info_{vid}.json")
    if os.path.exists(fp) and time.time()-os.path.getmtime(fp) < 86400:
        try: return json.load(open(fp))
        except: pass
    try:
        uq = shlex.quote(f"https://youtu.be/{vid}")
        r = run_logged("ytinfo", f'python3 -m yt_dlp --skip-download --no-playlist --no-warnings --socket-timeout 10 --js-runtimes node -J {uq}', 40)
        d = json.loads(r.stdout or "{}")
        info = {"title":d.get("title","Video"), "channel":d.get("channel") or d.get("uploader","?"),
                "channel_id":d.get("channel_id") or "", "views":d.get("view_count",0),
                "dur":d.get("duration_string") or "", "dur_sec":int(d.get("duration") or 0),
                "desc":(d.get("description") or "")[:220],
                "thumb":(d.get("thumbnail") or "")}
        json.dump(info, open(fp,"w"))
        if info["thumb"]: thumb_small(vid, info["thumb"])
        return info
    except: return {"title":"Video","channel":"?","views":0,"dur":"","desc":""}

def websearch(query, n=8):
    ck = f"web|{query}|{n}"
    ce = SEARCH_CACHE.get(ck)
    if ce and time.time()-ce[0] < 900:
        blog("CACHE>", f"web '{query}' hit")
        return ce[1]
    blog("WEB>", f"ddg '{query}'")
    out = []
    try:
        data = urllib.parse.urlencode({"q": query, "kp": "-2"}).encode()  # kp=-2: safe search OFF, no blur/filter
        req = urllib.request.Request("https://html.duckduckgo.com/html/", data=data, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read(400000).decode("utf-8", "ignore")
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<td[^>]*class="result-snippet"[^>]*>(.*?)</td>)', html, re.S):
            link, title, sn1, sn2 = m.group(1), m.group(2), m.group(3), m.group(4)
            link = urllib.parse.unquote(link)
            if link.startswith("//duckduckgo.com/l/?uddg="):
                link = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("uddg", [link])[0]
            title = re.sub(r"<[^>]+>", "", title).strip()
            snip = re.sub(r"<[^>]+>", "", (sn1 or sn2 or "")).strip()[:140]
            if title and link.startswith("http"):
                out.append({"title": title[:70], "url": link[:200], "snip": snip})
            if len(out) >= n: break
        # fallback pattern if ddg changes markup
        if not out:
            for m in re.finditer(r'result__a[^>]*href="([^"]+)"[^>]*>([^<]+)<', html):
                link, title = urllib.parse.unquote(m.group(1)), m.group(2).strip()
                if link.startswith("//duckduckgo.com/l/?uddg="):
                    link = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("uddg", [link])[0]
                if title and link.startswith("http"):
                    out.append({"title": title[:70], "url": link[:200], "snip": ""})
                if len(out) >= n: break
        SEARCH_CACHE[ck] = (time.time(), out)
        blog("WEB<", f"'{query}' {len(out)} results")
    except Exception as e:
        blog("FAIL<", f"web '{query}' {e}")
    return out

def web_tabs(query, active="all"):
    qe = urllib.parse.quote(query)
    t = lambda k, u, label: f"<b>{label}</b>" if active==k else f'<a href="{u}?q={qe}">{label}</a>'
    return f"<p>{t('all','/web','All')} | {t('images','/webimg','Images')} | {t('videos','/search','Videos')} | {t('news','/webnews','News')}</p>"

def gsuggest(query, n=5):
    try:
        req = urllib.request.Request("https://suggestqueries.google.com/complete/search?client=firefox&q=" + urllib.parse.quote(query), headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read(50000).decode("utf-8", "ignore"))
        return [s for s in data[1][:n] if isinstance(s, str)]
    except: return []

def instant_answer(query):
    try:
        req = urllib.request.Request("https://api.duckduckgo.com/?" + urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}), headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read(100000).decode("utf-8", "ignore"))
        txt = (d.get("AbstractText") or "")[:200]
        src = d.get("AbstractSource") or ""
        if txt: return f"<p><b>{esc(txt,200)}</b><br/><small>Source: {esc(src,30)}</small></p>"
        at = d.get("Answer") or ""
        if at: return f"<p><b>{esc(re.sub('<[^>]+>','',at),100)}</b></p>"
    except: pass
    return ""

def gnews(query, n=8):
    ck = f"gnews|{query}|{n}"
    ce = SEARCH_CACHE.get(ck)
    if ce and time.time()-ce[0] < 900:
        blog("CACHE>", f"gnews '{query}' hit")
        return ce[1]
    blog("GNEWS>", f"'{query}'")
    out = []
    try:
        req = urllib.request.Request("https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "rss"}), headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            xml = r.read(300000).decode("utf-8", "ignore")
        for m in list(re.finditer(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>", xml, re.S))[:n]:
            title = re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip()[:70]
            link = m.group(2).strip()
            # unwrap bing redirect to real article (phone opens direct)
            if "url=" in link:
                try: link = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(link.replace("&amp;", "&")).query).get("url", [link])[0])
                except: pass
            link = link[:300]
            if title and link.startswith("http"):
                out.append({"title": title, "url": link, "pub": ""})
        SEARCH_CACHE[ck] = (time.time(), out)
        blog("GNEWS<", f"'{query}' {len(out)} news")
    except Exception as e:
        blog("FAIL<", f"gnews '{query}' {e}")
    return out

def webimages(query, n=8):
    ck = f"webimg|{query}|{n}"
    ce = SEARCH_CACHE.get(ck)
    if ce and time.time()-ce[0] < 900:
        blog("CACHE>", f"webimg '{query}' hit")
        return ce[1]
    blog("WEBIMG>", f"ddg images '{query}'")
    out = []
    try:
        req = urllib.request.Request("https://duckduckgo.com/?q=" + urllib.parse.quote(query) + "&iax=images&ia=images", headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            main = r.read(500000).decode("utf-8", "ignore")
        m = re.search(r"vqd=([\d-]+)", main)
        if not m: m = re.search(r"vqd['\"]?\s*[:=]\s*['\"]?([\d-]+)", main)
        vqd = m.group(1) if m else ""
        if vqd:
            iq = urllib.parse.urlencode({"l": "wt-wt", "o": "json", "q": query, "vqd": vqd, "f": ",,,", "p": "1"})
            req2 = urllib.request.Request("https://duckduckgo.com/i.js?" + iq, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Referer": "https://duckduckgo.com/"})
            with urllib.request.urlopen(req2, timeout=20) as r2:
                data = json.loads(r2.read(500000).decode("utf-8", "ignore"))
            for it in data.get("results", [])[:n]:
                img = it.get("image", "")
                thumb = it.get("thumbnail", "") or img
                title = (it.get("title", "") or "")[:60]
                if img.startswith("http"):
                    out.append({"image": img[:300], "thumb": thumb[:300], "title": title})
        # parallel small thumbs for phone
        def _t(o):
            try:
                h = hashlib.md5(o["image"].encode()).hexdigest()[:12]
                o["h"] = h
                fp = os.path.join(TCACHE, "img_" + h + ".jpg")
                if not (os.path.exists(fp) and os.path.getsize(fp) > 500):
                    rq = urllib.request.Request(o["thumb"], headers={"User-Agent": "Mozilla/5.0", "Referer": "https://duckduckgo.com/"})
                    with urllib.request.urlopen(rq, timeout=12) as r, open(fp + ".tmp", "wb") as f:
                        f.write(r.read(300000))
                    run(f'ffmpeg -y -v error -i {shlex.quote(fp + ".tmp")} -vf scale=120:-1 -q:v 14 {shlex.quote(fp)}', 15)
                    try: os.remove(fp + ".tmp")
                    except: pass
            except: pass
        list(TPOOL.map(_t, out))
        SEARCH_CACHE[ck] = (time.time(), out)
        blog("WEBIMG<", f"'{query}' {len(out)} images")
    except Exception as e:
        blog("FAIL<", f"webimg '{query}' {e}")
    return out

def read_page(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype:
                return None  # not a page (file download) - open direct
            html = r.read(300000).decode("utf-8", "ignore")
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        title = re.sub(r"<[^>]+>", "", title.group(1)).strip()[:60] if title else "Page"
        html = re.sub(r"(?is)<(script|style|nav|footer|header|form|iframe|noscript)[^>]*>.*?</\1>", " ", html)
        imgs = []
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', html[:200000], re.I):
            src = m.group(1)
            if src.startswith("//"): src = "https:" + src
            elif src.startswith("/"):
                try: src = urllib.parse.urljoin(url, src)
                except: continue
            if src.startswith("http") and len(imgs) < 3 and not src.lower().endswith(".svg"):
                imgs.append(src[:300])
            if len(imgs) >= 3: break
        text = re.sub(r"(?is)<(a)[^>]*>", " ", html)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()[:1500]
        return {"title": title, "text": text, "imgs": imgs}
    except:
        return None

def item_html(e):
    vid = e.get("id",""); title = esc(e.get("title","Video"),60)
    ch = esc(e.get("channel") or e.get("uploader",""),30)
    vw = fmt_views(e.get("view_count",0))
    dur = e.get("duration") or 0
    try: ds = f"{int(dur)//60}:{int(dur)%60:02d} " if dur else ""
    except: ds = ""
    return f"""<p><a href="/watch?v={vid}"><img src="/thumb?v={vid}" width="144"/><br/>{title}</a><br/><small>{ds}{ch} {vw}</small></p>"""

def do_audio(vid, url, out, key, lock):
    try:
        uq = shlex.quote(url)
        run_logged("ytdlp-audio", f'python3 -m yt_dlp --no-playlist --no-warnings --js-runtimes node -x --audio-format mp3 --audio-quality 32K -o {shlex.quote(out+".%(ext)s")} {uq}', 300)
        for f in glob.glob(os.path.join(CACHE, key+"*")):
            if f==out or f==lock: continue
            if f.endswith(".mp3"):
                try:
                    if os.path.getsize(f) > (os.path.getsize(out) if os.path.exists(out) else 0):
                        if os.path.exists(out): os.remove(out)
                        shutil.move(f,out)
                    else: os.remove(f)
                except: pass
            elif f.endswith(".webm") or f.endswith(".m4a") or f.endswith(".part"):
                try: os.remove(f)
                except: pass
        blog("READY<", f"audio {os.path.basename(out)} {os.path.getsize(out)//1024 if os.path.exists(out) else 0}KB")
    except Exception as e:
        blog("FAIL<", f"audio {vid} {e}")
    finally:
        try:
            if os.path.exists(lock): os.remove(lock)
        except: pass
        JOBS.pop(key, None)

def do_video(vid, qual, part, url, out, key, lock):
    try:
        uq = shlex.quote(url)
        # H264 first: AV1/VP9 sections give 403 + slow decode. H264 = fast + phone-ready.
        h264 = "bv*[height<=144][vcodec^=avc1]+ba/b[height<=144][vcodec^=avc1]/bv[height<=144]+ba/b" if qual=="144" else "bv*[height<=240][vcodec^=avc1]+ba/b[height<=240][vcodec^=avc1]/bv[height<=240]+ba/b"
        vf = "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2" if qual=="144" else "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2"
        vb = "150k" if qual=="144" else "250k"
        s0 = part*60; s1 = (part+1)*60
        sec = f"--download-sections \"*{s0//60:02d}:{s0%60:02d}-{s1//60:02d}:{s1%60:02d}\""
        tmp = os.path.join(CACHE, key+"_src.%(ext)s")
        r1 = run_logged("ytdlp-video", f'python3 -m yt_dlp --no-playlist --no-warnings --retries 3 --fragment-retries 3 --js-runtimes node -f {shlex.quote(h264)} {sec} --max-filesize 30M -o {shlex.quote(tmp)} {uq}', 300)
        if r1.returncode!=0:
            # fallback: full low download then ffmpeg cut (avoids section 403)
            blog("RETRY>", f"sections 403, full download then cut p{part}")
            for f in glob.glob(os.path.join(CACHE, key+"_src.*")):
                try: os.remove(f)
                except: pass
            r1 = run_logged("ytdlp-full", f'python3 -m yt_dlp --no-playlist --no-warnings --retries 3 --js-runtimes node -f {shlex.quote(h264)} --max-filesize 60M -o {shlex.quote(tmp)} {uq}', 400)
            if r1.returncode!=0: return
            srcs=[s for s in glob.glob(os.path.join(CACHE,key+"_src.*")) if not s.endswith(".part")]
            if not srcs: return
            src=srcs[0]
            blog("FFMPEG>", f"full cut {vid} p{part} ss={s0}")
            run_logged("ffmpeg-video", f'ffmpeg -y -v error -ss {s0} -t 60 -i {shlex.quote(src)} -vf {shlex.quote(vf)} -r 15 -preset veryfast -tune fastdecode -c:v libx264 -profile:v baseline -level 3.0 -b:v {vb} -c:a aac -b:a 32k -ac 1 -ar 22050 -movflags +faststart {shlex.quote(out)}', 300)
            try: os.remove(src)
            except: pass
            if os.path.exists(out) and os.path.getsize(out)>10*1024*1024:
                os.remove(out); blog("FAIL<", f"video {vid} p{part} >10MB"); return
            blog("READY<", f"video {os.path.basename(out)} {os.path.getsize(out)//1024 if os.path.exists(out) else 0}KB via cut")
            return
        srcs=[s for s in glob.glob(os.path.join(CACHE,key+"_src.*")) if not s.endswith(".part")]
        if not srcs: return
        src=srcs[0]
        blog("FFMPEG>", f"{os.path.basename(src)} -> {vid}_{qual}_p{part} {vf} veryfast")
        run_logged("ffmpeg-video", f'ffmpeg -y -v error -i {shlex.quote(src)} -vf {shlex.quote(vf)} -r 15 -preset veryfast -tune fastdecode -c:v libx264 -profile:v baseline -level 3.0 -b:v {vb} -c:a aac -b:a 32k -ac 1 -ar 22050 -movflags +faststart {shlex.quote(out)}', 300)
        try: os.remove(src)
        except: pass
        if os.path.exists(out) and os.path.getsize(out)>10*1024*1024:
            os.remove(out); blog("FAIL<", f"video {vid} p{part} >10MB"); return
        blog("READY<", f"video {os.path.basename(out)} {os.path.getsize(out)//1024 if os.path.exists(out) else 0}KB")
    except Exception as e:
        blog("FAIL<", f"video {vid} p{part} {e}")
    finally:
        try:
            if os.path.exists(lock): os.remove(lock)
        except: pass
        JOBS.pop(key, None)

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_html(self,d):
        if len(d)>18000:  # emergency trim for 1MB phone
            s=d.decode("utf-8", "ignore"); s=re.sub(r'<img[^>]+>', '[img]', s); d=s.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        ua = (self.headers.get("User-Agent") or "")[:60]
        is_pc = "Mozilla" in (self.headers.get("User-Agent") or "") and "Mobile" not in ua
        blog("PHONE>" if not is_pc and u.path!="/pc" else "PC>", f"{u.path}?{urllib.parse.urlparse(self.path).query}"[:100] + f" | {ua}")
        if u.path=="/pc":
            return self.pc_page()
        if u.path=="/":
            # home = YOU decide: recent you watched + shortcuts, no auto hardcoded fetch
            recents = sorted(glob.glob(os.path.join(CACHE, "info_*.json")), key=os.path.getmtime, reverse=True)[:5]
            b = "<p><b>Home</b> <small>you decide</small></p>"
            if recents:
                b += "<p>Recent:</p>"
                for fp in recents:
                    try:
                        d = json.load(open(fp))
                        vid = os.path.basename(fp)[5:-5]
                        if len(vid) > 20: continue
                        b += f"""<p><a href="/watch?v={vid}"><img src="/thumb?v={vid}" width="144"/><br/>{esc(d.get('title','Video'),50)}</a></p>"""
                    except: pass
            else:
                b += "<p><small>No history yet. Search below.</small></p>"
            b += """<p><b>Browse:</b><br/><a href="/trending">Trending</a> | <a href="/search?q=music">Music</a> | <a href="/search?q=news">News</a> | <a href="/search?q=waz">Waz</a> | <a href="/search?q=drama">Drama</a> | <a href="/search?q=cricket">Cricket</a></p><p><a href="/test">Test phone</a> | <a href="/pc">PC monitor</a></p>"""
            return self.send_html(page("Home", b))
        if u.path=="/test":
            return self.send_html(page("OK","<p>OK if you see this.</p>"))
        if u.path=="/trending":
            fp = os.path.join(CACHE, "trending.json")
            entries = []
            if os.path.exists(fp) and time.time()-os.path.getmtime(fp) < 1800:
                try: entries = json.load(open(fp))
                except: pass
            if not entries:
                entries = ysearch("trending", 8)
                try: json.dump(entries, open(fp,"w"))
                except: pass
            b = "<p><b>Trending</b></p>"
            for e in entries: b += item_html(e)
            return self.send_html(page("Trending", b))
        if u.path=="/search":
            query = q.get("q",[""])[0].strip()
            if not query: return self.send_html(page("Search","<p>Empty.</p>"))
            entries = ysearch(query, 8)
            if not entries: return self.send_html(page("No result","<p>No result.</p>"))
            qe = urllib.parse.quote(query)
            b = f"<p><b>Videos</b> | <a href='/web?q={qe}'>All</a> | <a href='/webimg?q={qe}'>Images</a> | <a href='/webnews?q={qe}'>News</a></p>"
            b += f"<p><b>{esc(query,30)}</b> {len(entries)} found</p>"
            for e in entries: b += item_html(e)
            return self.send_html(page(query, b))
        if u.path=="/web":
            query = q.get("q",[""])[0].strip()
            if not query: return self.send_html(page("Web","<p>Type a word above, tap Web.</p>"))
            res = websearch(query, 8)
            if not res: return self.send_html(page("No result","<p>No web result. Try other words.</p>"))
            b = web_tabs(query, "all") + f"<p><b>Web: {esc(query,30)}</b> {len(res)} found</p>"
            try:
                sug = gsuggest(query)
                if sug:
                    b += "<p><small>Try: " + " ".join(f'<a href="/web?q={urllib.parse.quote(s)}">{esc(s,25)}</a>' for s in sug[:4]) + "</small></p>"
                ans = instant_answer(query)
                if ans: b += ans
            except: pass
            for r in res:
                host = esc(urllib.parse.urlparse(r['url']).netloc, 30)
                go = "/go?u=" + urllib.parse.quote(r['url'], safe="")
                b += f"""<p><a href="{go}">{esc(r['title'],60)}</a><br/><small>{host}</small><br/><small>{esc(r['snip'],140)}</small></p>"""
            return self.send_html(page(query, b))
        if u.path=="/webimg":
            query = q.get("q",[""])[0].strip()
            if not query: return self.send_html(page("Images","<p>Type a word above, tap Web.</p>"))
            res = webimages(query, 8)
            if not res: return self.send_html(page("No images","<p>No images. Try other words.</p>"))
            b = web_tabs(query, "images") + f"<p><b>Images: {esc(query,30)}</b></p>"
            for r in res:
                b += f"""<p><a href="{esc(r['image'],300)}"><img src="/imgthumb?h={r.get('h','')}" width="120"/><br/>{esc(r['title'],50)}</a></p>"""
            return self.send_html(page(query + " images", b))
        if u.path=="/webnews":
            query = q.get("q",[""])[0].strip()
            if not query: return self.send_html(page("News","<p>Type a word above, tap Web.</p>"))
            res = gnews(query, 8)
            if not res: return self.send_html(page("No news","<p>No news. Try other words.</p>"))
            b = web_tabs(query, "news") + f"<p><b>News: {esc(query,30)}</b></p>"
            for r in res:
                go = "/go?u=" + urllib.parse.quote(r['url'], safe="")
                b += f"""<p><a href="{go}">{esc(r['title'],70)}</a><br/><small>{esc(r['pub'],16)}</small></p>"""
            return self.send_html(page(query + " news", b))
        if u.path=="/go":
            url = q.get("u",[""])[0].strip()[:300]
            if not url.startswith("http"): return self.send_html(page("Error","<p>Bad link.</p>"))
            art = read_page(url)
            if art is None:  # file or fetch fail - send phone to original
                return self.send_html(page("Open", f"<p><a href='{esc(url,300)}'>Open original</a></p><p><small>File download - saves to SD.</small></p>"))
            b = f"<p><b>{esc(art['title'],60)}</b><br/><small>{esc(urllib.parse.urlparse(url).netloc,30)}</small></p>"
            for im in art["imgs"]:
                h = hashlib.md5(im.encode()).hexdigest()[:12]
                fp = os.path.join(TCACHE, "go_" + h + ".jpg")
                if not (os.path.exists(fp) and os.path.getsize(fp) > 500):
                    try:
                        rq = urllib.request.Request(im, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(rq, timeout=10) as rr, open(fp + ".tmp", "wb") as f:
                            f.write(rr.read(200000))
                        run(f'ffmpeg -y -v error -i {shlex.quote(fp + ".tmp")} -vf scale=220:-1 -q:v 14 {shlex.quote(fp)}', 15)
                        try: os.remove(fp + ".tmp")
                        except: pass
                    except: pass
                if os.path.exists(fp):
                    b += f'<p><img src="/gothumb?h={h}" width="220"/></p>'
            b += f"<p>{esc(art['text'],1500)}</p><p><small><a href='{esc(url,300)}'>Original page</a></small></p>"
            return self.send_html(page(art["title"][:40], b))
        if u.path=="/gothumb":
            h = re.sub(r'[^a-f0-9]','', q.get("h",[""])[0])[:12]
            fp = os.path.join(TCACHE, "go_" + h + ".jpg")
            if not os.path.exists(fp): self.send_response(404); self.end_headers(); return
            return self.serve_file(fp, "image/jpeg")
            h = re.sub(r'[^a-f0-9]','', q.get("h",[""])[0])[:12]
            fp = os.path.join(TCACHE, "img_" + h + ".jpg")
            if not os.path.exists(fp): self.send_response(404); self.end_headers(); return
            return self.serve_file(fp, "image/jpeg")
        if u.path=="/thumb":
            vid = re.sub(r'[^A-Za-z0-9_-]','', q.get("v",[""])[0])[:20]
            fp = os.path.join(TCACHE, vid+".jpg")
            if not os.path.exists(fp): self.send_response(404); self.end_headers(); return
            return self.serve_file(fp, "image/jpeg")
        if u.path=="/watch":
            vid = re.sub(r'[^A-Za-z0-9_-]','', q.get("v",[""])[0])[:20]
            if not vid: return self.send_html(page("Error","<p>No id</p>"))
            info = vinfo(vid)
            threading.Thread(target=prefetch_part, args=(vid,), daemon=True).start()
            rel = ysearch(info["title"][:30], 4)
            # filter self
            rel = [e for e in rel if e.get("id")!=vid][:3]
            dur_sec = int(info.get("dur_sec") or 0)
            parts = max(1, (dur_sec+59)//60) if dur_sec else 1
            if parts > 20: parts = 20  # cap page size for 1MB phone, first 20min
            if dur_sec and dur_sec > 90:
                plinks = "".join(f'<br/><a href="/v?v={vid}&q=144&p={i}">▶ Part{i+1} {i}-{i+1}min 3GP ~1.8MB</a>' for i in range(parts))
                plinks += f'<br/><a href="/v?v={vid}&q=audio">▶ Audio full ({dur_sec//60}min)</a>'
            else:
                plinks = f'<br/><a href="/v?v={vid}&q=144&p=0">▶ Play 144p 3GP ~1.8MB</a><br/><a href="/v?v={vid}&q=240&p=0">▶ Play 240p 3GP</a><br/><a href="/v?v={vid}&q=audio">▶ Audio</a>'
            b = f"""<p><b>{esc(info['title'],70)}</b><br/><small>{esc(info['dur'])} {fmt_views(info['views'])}<br/>By <a href="/search?q={urllib.parse.quote(info['channel'])}">{esc(info['channel'],30)}</a></small></p><p><img src="/thumb?v={vid}" width="144"/></p><p>{plinks}</p><p><small>Part1 preloads now - tap it, plays like stream.</small></p><p><small>{esc(info['desc'],200)}</small></p><p><b>Up next:</b></p>"""
            for e in rel: b += item_html(e)
            return self.send_html(page(info["title"][:40], b))
        if u.path=="/v":
            vid = re.sub(r'[^A-Za-z0-9_-]','', q.get("v",[""])[0])[:20]
            qual = q.get("q",["144"])[0]
            try: part = max(0, int(q.get("p",["0"])[0]))
            except: part = 0
            url = f"https://youtu.be/{vid}"
            key = hashlib.md5((vid+qual+str(part)).encode()).hexdigest()[:10]
            lock = os.path.join(CACHE, key+".lock")
            self_url = f"/v?v={vid}&q={qual}&p={part}"
            if qual=="audio":
                out = os.path.join(CACHE, key+".mp3")
                if os.path.exists(out) and not os.path.exists(lock):
                    nxt = f"<p><a href='/watch?v={vid}'>Back to video</a></p>"
                    # seamless: serve with back link hint via header? just serve file
                    return self.serve_file(out, "audio/mpeg")
                if key not in JOBS:
                    try: open(lock,"w").write("1")
                    except: pass
                    JOBS[key] = True
                    threading.Thread(target=do_audio, args=(vid, url, out, key, lock), daemon=True).start()
                    blog("JOB>", f"audio {vid} started in background")
                return self.send_html(converting_page(f"Audio converting... auto refresh", self_url))
            out = os.path.join(CACHE, f"{vid}_{qual}_p{part}.3gp")
            if os.path.exists(out) and not os.path.exists(lock):
                return self.serve_file(out, "video/3gpp")
            if key not in JOBS:
                try: open(lock,"w").write("1")
                except: pass
                JOBS[key] = True
                threading.Thread(target=do_video, args=(vid, qual, part, url, out, key, lock), daemon=True).start()
                blog("JOB>", f"video {vid} p{part} started in background")
            nxt = part+1
            return self.send_html(converting_page(f"Part{part+1} converting 30-60s... then plays. Next: Part{nxt+1}", self_url))
        self.send_response(404); self.end_headers()

    def pc_page(self):
        # PC realtime monitor - auto refresh, full details
        try:
            import subprocess as sp
            du = sp.run("du -sh cache tcache 2>/dev/null; ls -lh cache/*.mp4 cache/*.mp3 2>/dev/null | tail -n 10", shell=True, capture_output=True, text=True, timeout=5).stdout
        except: du = ""
        with LOCK:
            logs = list(LOGS)[:40]
        rows = "".join(f"<tr><td><small>{esc(l,120)}</small></td></tr>" for l in logs) or "<tr><td>No activity yet. Search from phone.</td></tr>"
        html = f"""<html><head><meta charset="utf-8"/><meta http-equiv="refresh" content="3"/><title>PC Monitor</title></head><body><h2>DummyTube PC Monitor - realtime</h2><p><a href="/">Phone Home</a> | <a href="/trending">Trending</a> | auto-refresh 3s | {time.strftime('%H:%M:%S')}</p><h3>What code is doing now</h3><table border="1" width="100%">{rows}</table><h3>Cache / ffmpeg outputs</h3><pre>{esc(du,2000)}</pre><h3>Legend</h3><pre>PHONE&gt; = Itel tapped a page
YTDLP&gt; = yt-dlp searching/info/download
FFMPEG&gt; = ffmpeg resizing thumb or video
RUN&gt;/DONE&lt; = command + time + result</pre></body></html>"""
        d = html.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)

    def serve_file(self, fp, ct):
        if not os.path.exists(fp): return self.send_html(page("Gone","<p>Gone.</p>"))
        sz=os.path.getsize(fp); rng=self.headers.get("Range")
        try:
            if rng:
                s=rng.strip().split("=")[-1].split("-")[0]; st=int(s) if s else 0
                if st>=sz: st=0
                self.send_response(206); self.send_header("Content-Type",ct)
                self.send_header("Accept-Ranges","bytes")
                self.send_header("Content-Range",f"bytes {st}-{sz-1}/{sz}")
                self.send_header("Content-Length",str(sz-st)); self.end_headers()
                with open(fp,"rb") as f: f.seek(st); shutil.copyfileobj(f,self.wfile)
                return
            self.send_response(200); self.send_header("Content-Type",ct)
            self.send_header("Accept-Ranges","bytes"); self.send_header("Content-Length",str(sz))
            self.end_headers()
            with open(fp,"rb") as f: shutil.copyfileobj(f,self.wfile)
        except: pass

if __name__=="__main__":
    print(f"DummyTube full on http://0.0.0.0:{PORT}")
    http.server.ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
