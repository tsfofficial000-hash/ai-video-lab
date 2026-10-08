#!/usr/bin/env python3
"""D1: qc.py blackdetect regex demands a space after colon; scan limited to first 10s.
ffmpeg prints `black_start:0` (no space) -> check is vacuous; black tail (18.5->26.17s
on the delivered run) is invisible. Probe must FAIL on HEAD, PASS after fix.
Fix contract: qc.parse_blackdetect(stderr) exists and parses `black_start:\\s*([\\d.]+)\\s+
black_end:\\s*([\\d.]+)`; whole-file scan (no `-t 10`)."""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_module, synth_black_windows, blackdetect_stderr, ok, fail

qc = load_module("qc_under_test", "scripts/cineforge/qc.py")
src = open(qc.__file__).read()

SAMPLE = ("[blackdetect @ 0x0] black_start:0 black_end:2 black_duration:2\n"
          "[blackdetect @ 0x0] black_start:18.503 black_end:26.17 black_duration:7.667")

# 1. parse function exists and handles real ffmpeg output (no space)
if not hasattr(qc, "parse_blackdetect"):
    fail("qc.parse_blackdetect() missing on HEAD - inline regex cannot be probed")
regions = qc.parse_blackdetect(SAMPLE)
if len(regions) != 2:
    fail(f"parse_blackdetect found {len(regions)} regions, expected 2 (regex demands space?)")
if abs(regions[0][0] - 0.0) > 0.01 or abs(regions[0][1] - 2.0) > 0.01:
    fail(f"first region wrong: {regions[0]}")
if abs(regions[1][0] - 18.503) > 0.01 or abs(regions[1][1] - 26.17) > 0.01:
    fail(f"black tail region not captured: {regions[1]}")
ok("parse_blackdetect captures `black_start:0` and the 18.5->26.17 tail")

# 2. whole-file scan (no -t 10 truncation)
if re.search(r'"-t",\s*"10"|"-t",\s*"10"', src) or re.search(r"-t 10\b", src):
    fail("qc.py still truncates blackdetect scan with -t 10")
ok("blackdetect scans the whole file (no -t 10)")

# 3. functional: real ffmpeg blackdetect on synthetic video with head+tail black
with tempfile.TemporaryDirectory() as td:
    v = os.path.join(td, "blk.mp4")
    synth_black_windows(v, dur=8.0)
    err = blackdetect_stderr(v)
    regions = qc.parse_blackdetect(err)
    if len(regions) < 2:
        fail(f"functional: only {len(regions)} black regions found in 8s synthetic "
             f"(expected 2: head 0-1.5s, tail 6-8s); stderr sample: {err[-300:]}")
    if regions[-1][0] < 5.5:
        fail(f"tail black region missed: {regions}")
    ok(f"functional blackdetect: {regions}")

print("D1 PROBE: PASS (defect fixed)")
