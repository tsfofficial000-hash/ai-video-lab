#!/usr/bin/env python3
"""R2 proof: a SOLO qc.py CLI invocation without --ass must (a) auto-discover
the ass recorded in captions_report.json and run the differential test,
(b) label the absolute ratio as a 0.15% FALLBACK when no ass exists anywhere.
Output: two QC runs' captions_burned verdicts (committed as the R2 log)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tests", "defects"))
from common import synth_video, pick_font  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "cap_p", os.path.join(REPO, "scripts", "cineforge", "captions.py"))
sys.path.insert(0, os.path.join(REPO, "scripts", "cineforge"))
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)

td = tempfile.mkdtemp(prefix="r2proof_")
fontsdir = os.path.dirname(pick_font())
os.environ["CF_FONTS_DIR"] = fontsdir

clean = synth_video(os.path.join(td, "clean.mp4"), dur=4.0, bright=True)
hdr = cap.ASS_HEADER.format(w=540, h=960, cap_font="Montserrat",
                            hook_font="Montserrat", size=96,
                            primary="&H00FFFFFF", outline="&H00000000",
                            outline_w=5, shadow=3, ml=32, mr=32, mv=240,
                            hook_size=150)
ev = "\n".join(f"Dialogue: 0,{cap.ts(max(0.0, t - 0.4))},{cap.ts(t + 0.4)},"
               f"Cine,,0,0,0,,A CAPTION LINE" for t in [0.5, 2.0, 3.5])
ass = os.path.join(td, "captions.ass")
open(ass, "w").write(hdr + "\n" + ev + "\n")
capped = os.path.join(td, "capped.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clean, "-vf",
                f"ass={ass}:fontsdir={fontsdir}", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "copy", capped], check=True)

reports = os.path.join(td, "reports")
os.makedirs(reports)
# production semantics: captions.py records the ass path (absolute)
json.dump({"style": "viral_high_contrast", "cues": [0.5, 2.0, 3.5], "events": 3,
           "ass_path": ass},
          open(os.path.join(reports, "captions_report.json"), "w"))
plan = os.path.join(td, "plan.json")
json.dump({"caption_style": "viral_high_contrast", "resolution": "540x960",
           "target_duration": 4.0, "fps": 30}, open(plan, "w"))

QC = [sys.executable, os.path.join(REPO, "scripts", "cineforge", "qc.py")]

print("=" * 78)
print("R2 PROOF A: solo qc.py CLI, NO --ass, NO --fontsdir (audit false-RED shape)")
print("=" * 78)
r = subprocess.run(QC + ["--video", capped, "--plan", plan, "--reports", reports],
                   capture_output=True, text=True,
                   cwd=os.path.join(REPO, "scripts", "cineforge"))
print(r.stdout)
det = json.load(open(os.path.join(reports, "qc_report.json")))
cb = next(c for c in det["checks"] if c["check"] == "captions_burned")
assert cb["passed"], "captioned final must PASS"
assert "differential" in cb["detail"] and "captions_report.json" in cb["detail"], cb["detail"]
print(f">>> captions_burned PASSED via: {cb['detail'][:160]}")

print()
print("=" * 78)
print("R2 PROOF B: same invocation with the ass REMOVED (labelled fallback)")
print("=" * 78)
os.remove(ass)
r = subprocess.run(QC + ["--video", capped, "--plan", plan, "--reports", reports],
                   capture_output=True, text=True,
                   cwd=os.path.join(REPO, "scripts", "cineforge"))
print(r.stdout)
det = json.load(open(os.path.join(reports, "qc_report.json")))
cb = next(c for c in det["checks"] if c["check"] == "captions_burned")
assert "FALLBACK" in cb["detail"] and "0.15%" in cb["detail"], cb["detail"]
assert cb["passed"], f"0.15% fallback must not false-RED a captioned final: {cb['detail']}"
print(f">>> labelled fallback, no false RED: {cb['detail'][:160]}")
print()
print("R2 PROOF: PASS")
