#!/usr/bin/env python3
"""D3: segment selection wrap-around replays the opening; no luma gate; no end-card
exclusion; duplicate/overlapping source ranges possible (evidence: run 37746375946
segments 42-48 == 0-6, 9.3s of output on black cards).
Probe must FAIL on HEAD, PASS after fix.
Fix contract: forward-only selection, no wrap-around, no src-range overlap > 0.3s,
luma gate (window min-Y >= 30) honored, end-card/dark zones excluded, and both
edit_plan.py and montage/build_timeline.py free of the `usable[0] + 0.37` replay."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_module, cf_path, ok, fail

edit_plan = load_module("edit_plan_under_test", "scripts/cineforge/edit_plan.py")

# fixture: 30s source, beat grid 136bpm from 1.8s; forces the cursor past the end on HEAD
DUR = 30.0
beats = []
t = 1.8
while t < DUR - 1.2:
    beats.append(round(t, 3))
    t += 60.0 / 136.0
beats_json = {"tempo": 136.0, "beats": beats,
              "energy_peak_starts": [14.0], "sections": [], "duration": DUR}
meta = {"duration": DUR, "width": 1920, "height": 1080, "fps": 30.0}
styles = json.load(open(cf_path("configs/styles.json")))
style_cfg = dict(styles["beat_montage"])
# all-bright luma profile at 2fps (post-fix signature takes it; HEAD does not)
luma = [{"t": round(i * 0.5, 2), "y": 110} for i in range(int(DUR * 2))]

try:
    res = edit_plan.build_timeline(meta, beats_json, style_cfg, "beat_montage", 26.0, luma=luma)
    print("  (build_timeline accepted luma= kwarg)")
except TypeError:
    res = edit_plan.build_timeline(meta, beats_json, style_cfg, "beat_montage", 26.0)
    print("  (build_timeline has no luma= kwarg - luma gate absent)")
segs = res[0] if isinstance(res, tuple) else res

# constraint 1: no duplicate src_starts
starts = [round(s["src_start"], 3) for s in segs]
dups = {s for s in starts if starts.count(s) > 1}
if dups:
    fail(f"duplicate src_starts (wrap-around replay): {sorted(dups)[:6]}")
ok("no duplicate src_start values")

# constraint 2: no overlapping src ranges > 0.3s
spans = sorted((s["src_start"], s["src_start"] + s["src_dur"]) for s in segs)
worst = 0.0
for (a1, a2), (b1, b2) in zip(spans, spans[1:]):
    ov = a2 - b1
    if ov > worst:
        worst = ov
if worst > 0.3:
    fail(f"source ranges overlap by {worst:.2f}s (> 0.3s allowed)")
ok(f"no src-range overlap > 0.3s (worst {worst:.2f}s)")

# constraint 3: no wrap-around (opening visited exactly once)
mn = min(starts)
openers = [s for s in starts if s <= mn + 1.0]
if len(openers) > 1:
    fail(f"wrap-around: opening revisited by {len(openers)} segments")
ok("forward-only selection: opening visited once")

# constraint 4: dark windows never selected (post-fix luma gate)
dark_luma = [{"t": round(i * 0.5, 2),
              "y": 8 if 10.0 <= i * 0.5 <= 14.0 else 110} for i in range(int(DUR * 2))]
try:
    res2 = edit_plan.build_timeline(meta, beats_json, style_cfg, "beat_montage", 20.0, luma=dark_luma)
    segs2 = res2[0] if isinstance(res2, tuple) else res2
    bad = [s for s in segs2 if 9.7 <= s["src_start"] <= 14.3]
    if bad:
        fail(f"luma gate ignored: {len(bad)} segments start inside dark window 10-14s")
    ok("luma gate excludes dark windows")
except TypeError:
    fail("no luma= support -> dark-window gate unimplemented")

# constraint 5: montage engine path carries the same fix (no literal wrap-around)
mt_src = open(cf_path("scripts/montage/build_timeline.py")).read()
if "usable[0] + 0.37" in mt_src:
    fail("montage/build_timeline.py still contains the `usable[0] + 0.37` wrap-around")
if "selection_audit" not in open(cf_path("scripts/cineforge/edit_plan.py")).read():
    fail("edit_plan.py does not emit a selection_audit manifest")
ok("montage engine de-wrapped; selection_audit emitted")

print("D3 PROBE: PASS (defect fixed)")
