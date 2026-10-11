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
    stage10 = wf[wf.find("Stage 10"):] if "Stage 10" in wf else ""
    if "G4_layout" not in stage10 or "assert" not in stage10:
        fail("W3 present: the iterate gate print does not REQUIRE draft G4 "
             "green - RED letterboxed drafts silently fed the creative loop")
    ok("iterate gate step asserts G4_layout green (letterboxed draft fails "
       "the run)")

    # ---- 2b) EXECUTE the gate-print script (CI lesson: the v2.2 W3 commit's
    # one-liner had an unbalanced paren that only fired in CI - a probe that
    # merely greps the YAML cannot catch that; run the heredoc for real) ----
    with tempfile.TemporaryDirectory() as gd:
        m = re.search(r"python3 - <<'PY'\n([\s\S]*?)\n\s*PY", stage10)
        if not m:
            fail("the stage-10 gate contract must be an executable heredoc "
                 "python block (grep-only one-liners already shipped a "
                 "SyntaxError to CI once)")
        script = m.group(1)
        # YAML block scalars are indented uniformly; dedent for exec
        script = "\n".join(ln[10:] if ln.startswith(" " * 10) else ln
                           for ln in script.splitlines())
        def run_case(gates, expect_rc, tag):
            cwd = os.path.join(gd, tag)
            gp = os.path.join(cwd, "reports")
            os.makedirs(gp, exist_ok=True)
            json.dump(gates, open(os.path.join(gp, "gates_report.json"), "w"))
            r = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True, cwd=cwd)
            if r.returncode != expect_rc:
                fail(f"stage-10 gate script rc={r.returncode} != {expect_rc} "
                     f"for {tag}: {(r.stderr or r.stdout)[-200:]}")
            return r
        base = {"ALL_GREEN": True, "PENDING": ["G9_latency"],
                "G4_layout": {"green": True, "value": "bar_fraction=0.000"},
                "G6_audio": {"green": True, "value": "outI=-15.6 via=archive_cc"}}
        r_ok = run_case(base, 0, "g4g6green")
        if "W6 label" not in r_ok.stdout:
            fail(f"green-G6 case must print the W6 label (got: {r_ok.stdout[-160:]})")
        red6 = json.loads(json.dumps(base))
        red6["G6_audio"] = {"green": False, "value": "outI=-14.8 outside band"}
        r_v = run_case(red6, 0, "g6variance")
        if "VARIANCE" not in r_v.stdout or "[-18,-14]" not in r_v.stdout:
            fail(f"G6 variance case must print the labelled wider band "
                 f"(got: {r_v.stdout[-160:]})")
        red4 = json.loads(json.dumps(base))
        red4["G4_layout"] = {"green": False, "value": "bar_fraction=0.870"}
        r_f = run_case(red4, 1, "g4red")
        if "W3: draft G4 must be green" not in (r_f.stderr + r_f.stdout):
            fail(f"G4-red case must fail with the W3 message")
        ok("gate script executes: G4-green/G6-green rc0 + W6 label; G6 "
           "variance labelled [-18,-14] non-fatal; G4-red fails with the W3 "
           "message")

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
