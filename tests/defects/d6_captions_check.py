#!/usr/bin/env python3
"""D6 + R1: the captions_burned probe must be HERMETIC and PATH-EXPLICIT.

Audit R1: this probe used to call qc.check() WITHOUT an ass file, so QC fell
to the legacy absolute white-ratio path and the verdict depended on the
machine's font metrics (independent rerun: a captioned 540x960 video measured
0.264-0.278% white vs the 0.3% threshold -> false RED with Montserrat-Bold;
the original author's DejaVu-Bold machine passed by a hair).

Fix contract (R1):
  - the probe synthesizes its OWN tiny ass, matching production semantics
    (captions.py ASS_HEADER, bottom safe-zone Cine style, Dialogue events
    spanning the sampled cues), and burns it itself - no dependence on any
    pre-existing repo state or font metrics;
  - it asserts the DIFFERENTIAL re-burn path is the one QC actually used
    (detail string), never the absolute fallback, when the ass is available;
  - it also pins the R2 labels: auto-discovery via captions_report.json and
    the labelled 0.15% FALLBACK when no ass exists anywhere.

Probe exit 0 = contract holds; exit 1 = defect present.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_module, synth_video, ok, fail, pick_font

qc = load_module("qc_under_test_d6", "scripts/cineforge/qc.py")
captions = load_module("captions_under_test_d6", "scripts/cineforge/captions.py")

CUES = [0.5, 2.0, 3.5]


def font_family():
    f = os.path.basename(pick_font())
    if "Montserrat" in f:
        return "Montserrat"
    if "Anton" in f:
        return "Anton"
    return "DejaVu Sans"


def tiny_ass(path):
    """Production-shaped ASS: captions.py header, bottom-band Cine style,
    one <=18-char line per production wrap rules, events spanning each cue."""
    fam = font_family()
    hdr = captions.ASS_HEADER.format(
        w=540, h=960, cap_font=fam, hook_font=fam, size=96,
        primary="&H00FFFFFF", outline="&H00000000", outline_w=5, shadow=3,
        ml=32, mr=32, mv=240, hook_size=150)
    events = []
    for t in CUES:
        events.append(f"Dialogue: 0,{captions.ts(max(0.0, t - 0.4))},"
                      f"{captions.ts(t + 0.4)},Cine,,0,0,0,,A CAPTION LINE")
    open(path, "w").write(hdr + "\n" + "\n".join(events) + "\n")
    return path


def burn(src, ass, fontsdir, dest):
    vf = f"ass={ass}:fontsdir={fontsdir}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "copy", dest], check=True)
    return dest


def verdict(res, name):
    return next(r for r in res if r["check"] == "captions_burned")


def main():
    with tempfile.TemporaryDirectory() as td:
        # hermetic envelope: QC's repo-root glob + font discovery both resolve
        # inside the sandbox (CF_FONTS_DIR only - no system font assumptions)
        qc.REPO_ROOT = td
        fontsdir = os.path.dirname(pick_font())
        os.environ["CF_FONTS_DIR"] = fontsdir

        clean = synth_video(os.path.join(td, "clean.mp4"), dur=4.0, bright=True)
        ass = tiny_ass(os.path.join(td, "probe_burn.ass"))
        capped = burn(clean, ass, fontsdir, os.path.join(td, "capped.mp4"))

        reports = os.path.join(td, "reports")
        os.makedirs(reports, exist_ok=True)
        json.dump({"style": "viral_high_contrast", "cues": CUES, "events": 3,
                   "ass_path": os.path.abspath(ass)},
                  open(os.path.join(reports, "captions_report.json"), "w"))
        plan = {"caption_style": "viral_high_contrast", "resolution": "540x960",
                "target_duration": 4.0, "fps": 30}

        # 1) captioned final, NO --ass argument: QC must auto-discover the ass
        #    recorded in captions_report.json and run the DIFFERENTIAL test
        res_cap, _, _ = qc.check(capped, plan, reports)
        v = verdict(res_cap, "capped")
        if not v["passed"]:
            fail(f"captioned final must PASS via auto-discovered differential "
                 f"path (detail: {v['detail']})")
        if "differential" not in v["detail"] or "FALLBACK" in v["detail"]:
            fail(f"R1 present: QC did not use the differential path for a "
                 f"captioned final (detail: {v['detail']})")
        if "captions_report.json" not in v["detail"]:
            fail(f"R2 marker missing: detail must state the ass was "
                 f"auto-discovered from captions_report.json (detail: {v['detail']})")
        ok(f"captioned final PASSES via auto-discovered differential path")

        # 2) uncaptioned final, same auto-discovery: re-burn injects glyph
        #    edges -> the differential test must FAIL it (tautology dead)
        res_clean, _, _ = qc.check(clean, plan, reports)
        v = verdict(res_clean, "clean")
        if v["passed"]:
            fail(f"tautology confirmed: captions_burned PASSES on a final with "
                 f"NO captions (detail: {v['detail']})")
        if "differential" not in v["detail"] or "FALLBACK" in v["detail"]:
            fail(f"differential path not used on the uncaptioned final "
                 f"(detail: {v['detail']})")
        ok("uncaptioned final correctly FAILS the differential re-burn test")

        # 3) no ass anywhere -> the absolute ratio is a labelled LAST-RESORT
        #    fallback at 0.15% and must NOT false-RED the captioned fixture
        #    (the audit's machine-dependent false-RED case)
        os.remove(ass)
        json.dump({"style": "viral_high_contrast", "cues": CUES, "events": 3,
                   "ass_path": os.path.join(td, "missing", "gone.ass")},
                  open(os.path.join(reports, "captions_report.json"), "w"))
        res_fb, _, _ = qc.check(capped, plan, reports)
        v = verdict(res_fb, "fallback")
        if "FALLBACK" not in v["detail"] or "0.15%" not in v["detail"]:
            fail(f"fallback path must be labelled 'FALLBACK ... 0.15% threshold' "
                 f"in the detail string (detail: {v['detail']})")
        if not v["passed"]:
            fail(f"R2 present: the 0.15%-labelled fallback still false-REDs a "
                 f"correctly captioned 540x960 final (detail: {v['detail']})")
        ok("ass-less invocation uses the labelled 0.15% FALLBACK and passes a "
           "correctly captioned small-frame final")

        # 4) plan without captions -> check skipped by design
        plan_nc = dict(plan, caption_style=None)
        res_nc, _, _ = qc.check(clean, plan_nc, reports)
        nc = verdict(res_nc, "no-caption")
        if not nc["passed"]:
            fail("check should skip (pass) when plan has no caption_style")
        ok("no-caption plans skip the check")

    print("D6 PROBE: PASS (defect fixed; R1 hermeticity + R2 path labels verified)")


if __name__ == "__main__":
    main()
