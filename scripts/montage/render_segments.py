#!/usr/bin/env python3
"""Render montage segments from timeline.json using pure FFmpeg.

Per segment produces one mp4 (silent video + aac audio) with:
 - 9:16 vertical composite: blurred cover background + contain foreground
 - punch-in zoom (static, computed from source AR)
 - speed ramp (uniform fps=60 -> setpts -> fps=30 resampling)
 - grade: contrast/saturation lift, vignette, light sharpen
"""
import argparse
import json
import os
import subprocess
import sys
import concurrent.futures as cf


def even(x):
    x = int(round(x))
    return x + (x % 2)


def fg_geometry(meta, zoom):
    """Foreground window geometry for contain-fit + zoom, centered on 9:16."""
    sw, sh = meta["src_w"], meta["src_h"]
    ow, oh = meta["out_w"], meta["out_h"]
    s = min(ow / sw, oh / sh)          # contain scale
    fw, fh = even(sw * s * zoom), even(sh * s * zoom)
    cw, ch = even(min(fw, ow)), even(min(fh, oh))
    return even(fw), even(fh), cw, ch


def seg_filter(meta, seg):
    fw, fh, cw, ch = fg_geometry(meta, seg["zoom"])
    ow, oh = meta["out_w"], meta["out_h"]
    fps = meta["out_fps"]
    # uniform speed handling: decode 2x fps, rescale pts, resample to out fps
    chain = f"fps={fps*2},setpts=PTS/{seg['speed']:.6f},fps={fps}"
    v = (
        f"[0:v]null,format=rgba,split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={ow}:{oh}:force_original_aspect_ratio=increase,"
        f"crop={ow}:{oh},boxblur=18:2,eq=brightness=-0.07:saturation=0.85[bg];"
        f"[fgsrc]{chain},scale={fw}:{fh},crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2,setsar=1[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,format=yuv420p,"
        f"eq=contrast=1.06:saturation=1.14:brightness=0.004,"
        f"vignette=PI/4.6,unsharp=5:5:0.35,"
        f"trim=duration={seg['out_dur']:.3f},setpts=PTS-STARTPTS[v]"
    )
    a = (
        f"[0:a]atempo={seg['speed']:.6f},atrim=duration={seg['out_dur']:.3f},"
        f"asetpts=PTS-STARTPTS,afade=t=in:d=0.012,afade=t=out:st={max(0.0, seg['out_dur']-0.05):.3f}:d=0.05[a]"
    )
    return v + ";" + a


def render_one(args_tuple):
    src, seg, meta, outdir, crf, preset = args_tuple
    i = seg["i"]
    out = os.path.join(outdir, f"seg_{i:03d}.mp4")
    log = os.path.join(outdir, f"seg_{i:03d}.log")
    fc = seg_filter(meta, seg)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{seg['src_start']:.3f}", "-t", f"{seg['src_dur']:.3f}", "-i", src,
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-r", str(meta["out_fps"]), "-vsync", "cfr", "-shortest", out]
    with open(log, "w") as lf:
        p = subprocess.run(cmd, stdout=lf, stderr=lf)
    if p.returncode != 0:
        tail = open(log).read()[-600:]
        raise RuntimeError(f"segment {i} failed:\n{tail}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="veryfast")
    a = ap.parse_args()

    tl = json.load(open(a.timeline))
    meta, segs = tl["meta"], tl["segments"]
    os.makedirs(a.outdir, exist_ok=True)
    print(f"[render] {len(segs)} segments, {a.jobs} parallel jobs", flush=True)

    tasks = [(a.source, s, meta, a.outdir, a.crf, a.preset) for s in segs]
    done = 0
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for fut in cf.as_completed([ex.submit(render_one, t) for t in tasks]):
            fut.result()
            done += 1
            print(f"[render] {done}/{len(segs)} done", flush=True)

    # verify every segment exists and is readable
    for s in segs:
        p = os.path.join(a.outdir, f"seg_{s['i']:03d}.mp4")
        if not os.path.isfile(p) or os.path.getsize(p) < 4096:
            raise RuntimeError(f"segment {s['i']} missing/too small")
    print("[render] all segments verified", flush=True)


if __name__ == "__main__":
    main()
