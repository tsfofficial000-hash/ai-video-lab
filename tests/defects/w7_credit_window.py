#!/usr/bin/env python3
"""W4-CI: the outro credit window was anchored to a PHANTOM plan total.

Found by the post-veto sweep re-run 38126217839 (sad_emotional): QC RED'd
music_credit_on_screen with 'credit window 8.9-11.1s falls outside the
final duration 7.90s'. Root cause: captions.py src_to_out_map computed

    total = cum + rows[-1]["out_dur"]

but cum ALREADY includes the last segment (its transition_after does not
consume timeline) - the last segment was double-counted. Measured on the
artifact plan: correct model 7.90 == delivered 7.90; the code's total was
11.30 (+3.4 = last segment). The ship run masked it (18.44 vs 18.37 - the
credit cue still fell inside the video); scarcity-shrunk plans expose it:
the credit event lands beyond the end of the video and is never visible -
exactly what the W1 pixel verification is for.

Fix: total = cum (the last transition_after is inside the last segment's
out_dur; the model matches edit_plan's own duration_chain.delivered, verified
on run-38109649950: cum 18.44 == plan delivered 18.44 == ffprobe 18.37 +-xfade
rounding).

Probe exit 0 = contract holds; exit 1 = defect present.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, cf_path

CREDIT = ("Music: Healing - Kevin MacLeod (incompetech.com), "
          "Licensed under CC BY 4.0")


def main():
    with tempfile.TemporaryDirectory() as td:
        reports = os.path.join(td, "reports")
        os.makedirs(reports, exist_ok=True)
        # 2-segment plan: od 4.0 + od 3.9, no inter-segment transition ->
        # delivered total = 7.9 (the sad draft's shape)
        plan = {"music_credit": CREDIT,
                "target_duration": 7.9,
                "hook": {"type": "title_card", "text": "GO",
                         "seconds": [0, 2.5]},
                "segments": [
                    {"src_start": 0.0, "src_dur": 4.0, "out_dur": 4.0,
                     "speed": 1.0, "transition_after": {"type": "fade", "dur": 0.0}},
                    {"src_start": 4.0, "src_dur": 3.9, "out_dur": 3.9,
                     "speed": 1.0, "transition_after": {"type": "fadeblack",
                                                        "dur": 0.4}},
                ]}
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

        def seconds(ts_str):
            h, m, s = ts_str.strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)

        win = None
        for ln in open(ass_p, errors="ignore"):
            if ln.startswith("Dialogue:") and CREDIT[:24] in re.sub(
                    r"\{[^}]*\}", "", ln):
                parts = ln.rstrip("\n").split(",", 9)
                win = (seconds(parts[1]), seconds(parts[2]))
                break
        if not win:
            fail("no credit Dialogue event in the generated ass")
        c0, c1 = win
        delivered = 7.9
        if c1 > delivered - 0.05:
            fail(f"W4-CI present: credit window {c0:.2f}-{c1:.2f}s exceeds "
                 f"the delivered duration {delivered}s - the plan total was "
                 f"inflated by double-counting the last segment "
                 f"(pre-fix: 8.9-11.1s); the credit would never be visible")
        if not (delivered - 2.4 - 0.05 <= c0 <= delivered - 0.2):
            fail(f"credit window must sit in the outro band of the DELIVERED "
                 f"duration (got {c0:.2f}-{c1:.2f}s vs total {delivered}s)")
        ok(f"credit window {c0:.2f}-{c1:.2f}s anchored to the delivered "
           f"duration {delivered}s (2.4s outro event)")

    print("W4-CI PROBE: PASS (credit window anchored to the delivered "
          "duration; no phantom plan total)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"W4-CI PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
