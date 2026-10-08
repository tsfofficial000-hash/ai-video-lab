#!/usr/bin/env python3
"""Stage 8+9: render engine. Delegates segments/xfade to the proven montage engine,
then applies captions burn-in, music replace, grade polish, dry-run gate.
Usage: render_ffmpeg.py --source S --timeline out/timeline.json --plan reports/edit_plan.json \
         --mixed media/mixed_audio.wav --captions media/captions.ass --out out/final.mp4 [--draft]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MONTAGE = os.path.join(HERE, "..", "montage")


def sh(cmd, **kw):
    print("+", " ".join(cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--plan", default="reports/edit_plan.json")
    ap.add_argument("--mixed", default=None)
    ap.add_argument("--captions", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dryrun", action="store_true", help="render first 4s only")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()

    tl = json.load(open(a.timeline))
    plan = json.load(open(a.plan))
    segs = tl["segments"]
    draft = a.draft or a.dryrun

    # ---- dry-run gate: 3-5s sanity render of segment 0 at draft settings ----
    if a.dryrun:
        mini = {"meta": dict(tl["meta"]), "segments": segs[:2]}
        for s in mini["segments"]:
            s["out_dur"] = min(s["out_dur"], 1.5)
            s["src_dur"] = min(s["src_dur"], 1.5)
        json.dump(mini, open("out/_dryrun_timeline.json", "w"))
        sh([sys.executable, f"{MONTAGE}/render_segments.py", "--source", a.source,
            "--timeline", "out/_dryrun_timeline.json", "--outdir", "out/_dryrun_segs",
            "--jobs", "2", "--crf", "28", "--preset", "ultrafast"])
        sh([sys.executable, f"{MONTAGE}/assemble.py", "--timeline", "out/_dryrun_timeline.json",
            "--segdir", "out/_dryrun_segs", "--out", "out/_dryrun.mp4"])
        print("[render] dry-run gate passed")
        return

    # ---- segments via proven engine ----
    sh([sys.executable, f"{MONTAGE}/render_segments.py", "--source", a.source,
        "--timeline", a.timeline, "--outdir", "out/segs",
        "--jobs", "2", "--crf", "23" if draft else "19",
        "--preset", "veryfast" if draft else "medium"])
    sh([sys.executable, f"{MONTAGE}/assemble.py", "--timeline", a.timeline,
        "--segdir", "out/segs", "--out", "out/master.mp4",
        "--poster", "out/poster.jpg", "--script", "out/filtergraph.txt"])

    # ---- audio replace (mixed track) without re-encoding video ----
    cur = "out/master.mp4"
    if a.mixed and os.path.isfile(a.mixed):
        sh(["ffmpeg", "-v", "error", "-y", "-i", cur, "-i", a.mixed,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", "out/_av.mp4"])
        cur = "out/_av.mp4"

    # ---- captions burn-in (libass) ----
    if a.captions and os.path.isfile(a.captions):
        sh(["ffmpeg", "-v", "error", "-y", "-i", cur,
            "-vf", f"ass={a.captions}", "-c:v", "libx264",
            "-preset", "veryfast" if draft else "medium",
            "-crf", "23" if draft else "19", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", "out/_cap.mp4"])
        cur = "out/_cap.mp4"

    # ---- letterbox if plan asks ----
    if plan.get("letterbox"):
        h = 1920
        bar = int(h * 0.055)
        sh(["ffmpeg", "-v", "error", "-y", "-i", cur,
            "-vf", f"drawbox=y=0:w=iw:h={bar}:color=black@1:t=fill,"
                   f"drawbox=y=ih-{bar}:w=iw:h={bar}:color=black@1:t=fill",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy",
            "-movflags", "+faststart", "out/_lb.mp4"])
        cur = "out/_lb.mp4"

    os.replace(cur, a.out)
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", a.out]).decode())
    print(f"[render] FINAL {a.out} dur={float(probe['format']['duration']):.2f}s "
          f"size={int(probe['format']['size'])/1e6:.1f}MB")


if __name__ == "__main__":
    main()
