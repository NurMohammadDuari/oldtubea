#!/usr/bin/env python3
"""SD-card maker for Itel 5031 (4MB RAM, 240x320, SC6531E, up to 32GB microSD).
Like Throaty Mumbo GBCTube: PC does yt-dlp + ffmpeg, phone just plays dumb MP4s.
Usage:
  python3 sd_make.py "https://youtu.be/XXX" --q 144 --part 5 --out SD_CARD
  python3 sd_make.py "https://youtu.be/XXX" --q 144 --preview 60 --part 0
Output: 320x240/256x144, 15fps, H264 baseline, AAC mono, ~2-3MB per 5min, FAT32 safe.
"""
import argparse, subprocess, os, re, sys, glob

def run(cmd, timeout=600):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p

def safe(s):
    s = re.sub(r'[^\w\- ]+', '', s).strip().replace(' ', '_')[:40]
    return s or "video"

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("--q", default="144", choices=["144","240","audio"])
ap.add_argument("--part", type=int, default=3, help="minutes per file, 0=no split (3=5.4MB safe for 1MB phone)")
ap.add_argument("--preview", type=int, default=0, help="only first N seconds (test)")
ap.add_argument("--out", default="SD_CARD")
args = ap.parse_args()

os.makedirs(args.out, exist_ok=True)

print("[1/4] info...")
r = run(f'python3 -m yt_dlp --skip-download --no-playlist --js-runtimes node --print "%(id)s||%(title)s||%(duration)s" "{args.url}"', 60)
if r.returncode != 0:
    print("yt-dlp info failed:\n", r.stderr[-1000:]); sys.exit(1)
vid, title, dur = (r.stdout.strip().split("||") + ["0","?","0"])[:3]
name = safe(title)
print(f"  {title} id={vid} dur={dur}s")

section = f'--download-sections "*00:00-{args.preview//60:02d}:{args.preview%60:02d}" ' if args.preview else ""
if args.q == "144":
    fmt, vf, vb, ab = "bv[height<=144]+ba/b[height<=144]/b", "scale=256:144", "250k", "48k"
elif args.q == "240":
    fmt, vf, vb, ab = "bv[height<=240]+ba/b[height<=240]/b", "scale=320:240", "350k", "64k"
else:
    fmt, vf, vb, ab = "ba/b", "", "", "64k"

src_tpl = os.path.join(args.out, f"_{name}_src.%(ext)s")
# clean old src
for f in glob.glob(os.path.join(args.out, f"_{name}_src.*")):
    os.remove(f)

print("[2/4] downloading low-res source (PC does heavy work)...")
r = run(f'python3 -m yt_dlp --no-playlist --js-runtimes node -f "{fmt}" {section}-o "{src_tpl}" "{args.url}"', 600)
print((r.stdout or "")[-500:], (r.stderr or "")[-800:])
srcs = glob.glob(os.path.join(args.out, f"_{name}_src.*"))
srcs = [s for s in srcs if not s.endswith(".part")]
if not srcs:
    print("Download failed. Try --q audio or shorter --preview."); sys.exit(1)
src = srcs[0]
print("  src:", src, int(os.path.getsize(src)/1024), "KB")

if args.q == "audio":
    out = os.path.join(args.out, f"{name}_audio.mp3")
    print("[3/4] to MP3 mono for phone...")
    r = run(f'ffmpeg -y -i "{src}" -vn -c:a libmp3lame -b:a {ab} -ac 1 -ar 22050 "{out}"', 300)
    os.remove(src)
    print("OK:", out, int(os.path.getsize(out)/1024), "KB - copy to SD root, play via Music player")
else:
    print("[3/4] transcoding to Itel-safe MP4 (baseline, 15fps, faststart)...")
    if args.part > 0:
        secs = args.part * 60
        outpat = os.path.join(args.out, f"{name}_{args.q}p_part%03d.mp4")
        r = run(f'ffmpeg -y -i "{src}" -vf "{vf}" -r 15 -c:v libx264 -profile:v baseline -level 3.0 -b:v {vb} -c:a aac -b:a {ab} -ac 1 -ar 22050 -movflags +faststart -f segment -segment_time {secs} -reset_timestamps 1 "{outpat}"', 900)
    else:
        out = os.path.join(args.out, f"{name}_{args.q}p.mp4")
        r = run(f'ffmpeg -y -i "{src}" -vf "{vf}" -r 15 -c:v libx264 -profile:v baseline -level 3.0 -b:v {vb} -c:a aac -b:a {ab} -ac 1 -ar 22050 -movflags +faststart "{out}"', 900)
    print((r.stderr or "")[-600:])
    os.remove(src)
    outs = sorted(glob.glob(os.path.join(args.out, f"{name}_{args.q}p*.mp4")))
    if not outs:
        print("Convert failed"); sys.exit(1)
    print("[4/4] done. Copy these to SD card /VIDEO folder (FAT32):")
    total = 0
    with open(os.path.join(args.out, "PLAY_ORDER.txt"), "w") as pl:
        for o in outs:
            kb = os.path.getsize(o)//1024
            total += kb
            print(f"  {os.path.basename(o)} {kb}KB")
            pl.write(os.path.basename(o)+"\n")
    print(f"Total {total//1024}MB in {len(outs)} file(s). Each <10MB = safe for 4MB RAM.")
    print("On Itel 5031: insert SD -> File manager -> Memory card -> VIDEO -> play Part001 first.")
