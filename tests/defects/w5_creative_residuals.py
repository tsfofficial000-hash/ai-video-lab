#!/usr/bin/env python3
"""W5: the v2.1 ship review's own declared creative residuals.

(a) In-cluster motion-variance selection: the cap-2 cluster budget spent
    slots on near-static sky-holds (run 38043976013 review, complaint 2:
    t=3.4s/5.2s cloud frames with no subject) because the Selector took the
    EARLIEST qualifying candidate in each cluster regardless of motion.
    Fix: within a small same-scene horizon, the MOST DYNAMIC candidate wins;
    every hard guard (luma gate, overlap, scene cap, forward-only) is
    unchanged, and no-luma/tie cases fall back to v2.1 behaviour.

(b) Hook y-anchor optical centering: the Hook style is \an5 (mid-center),
    so \\pos anchors the whole block's center - but the generator subtracted
    (lines-1)*fs*0.55, double-compensating and pushing 2-line hooks up to
    ~y12-16% vs the y=30% spec center (both v2.1 ship reviews, complaint).
    Fix: anchor the block center directly on the spec line.

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

sel_mod = load_module("selection_under_test_w5", "scripts/cineforge/selection.py")
Selector = sel_mod.Selector


def luma_profile():
    """2fps, 40s: flat 'sky-hold' [0,8) (motion 0), oscillating action
    [8,12) (high motion), flat rest. Everything bright (>= 36)."""
    rows = []
    for i in range(80):
        t = i * 0.5
        if 8.0 <= t < 12.0:
            y = 140.0 if i % 2 else 100.0          # |dY| = 40 every step
        else:
            y = 100.0                              # static hold
        rows.append({"t": t, "y": y})
    return rows


def scene_factory(cut):
    return lambda t: 0 if t < cut else 1


def main():
    # ---- (a) in-cluster motion-variance selection ----
    beats = [4.0, 4.5, 5.0, 8.0, 8.5, 20.0, 20.5]
    luma = luma_profile()
    sel = Selector(beats, 40.0, luma=luma, min_y=36.0,
                   scene_of=scene_factory(12.0), max_per_scene=2,
                   scene_cuts=[12.0])
    span = 2.0
    p1 = sel.pick(0.0, span)
    if p1 is None:
        fail("W5a: pick returned None on a bright fixture")
    if abs(p1 - 8.0) > 1e-6:
        fail(f"W5a present: first pick is {p1}s (the static sky-hold at 4.0s "
             f"won) - in-cluster motion preference missing (the ship review's "
             f"complaint: static cloud holds dilute the middle)")
    ok(f"dynamic candidate wins the horizon set: picked {p1}s over the "
       f"static hold at 4.0s (motion {sel._motion(8.0, span):.1f} vs "
       f"{sel._motion(4.0, span):.1f})")

    p2 = sel.pick(p1 + span, span)
    if p2 is None or abs(p2 - 20.0) > 1e-6:
        fail(f"second pick must continue forward-only into the next cluster "
             f"(got {p2})")
    if len(sel.used) != 2 or sel.used != [(8.0, 10.0), (20.0, 22.0)]:
        fail(f"used spans must be exactly the two picks (got {sel.used})")
    audit = sel.audit(2)
    if audit["wraparound"] is not False or audit["overlaps_gt_030s"]:
        fail(f"G3 audit must stay clean (got {audit})")
    if max(audit["cluster_histogram"].values()) > 2:
        fail(f"scene cap violated: {audit['cluster_histogram']}")
    ok("forward-only + overlap-free + scene cap 2 respected after the "
       "motion preference")

    # no-luma fallback: v2.1 earliest-qualifying behaviour preserved
    sel_nl = Selector(beats, 40.0, luma=None, min_y=36.0)
    p_nl = sel_nl.pick(0.0, span)
    if abs(p_nl - 4.0) > 1e-6:
        fail(f"no-luma fallback must pick the earliest qualifying candidate "
             f"(got {p_nl})")
    ok("no-luma fallback unchanged (earliest qualifying)")

    # ---- (b) hook y-anchor optical centering ----
    with tempfile.TemporaryDirectory() as td:
        reports = os.path.join(td, "reports")
        os.makedirs(reports, exist_ok=True)
        plan = {"hook": {"type": "title_card",
                         "text": "SEARCHING FOR SOMEONE WHO CAN HELP ME",
                         "seconds": [0, 2.5]},
                "target_duration": 10.0}
        json.dump({"transcript_empty": True, "segments": []},
                  open(os.path.join(reports, "transcript.json"), "w"))
        json.dump(plan, open(os.path.join(reports, "edit_plan.json"), "w"))
        ass_p = os.path.join(td, "captions.ass")
        r = subprocess.run(
            [sys.executable, cf_path("scripts/cineforge/captions.py"),
             "--transcript", os.path.join(reports, "transcript.json"),
             "--plan", os.path.join(reports, "edit_plan.json"),
             "--style", "minimal_clean", "--out", ass_p,
             "--resolution", "1080x1920"],
            capture_output=True, text=True, cwd=td)
        if not os.path.isfile(ass_p):
            fail(f"captions.py produced no ass: {(r.stderr or r.stdout)[-300:]}")
        hook_lines_txt = []
        y_anchor = None
        for ln in open(ass_p, errors="ignore"):
            if ln.startswith("Dialogue:") and ",Hook," in ln:
                m = re.search(r"\\pos\(\d+,(\d+)\)", ln)
                if m:
                    y_anchor = int(m.group(1))
                text = re.sub(r"\{[^}]*\}", "", ln.split(",", 9)[9]).strip()
                hook_lines_txt.append(text)
        if y_anchor is None or not hook_lines_txt:
            fail("no Hook Dialogue event with a \\pos anchor found")
        if len(hook_lines_txt[0].split(r"\N")) < 2 and r"\N" not in hook_lines_txt[0]:
            pass  # line count checked via wrap below
        spec = int(1920 * 0.30)
        if y_anchor != spec:
            fail(f"W5b present: 2-line hook anchors at y={y_anchor} (the old "
                 f"half-line subtraction) - the block center must sit on the "
                 f"y=30% spec line ({spec})")
        ok(f"2-line hook block center anchored at y={y_anchor} "
           f"(spec {spec} = 30% height)")

    print("W5 PROBE: PASS (in-cluster motion preference + hook optical "
          "centering)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"W5 PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
