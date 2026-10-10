#!/usr/bin/env python3
"""E7: end-card ignores face avoidance.

Audit: the "AI VIDEO LAB" credit burns over the subject's face at ~15 s
(assemble.py pins the end-card to y=h*0.44 - mid-frame, where faces live).

Fix contract: end-card pinned to the bottom safe-zone band (y >= 86% height)
OR face-bbox avoidance reusing the captions-stage face cache; decision logged
per run.

Probe loads assemble.py and verifies the end-card geometry contract. On HEAD
the y=0.44h placement is present and no position helper exists -> FAILS.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module


def main():
    try:
        asm = load_module("assemble_under_test_e7", "scripts/montage/assemble.py")
    except Exception as e:
        fail(f"assemble.py unimportable: {e}")

    if not hasattr(asm, "endcard_positions"):
        fail("E7 contract missing: assemble.endcard_positions() - end-card geometry "
             "is hardcoded at y=h*0.44 (mid-frame, burns over faces)")

    oh = 1920
    y1, y2 = asm.endcard_positions(oh)
    band_top = 0.86 * oh
    if y1 < band_top:
        fail(f"E7 present: end-card first line at y={y1} < 86% band top "
             f"({band_top:.0f}) - it rides over the subject's face")
    if y2 + 10 > oh:
        fail(f"end-card second line falls off canvas: y2={y2} (h={oh})")
    ok(f"end-card pinned to bottom safe band: y1={y1} (>= {band_top:.0f}), y2={y2}")

    # the overlay strings actually emitted must carry the bottom-band anchor
    if hasattr(asm, "endcard_overlays"):
        fs_end = int(1080 * 0.052)
        fs_end2 = int(1080 * 0.026)
        ovs = asm.endcard_overlays(oh, fs_end, fs_end2, total=20.0,
                                   txt1="AI VIDEO LAB", txt2="FFMPEG x GITHUB ACTIONS",
                                   font="whatever.ttf", txtfiles={"end1": "/a",
                                                                  "end2": "/b"})
        joined = " ".join(ovs)
        if "h*0.44" in joined:
            fail("end-card overlays still anchor at h*0.44 (mid-frame)")
        if f"y={y1}" not in joined:
            fail(f"end-card overlays do not use the computed bottom-band y={y1}: "
                 f"{joined[:200]}")
        ok("end-card overlay strings carry the bottom-band anchor")

    # decision must be logged per run
    if not hasattr(asm, "endcard_decision"):
        fail("E7 contract missing: endcard_decision() log (placement policy must be "
             "recorded per run)")
    dec = asm.endcard_decision(oh)
    pol = str(dec.get("policy", "")).lower()
    if "bottom" not in pol and "86" not in pol.replace(".", ""):
        fail(f"end-card decision log lacks the placement policy: {dec}")
    ok(f"end-card decision logged: {json.dumps(dec)}")

    print("E7 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
