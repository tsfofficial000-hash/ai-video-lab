#!/usr/bin/env python3
"""D6: qc.py captions_burned is a tautology:
   ok("captions_burned", not plan.get("caption_style") or (reports+"/captions_report.json") and True)
It can never fail. Probe must FAIL on HEAD, PASS after fix.
Fix contract: burn-existence pixel test at 3 cue timestamps inside the safe-zone caption
band - a final WITHOUT burned captions must FAIL the check; a final WITH captions passes.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_module, synth_video, ok, fail

qc = load_module("qc_under_test_d6", "scripts/cineforge/qc.py")

CUES = [0.5, 2.0, 3.5]

with tempfile.TemporaryDirectory() as td:
    clean = synth_video(os.path.join(td, "clean.mp4"), dur=4.0, bright=True)
    capped = synth_video(os.path.join(td, "capped.mp4"), dur=4.0, bright=True,
                         drawtext="THIS IS A CAPTION")
    reports = os.path.join(td, "reports")
    os.makedirs(reports, exist_ok=True)
    json.dump({"style": "viral_high_contrast", "cues": CUES, "events": 3},
              open(os.path.join(reports, "captions_report.json"), "w"))
    plan = {"caption_style": "viral_high_contrast", "resolution": "540x960",
            "target_duration": 4.0, "fps": 30}

    res_clean, _, _ = qc.check(clean, plan, reports)
    clean_verdict = next(r for r in res_clean if r["check"] == "captions_burned")
    if clean_verdict["passed"]:
        fail(f"tautology confirmed: captions_burned PASSES on a final with NO captions "
             f"(detail: {clean_verdict['detail']})")
    ok("captions_burned correctly FAILS an uncaptioned final")

    res_cap, _, _ = qc.check(capped, plan, reports)
    cap_verdict = next(r for r in res_cap if r["check"] == "captions_burned")
    if not cap_verdict["passed"]:
        fail(f"captions_burned FAILS on a captioned final (detail: {cap_verdict['detail']})")
    ok("captions_burned correctly PASSES a captioned final")

    # plan without captions -> check skipped by design
    plan_nc = dict(plan, caption_style=None)
    res_nc, _, _ = qc.check(clean, plan_nc, reports)
    nc = next(r for r in res_nc if r["check"] == "captions_burned")
    if not nc["passed"]:
        fail("check should skip (pass) when plan has no caption_style")
    ok("no-caption plans skip the check")

print("D6 PROBE: PASS (defect fixed)")
