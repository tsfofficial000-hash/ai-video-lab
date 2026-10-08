#!/usr/bin/env python3
"""D4: render_segments.py crushes the composite: bg eq=brightness=-0.07 + full-canvas
vignette=PI/4.6; 16:9 contain-fit foreground = 31% of canvas height (G4 demands >= 55%
or full-bleed). Probe must FAIL on HEAD, PASS after fix.
Fix contract: bg brightness 0.00 / saturation 0.90 / boxblur 16:2; vignette <= PI/5 or
absent; `vertical` composite modes (cover_crop = full-bleed, smart_crop, blur_fill
fallback) selected via timeline meta."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_module, synth_video, ok, fail

rs = load_module("render_segments_under_test", "scripts/montage/render_segments.py")

meta = {"src_w": 1920, "src_h": 1080, "out_w": 540, "out_h": 960, "out_fps": 30}
seg = {"i": 0, "src_start": 0.0, "src_dur": 1.0, "out_dur": 1.0, "speed": 1.0, "zoom": 1.0}

# 1. crushed-bg constants gone from the default/blur path
try:
    fc = rs.seg_filter(dict(meta, vertical="blur_fill"), seg)
except TypeError:
    fc = rs.seg_filter(meta, seg)
if "brightness=-0.07" in fc:
    fail("bg eq=brightness=-0.07 still crushes the blurred background")
if "vignette=PI/4.6" in fc:
    fail("full-canvas vignette=PI/4.6 still applied (stronger than ffmpeg default)")
if "brightness=0.00" not in fc and "eq=brightness=0" not in fc.replace("eq=brightness=0.004", ""):
    fail("bg not lifted to brightness 0.00")
if "boxblur=16:2" not in fc:
    fail("bg boxblur=16:2 spec not honored")
ok("blur_fill composite: bg lifted, no -0.07 crush, no PI/4.6 vignette")

# 2. cover_crop mode = full-bleed (fg covers 100% of canvas height)
try:
    fc_cover = rs.seg_filter(dict(meta, vertical="cover_crop"), seg)
    fw, fh, cw, ch = rs.fg_geometry(dict(meta, vertical="cover_crop"), seg["zoom"])
    cov = ch / meta["out_h"]
    if cov < 0.999:
        fail(f"cover_crop foreground covers only {cov:.0%} of canvas height")
    ok(f"cover_crop is full-bleed (coverage {cov:.0%})")
except (TypeError, KeyError) as e:
    fail(f"cover_crop mode not implemented: {e}")

# 3. G4 rule: default blur_fill on 16:9 must either raise coverage >= 55% or refuse
try:
    fw, fh, cw, ch = rs.fg_geometry(dict(meta, vertical="blur_fill"), seg["zoom"])
    cov = ch / meta["out_h"]
    if cov < 0.55:
        fail(f"blur_fill 16:9 foreground coverage {cov:.0%} < 55% with no cover_crop escalation")
    ok(f"blur_fill coverage {cov:.0%} >= 55%")
except (TypeError, KeyError) as e:
    fail(f"geometry mode-awareness missing: {e}")

# 4. functional: cover_crop segment renders and is full-bleed
with tempfile.TemporaryDirectory() as td:
    srcf = os.path.join(td, "src.mp4")
    synth_video(srcf, dur=2.0, w=640, h=360)
    tl = {"meta": dict(meta, vertical="cover_crop"), "segments": [seg]}
    tlp = os.path.join(td, "tl.json")
    open(tlp, "w").write(__import__("json").dumps(tl))
    outdir = os.path.join(td, "segs")
    import json as _j
    sys.path.insert(0, os.path.dirname(rs.__file__))
    try:
        rs.main.__wrapped__  # never taken
    except AttributeError:
        pass
    # run via subprocess to isolate argparse main
    import subprocess
    p = subprocess.run([sys.executable, rs.__file__, "--source", srcf, "--timeline", tlp,
                        "--outdir", outdir, "--jobs", "1", "--crf", "28",
                        "--preset", "ultrafast"], capture_output=True, text=True)
    if p.returncode != 0:
        fail(f"cover_crop segment render failed:\n{p.stderr[-400:]}")
    outp = os.path.join(outdir, "seg_000.mp4")
    if not os.path.isfile(outp):
        fail("cover_crop segment not produced")
    ok("functional cover_crop render OK")

print("D4 PROBE: PASS (defect fixed)")
