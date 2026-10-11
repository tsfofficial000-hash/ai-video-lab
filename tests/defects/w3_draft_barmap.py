#!/usr/bin/env python3
"""W3: the draft path (98-iterate) was BAR-BLIND.

98's stage-01+02 block never ran bar_map.py (only make_proxy.sh in the 99
chain does), so reports/bar_map.json never existed on the draft path ->
edit_plan.py attached no per-segment active_crop -> every draft rendered
letterboxed -> draft G4 went RED -> and the creative loop reviewed frames
that production would never show (the shipped v2.1 final measures
bar_fraction=0.000; its own drafts were letterboxed).

Fix contract:
  - 98's stage-01+02 block runs bar_map.py (same proxy/meta inputs as the
    99 chain) BEFORE the edit-decision step, so edit_plan attaches segment
    crops (the attach mechanism itself is pinned by e1_bars);
  - the iterate evidence bundle copies reports/bar_map.json;
  - the iterate gate print REQUIRES draft G4 green - a letterboxed draft
    now fails the run instead of feeding the creative loop frames that
    production will never show.

Pixel leg: gate4() REDs a letterboxed cover_crop fixture and GREENs the
same fixture pre-cropped - the exact measurement the draft loop now runs.

Probe exit 0 = contract holds; exit 1 = defect present.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module, cf_path


def synth_fixture(path, mode, dur=8.0):
    """8s 540x960 cover_crop fixture: 'letterboxed' has black top/bottom bars
    (the defect's draft look); 'barfree' is full-bleed (the post-fix look)."""
    if mode == "letterboxed":
        vf = ("gradients=s=540x304:d=%.1f:c0=0x303050:c1=0xE0E0FF,format=yuv420p,"
              "pad=540:960:(ow-iw)/2:(oh-ih)/2:color=black" % dur)
    else:
        vf = "gradients=s=540x960:d=%.1f:c0=0x303050:c1=0xE0E0FF,format=yuv420p" % dur
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=%.1f" % dur,
                    "-map", "0:v", "-map", "1:a", "-t", str(dur), "-r", "30",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", path], check=True)
    return path


def main():
    gates = load_module("gates_under_test_w3", "scripts/cineforge/gates.py")

    # ---- 1) WORKFLOW WIRING: the draft path must build the bar map ----
    wf = open(cf_path(".github/workflows/98-iterate.yml")).read()
    if "bar_map.py" not in wf:
        fail("W3 present: 98-iterate.yml never runs bar_map.py - the draft "
             "path has no per-scene bar map, every draft renders letterboxed "
             "and draft G4 goes RED (creative loop reviews frames "
             "production will never show)")
    bar_pos = wf.find("bar_map.py")
    edl_pos = wf.find("edit_plan.py")
    if not (0 <= bar_pos < edl_pos):
        fail("bar_map.py must run BEFORE edit_plan.py so edit_plan attaches "
             "the segment crops (this run would plan against a missing map)")
    for needle, what in (
            ("--proxy media/proxy.mp4", "bar map consumes the draft proxy"),
            ("--out reports/bar_map.json", "bar map lands in reports/ where "
             "edit_plan reads it"),
            ("reports/bar_map.json", "evidence bundle copies the bar map")):
        if needle not in wf:
            fail(f"W3 present: {what} missing ({needle!r} not in "
                 f"98-iterate.yml)")
    ok("98 stage-01+02 runs bar_map.py before edit_plan; evidence copies it")

    # ---- 2) GATE CONTRACT: draft G4 must be REQUIRED green ----
    m = re.search(r"Draft gates[\s\S]*", wf) or None
    stage10 = wf[wf.find("Stage 10"):] if "Stage 10" in wf else ""
    if "G4_layout" not in stage10 or "assert" not in stage10:
        fail("W3 present: the iterate gate print does not REQUIRE draft G4 "
             "green - RED letterboxed drafts silently fed the creative loop")
    ok("iterate gate step asserts G4_layout green (letterboxed draft fails "
       "the run)")

    # ---- 3) PIXEL LEG: gate4 sees the bars the loop will now react to ----
    with tempfile.TemporaryDirectory() as td:
        plan = {"vertical_plan": "cover_crop", "resolution": "540x960"}
        lb = synth_fixture(os.path.join(td, "lb.mp4"), "letterboxed")
        bf = synth_fixture(os.path.join(td, "bf.mp4"), "barfree")
        g_lb, val_lb, _ = gates.gate4(lb, plan, 8.0)
        g_bf, val_bf, det_bf = gates.gate4(bf, plan, 8.0)
        if g_lb:
            fail(f"W3 pixel leg: a letterboxed draft passed G4 ({val_lb}) - "
                 f"the loop could never see the defect")
        if not g_bf:
            fail(f"W3 pixel leg: a bar-free draft failed G4 ({val_bf})")
        ok(f"gate4: letterboxed RED ({val_lb[:58]}...) vs bar-free GREEN "
           f"bar_fraction={det_bf.get('bar_fraction')}")

    print("W3 PROBE: PASS (draft path builds the bar map, evidence carries "
          "it, draft G4 is required green)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"W3 PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
