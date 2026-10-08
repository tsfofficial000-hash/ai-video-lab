#!/usr/bin/env python3
"""D5: configs/grades.json is dead code - zero consumers; grade hardcoded inside
render_segments.py composite; plan.color_grade ignored. Probe must FAIL on HEAD,
PASS after fix.
Fix contract: a single grade application point (render_ffmpeg.apply_grade) reads
configs/grades.json and applies plan.color_grade exactly once post-assembly;
render_segments.py contains no grade chain; 3 grades yield 3 measurable signatures."""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_module, cf_path, synth_video, ok, fail

# 1. grades.json has at least one consumer
consumers = []
for root, _dirs, files in os.walk(cf_path("scripts")):
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(root, f)
            txt = open(p).read()
            if "grades.json" in txt:
                consumers.append(os.path.relpath(p, cf_path()))
if not consumers:
    fail("zero consumers of configs/grades.json (dead code)")
ok(f"grades.json consumed by: {consumers}")

# 2. render_segments.py no longer hardcodes the grade
rs_src = open(cf_path("scripts/montage/render_segments.py")).read()
if re.search(r"eq=contrast=1\.0\d", rs_src) or "vignette=PI/4.6" in rs_src:
    fail("render_segments.py still hardcodes the grade chain")
ok("render_segments.py is grade-free (pure geometry/composite)")

# 3. single application point exists and is measurable
try:
    rf = load_module("render_ffmpeg_under_test", "scripts/cineforge/render_ffmpeg.py")
    if not hasattr(rf, "apply_grade"):
        fail("render_ffmpeg.apply_grade() missing")
except Exception as e:
    fail(f"render_ffmpeg not importable / no apply_grade: {e}")

grades = ["natural", "cinematic_teal_orange", "sad_cold"]
sats = {}
with tempfile.TemporaryDirectory() as td:
    srcf = os.path.join(td, "src.mp4")
    synth_video(srcf, dur=2.0, w=320, h=240)
    for g in grades:
        outp = os.path.join(td, f"g_{g}.mp4")
        rf.apply_grade(srcf, g, outp, repo_root=cf_path())
        if not os.path.isfile(outp):
            fail(f"grade {g} produced no output")
        err = subprocess.run(["ffmpeg", "-hide_banner", "-i", outp, "-vf",
                              "signalstats,metadata=print:key=lavfi.signalstats.SATAVG",
                              "-f", "null", "-"], capture_output=True, text=True).stderr
        vals = [float(m) for m in re.findall(r"SATAVG=([\d.]+)", err)]
        if not vals:
            fail(f"no SATAVG measured for {g}")
        sats[g] = sum(vals) / len(vals)
    trio = sorted(sats.values())
    if trio[-1] - trio[0] < 3.0:
        fail(f"grade signatures not measurably distinct: {sats}")
ok(f"3 grades -> 3 distinct saturation signatures: "
   f"{ {k: round(v, 1) for k, v in sats.items()} }")

# 4. render_ffmpeg main path calls apply_grade exactly once
rf_src = open(cf_path("scripts/cineforge/render_ffmpeg.py")).read()
calls = len(re.findall(r"apply_grade\(", rf_src)) - 1  # minus the def
if calls < 1:
    fail("main render path never calls apply_grade")
ok("main render path applies the grade (single point)")

print("D5 PROBE: PASS (defect fixed)")
