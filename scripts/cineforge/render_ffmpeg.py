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
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def sh(cmd, **kw):
    print("+", " ".join(cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True, **kw)


def load_grades(repo_root=None):
    import json
    root = repo_root or REPO_ROOT
    path = os.path.join(root, "configs", "grades.json")
    with open(path) as f:
        return json.load(f)


def apply_grade(src, grade_name, out, repo_root=None):
    """Single grade application point (defect D5): configs/grades.json supplies the
    filter chain; plan.color_grade selects the entry. Applied exactly once, after
    master assembly (and mix mux), before captions so burned text stays clean."""
    grades = load_grades(repo_root)
    g = grades.get(grade_name)
    if not g:
        print(f"[grade] '{grade_name}' not in grades.json - copying ungraded", flush=True)
        import shutil
        shutil.copyfile(src, out)
        return out
    vf = g["filters"]
    print(f"[grade] applying {grade_name}: {vf}", flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                    "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--plan", default="reports/edit_plan.json")
    ap.add_argument("--mixed", default=None)
    ap.add_argument("--captions", default=None)
    ap.add_argument("--out", default="out/final.mp4")
    ap.add_argument("--dryrun", action="store_true", help="render first 4s only")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()

    tl = json.load(open(a.timeline))
    plan = json.load(open(a.plan)) if (a.plan and os.path.isfile(a.plan)) else {}
    segs = tl["segments"]
    draft = a.draft or a.dryrun

    # ---- dry-run gate: 3-5s sanity render of segment 0 at draft settings ----
    if a.dryrun:
        os.makedirs("out", exist_ok=True)
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
        # typography + grade smoke (fail in <=60s, not at stage 9): grade the mini
        # master and burn a 1-cue smoke ASS through the real font path
        apply_grade("out/_dryrun.mp4", plan.get("color_grade") or "natural",
                    "out/_dryrun_graded.mp4", repo_root=REPO_ROOT)
        smoke = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cine,Montserrat,100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,"
            "100,100,0,0,1,5,3,2,64,64,292,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:02.00,Cine,,0,0,0,,SMOKE TEST CAPTION\n")
        os.makedirs("media/fonts", exist_ok=True)
        open("out/_smoke.ass", "w").write(smoke)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "out/_dryrun_graded.mp4",
                        "-vf", "ass=out/_smoke.ass:fontsdir=media/fonts",
                        "-frames:v", "30", "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "28", "-an", "out/_dryrun_smoke.mp4"], check=True)
        print("[render] dry-run gate passed (incl. grade + typography smoke)")
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
        mdur = float(json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", cur]).decode()
        )["format"]["duration"])
        sh(["ffmpeg", "-v", "error", "-y", "-i", cur, "-i", a.mixed,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{mdur:.3f}", "-movflags", "+faststart", "out/_av.mp4"])
        # verify the mux preserved the video length (G-gate: never ship a shrunken master)
        adur = float(json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "out/_av.mp4"]).decode()
        )["format"]["duration"])
        if adur < mdur * 0.9:
            raise RuntimeError(f"audio mux truncated video: {adur:.2f}s < {mdur:.2f}s "
                               f"(mixed={a.mixed}) - refusing to continue")
        cur = "out/_av.mp4"

    # ---- grade (D5: single application point, from configs/grades.json) ----
    grade = plan.get("color_grade") or "natural"
    if not a.draft or os.environ.get("CF_GRADE_DRAFT") == "1":
        apply_grade(cur, grade, "out/_graded.mp4", repo_root=REPO_ROOT)
        cur = "out/_graded.mp4"
    else:
        print(f"[render] draft path: grade '{grade}' deferred to final pass", flush=True)

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

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    os.replace(cur, a.out)
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", a.out]).decode())
    print(f"[render] FINAL {a.out} dur={float(probe['format']['duration']):.2f}s "
          f"size={int(probe['format']['size'])/1e6:.1f}MB")


if __name__ == "__main__":
    main()
