#!/usr/bin/env python3
"""Assemble montage master from rendered segments.

Builds a single ffmpeg filter_complex:
 - video: per-input normalize -> xfade chain (offsets from timeline) -> drawtext
          title/tag/end-card -> global fades
 - audio: per-input trim -> acrossfade chain mirroring video -> loudnorm -14 LUFS
 -> H.264 +faststart mp4. Also extracts a poster frame.
"""
import argparse
import json
import os
import subprocess


def esc(t):
    """escape for drawtext textfile-free usage via textfile instead (safer)."""
    return t


def write_textfiles(meta, outdir):
    paths = {}
    for key, txt in (("main", meta["title_main"]), ("sub", meta["title_sub"]),
                     ("end1", "AI VIDEO LAB"), ("end2", "FFMPEG x GITHUB ACTIONS")):
        p = os.path.join(outdir, f"_txt_{key}.txt")
        open(p, "w").write(txt)
        paths[key] = p
    return paths


def find_font():
    """N2: repo fonts (fetch_fonts output) first - the ASS hook path uses
    media/fonts, drawtext must not silently depend on system DejaVu."""
    cands = []
    env_dir = os.environ.get("CF_FONTS_DIR")
    if env_dir:
        cands += [os.path.join(env_dir, f) for f in
                  ("Anton-Regular.ttf", "Montserrat-Bold.ttf")]
    repo_media = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                              "..", "..", "media", "fonts"))
    cands += [os.path.join(repo_media, f) for f in
              ("Anton-Regular.ttf", "Montserrat-Bold.ttf")]
    cands += ["media/fonts/Anton-Regular.ttf", "media/fonts/Montserrat-Bold.ttf"]
    cands += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
    for c in cands:
        if os.path.isfile(c):
            return c
    raise RuntimeError("no bold sans font found for drawtext")


def endcard_positions(oh):
    """E7: end-card is pinned to the BOTTOM safe-zone band (y >= 86% height).
    The v2.0 y=h*0.44 anchor burned the credit over the subject's face."""
    import math
    y1 = math.ceil(oh * 0.86)          # ceil: never a hair under the band top
    y2 = y1 + int(oh * 0.030) + int(oh * 0.012)
    return y1, y2


def endcard_decision(oh):
    """E7: per-run placement decision record (logged next to the render)."""
    y1, y2 = endcard_positions(oh)
    return {"policy": (f"bottom safe band: first line y={y1} >= 86% of {oh}px; "
                       "below the caption marginV zone; face-bbox avoidance not "
                       "required at this anchor"),
            "y1": y1, "y2": y2, "canvas_h": oh,
            "face_cache_used": False,
            "band_top_fraction": 0.86}


def endcard_overlays(oh, fs_end, fs_end2, total, txt1, txt2, font, txtfiles):
    """E7: the two end-card drawtext filters, anchored at the bottom band."""
    y1, y2 = endcard_positions(oh)
    return [
        f"drawtext=fontfile={font}:textfile={txtfiles['end1']}:fontsize={fs_end}:"
        f"fontcolor=white:borderw=3:bordercolor=black@0.55:x=(w-text_w)/2:y={y1}:"
        f"alpha='if(lt(t,{total-2.6:.2f}),0,if(lt(t,{total-2.1:.2f}),(t-{total-2.6:.2f})/0.5,1))':"
        f"enable='gte(t,{total-2.6:.2f})'",
        f"drawtext=fontfile={font}:textfile={txtfiles['end2']}:fontsize={fs_end2}:"
        f"fontcolor=white@0.85:borderw=2:bordercolor=black@0.5:x=(w-text_w)/2:y={y2}:"
        f"alpha='if(lt(t,{total-2.4:.2f}),0,if(lt(t,{total-1.9:.2f}),(t-{total-2.4:.2f})/0.5,1))':"
        f"enable='gte(t,{total-2.4:.2f})'",
    ]


def real_duration(path):
    """VIDEO stream duration (frames are the ground truth for xfade offsets).
    The container duration follows the audio (aac priming makes it longer),
    which starved the xfade chain of frames after ~2 segments on ffmpeg 6.1."""
    import json as _json
    out = subprocess.check_output(["ffprobe", "-v", "error", "-print_format", "json",
                                   "-select_streams", "v:0", "-show_entries",
                                   "stream=duration", path]).decode()
    d = _json.loads(out)["streams"][0].get("duration")
    return float(d) if d is not None else 0.0


def xfade_chain(n, segs, ow, oh, fps):
    """returns (filtergraph_video_prefix, last_label)."""
    parts = []
    prev = "v0"
    cum = 0.0  # cumulative duration of current composite
    for k in range(n):
        parts.append(f"[{k}:v:0]settb=AVTB,scale={ow}:{oh},setsar=1,"
                     f"setpts=PTS-STARTPTS,fps={fps},format=yuv420p[v{k}]")
    for k in range(1, n):
        tr = segs[k - 1]["transition_after"]
        f = max(tr["dur"], 0.017)
        cum += segs[k - 1]["out_dur"] - f
        offset = max(cum, 0.0)
        lab_v = f"x{k}"
        parts.append(f"[{prev}][v{k}]xfade=transition={tr['type']}:duration={f:.3f}:"
                     f"offset={offset:.3f}[{lab_v}]")
        prev = lab_v
    return parts, prev


def acrossfade_chain(n, segs):
    parts = []
    prev = "a0"
    cum = 0.0
    for k in range(n):
        parts.append(f"[{k}:a:0]atrim=duration={segs[k]['out_dur']:.3f},"
                     f"asetpts=PTS-STARTPTS[a{k}]")
    for k in range(1, n):
        f = max(segs[k - 1]["transition_after"]["dur"], 0.017)
        cum += segs[k - 1]["out_dur"] - f
        lab_a = f"xa{k}"
        parts.append(f"[{prev}][a{k}]acrossfade=d={f:.3f}:c1=tri:c2=tri[{lab_a}]")
        prev = lab_a
    return parts, prev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--segdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--poster", default=None)
    ap.add_argument("--script", default=None, help="write filter_complex script here")
    a = ap.parse_args()

    tl = json.load(open(a.timeline))
    meta, segs = tl["meta"], tl["segments"]
    n = len(segs)

    # ground truth: use ACTUAL encoded segment durations for offset math
    planned = sum(s["out_dur"] for s in segs)
    for s in segs:
        p = os.path.join(a.segdir, f"seg_{s['i']:03d}.mp4")
        try:
            s["out_dur"] = round(min(real_duration(p), s["out_dur"] + 0.05), 3)
        except Exception:
            pass  # keep planned duration on probe failure
    real_total = sum(s["out_dur"] for s in segs)
    print(f"[assemble] planned={planned:.2f}s real_sum={real_total:.2f}s", flush=True)
    ow, oh, fps = meta["out_w"], meta["out_h"], meta["out_fps"]
    total = sum(s["out_dur"] for s in segs) - sum(
        s["transition_after"]["dur"] for s in segs[:-1])
    font = find_font()
    txt = write_textfiles(meta, os.path.dirname(os.path.abspath(a.out)))

    vparts, vlast = xfade_chain(n, segs, ow, oh, fps)
    apart, alast = acrossfade_chain(n, segs)

    fs_main = int(ow * 0.062)
    fs_sub = int(ow * 0.030)
    fs_end = int(ow * 0.052)
    fs_end2 = int(ow * 0.026)

    # when the plan carries an ASS hook line, the burned hook replaces the
    # generic title card (avoids two competing texts in the first 2.5s)
    suppress_title = bool(meta.get("suppress_title"))

    alpha_in = ("if(lt(t,1.0),0,if(lt(t,1.6),(t-1.0)/0.6,"
                "if(lt(t,3.6),1,if(lt(t,4.2),(4.2-t)/0.6,0))))")
    endcard = endcard_overlays(oh, fs_end, fs_end2, total,
                               txt1="AI VIDEO LAB", txt2="FFMPEG x GITHUB ACTIONS",
                               font=font, txtfiles=txt)
    overlays = ([] if suppress_title else [
        f"drawtext=fontfile={font}:textfile={txt['main']}:fontsize={fs_main}:"
        f"fontcolor=white:borderw=3:bordercolor=black@0.55:x=(w-text_w)/2:y=h*0.36:"
        f"alpha='{alpha_in}':enable='between(t,1.0,4.2)'",
        f"drawtext=fontfile={font}:textfile={txt['sub']}:fontsize={fs_sub}:"
        f"fontcolor=white@0.92:borderw=2:bordercolor=black@0.5:x=(w-text_w)/2:y=h*0.36+{fs_main}+28:"
        f"alpha='{alpha_in}':enable='between(t,1.0,4.2)'"]
    ) + endcard

    dec_path = os.path.join(os.path.dirname(os.path.abspath(a.out)),
                            "endcard_decision.json")
    try:
        import json as _json
        _json.dump(endcard_decision(oh), open(dec_path, "w"), indent=1)
        print(f"[assemble] end-card decision -> {dec_path}", flush=True)
    except Exception as _e:
        print(f"[assemble] end-card decision log failed: {_e}", flush=True)

    last_tr = segs[-2]["transition_after"]["type"] if len(segs) > 1 else "none"
    fades = [f"fade=t=in:st=0:d=0.45"]
    if last_tr != "fadeblack":
        # fadeblack already lands the outro on black; stacking a second fade
        # doubles the detectable black region (G1 budget)
        fades.append(f"fade=t=out:st={max(0.0,total-0.7):.3f}:d=0.7")
    post_v = ",".join(overlays + fades)
    post_a = (f"loudnorm=I=-16:TP=-1.5:LRA=11,"
              f"afade=t=out:st={max(0.0,total-0.9):.3f}:d=0.9")

    graph = ";".join(vparts + apart + [
        f"[{vlast}]{post_v}[vout]",
        f"[{alast}]{post_a}[aout]",
    ])

    script_path = a.script or (a.out + ".filter.txt")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(script_path, "w").write(graph)

    inputs = []
    for s in segs:
        p = os.path.join(a.segdir, f"seg_{s['i']:03d}.mp4")
        inputs += ["-i", p]

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + inputs + [
        # inline -filter_complex: -filter_complex_script is deprecated in ffmpeg 7.0
        # and breaks on the static runner build ("Filter not found"); inline works
        # on every version (apt 6.1.1, static 7.0.2+, 8.x)
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-fps_mode", "cfr",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", a.out]
    print(f"[assemble] master graph: {n} inputs, target {total:.2f}s -> {a.out}", flush=True)
    p = subprocess.run(cmd)
    if p.returncode != 0:
        raise SystemExit(f"[assemble] ffmpeg failed (graph at {script_path})")

    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", a.out]).decode())
    dur = float(probe["format"]["duration"])
    size = os.path.getsize(a.out)
    print(f"[assemble] OK duration={dur:.2f}s size={size/1e6:.1f}MB", flush=True)

    if a.poster:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur/3:.2f}", "-i", a.out,
                        "-frames:v", "1", "-q:v", "3", a.poster], check=True)
        print(f"[assemble] poster -> {a.poster}", flush=True)


if __name__ == "__main__":
    main()
