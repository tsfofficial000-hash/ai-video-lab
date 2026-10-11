#!/usr/bin/env python3
"""W2: the differential burn test must FAIL LOUDLY when fonts are
unresolvable - unmeasurable is RED, never green.

Audit reproduction (clean checkout, no system fonts, CF_FONTS_DIR set):
the re-burn rendered NOTHING (family unresolvable for the probe's
synthetic ass) -> deltas 0.000 -> `captions_burned` PASSED an uncaptioned
video ("tautology confirmed"). A delta of zero can equally mean
"perfectly burned" or "nothing rendered" - trusting it without a control
violates the evidence law.

Fix contract:
  - probes' synthetic ass embeds the exact family parsed from the font
    file in CF_FONTS_DIR (common.font_family_name) and every burn passes
    fontsdir= - resolution never relies on fontconfig fallback;
  - differential_caption_check runs a SELF-TEST before trusting any delta:
    a control re-burn of a known-text 1-frame ass (the ass-under-test's
    own families) onto a synthetic black frame must inject luma. When it
    injects nothing, the differential returns
    passed=False, reason="font resolution failed - differential not
    measurable" - and captions_burned goes RED.

Probe mechanics: fontconfig is NEUTERED via FONTCONFIG_FILE (empty font
config) so the ffmpeg children see zero system fonts on ANY machine -
this reproduces the audit's clean-checkout environment deterministically.
fonts_resolvable() then only succeeds through the explicit fontsdir leg.

Probe exit 0 = contract holds; exit 1 = defect present.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (ok, fail, load_module, synth_video, pick_font,
                    font_family_name, cf_path)

qc = load_module("qc_under_test_w2", "scripts/cineforge/qc.py")
captions = load_module("captions_under_test_w2", "scripts/cineforge/captions.py")

CUE = 2.0
REASON = "font resolution failed - differential not measurable"


def neuter_fontconfig(td):
    """Empty fontconfig config -> every ffmpeg child sees zero system fonts,
    reproducing the audit's clean checkout on any machine."""
    conf = os.path.join(td, "fonts.conf")
    open(conf, "w").write(
        '<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig></fontconfig>\n")
    os.environ["FONTCONFIG_FILE"] = conf
    return conf


def synthetic_ass(path, family):
    """Production-shaped ass: captions.py header + Cine style with the EXACT
    family baked in (parsed from the font file - never filename-guessed),
    one Dialogue spanning the sampled cue."""
    hdr = captions.ASS_HEADER.format(
        w=540, h=960, cap_font=family, hook_font=family, size=96,
        primary="&H00FFFFFF", outline="&H00000000", outline_w=5, shadow=3,
        ml=32, mr=32, mv=240, hook_size=150)
    events = [f"Dialogue: 0,{captions.ts(CUE - 0.4)},{captions.ts(CUE + 0.4)},"
              f"Cine,,0,0,0,,A CAPTION LINE"]
    open(path, "w").write(hdr + "\n" + "\n".join(events) + "\n")
    return path


def burn(src, ass, fontsdir, dest):
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src,
           "-vf", f"ass={ass}" + (f":fontsdir={fontsdir}" if fontsdir else ""),
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-c:a", "copy", dest]
    subprocess.run(cmd, check=True)
    return dest


def verdict(res):
    return next(r for r in res if r["check"] == "captions_burned")


def main():
    with tempfile.TemporaryDirectory() as td:
        neuter_fontconfig(td)
        qc.REPO_ROOT = td                      # no repo media/fonts, no repo globs
        os.environ.pop("CF_FONTS_DIR", None)   # scenario A: no fontsdir anywhere

        clean = synth_video(os.path.join(td, "clean.mp4"), dur=4.0, bright=True)
        ass = synthetic_ass(os.path.join(td, "probe.ass"), "DejaVu Sans")
        plan = {"caption_style": "viral_high_contrast", "resolution": "540x960",
                "target_duration": 4.0, "fps": 30}
        reports = os.path.join(td, "reports")
        os.makedirs(reports, exist_ok=True)
        json.dump({"style": "viral_high_contrast", "cues": [CUE], "events": 1,
                   "ass_path": os.path.abspath(ass)},
                  open(os.path.join(reports, "captions_report.json"), "w"))

        # ---- Scenario A: unresolvable fonts -> UNMEASURABLE = RED ----
        # (pre-fix: the re-burn rendered nothing, deltas 0.000, and
        # captions_burned PASSED this uncaptioned video - tautology)
        diff = qc.differential_caption_check(clean, ass, [CUE], fontsdir=None)
        if diff["passed"]:
            fail(f"W2 present: differential PASSES an uncaptioned video when "
                 f"fonts render nothing (deltas {diff['deltas']}) - tautology")
        if diff.get("reason") != REASON:
            fail(f"expected exact reason {REASON!r}, got {diff.get('reason')!r}")
        ok(f"unmeasurable differential REDs with the contract reason")

        res, _, _ = qc.check(clean, plan, reports, ass=ass, fontsdir=None)
        v = verdict(res)
        if v["passed"]:
            fail(f"W2 present: captions_burned PASSES an uncaptioned video in "
                 f"a clean checkout (detail: {v['detail']})")
        if REASON not in v["detail"]:
            fail(f"captions_burned detail must carry the unmeasurable reason "
                 f"(detail: {v['detail']})")
        ok("qc.check REDs the uncaptioned final loudly (reason propagated)")

        # ---- Scenario B: fontsdir leg -> measurable again, never fontconfig ----
        fdir = os.path.join(td, "cffonts")
        os.makedirs(fdir, exist_ok=True)
        shutil.copy(pick_font(), os.path.join(fdir, os.path.basename(pick_font())))
        os.environ["CF_FONTS_DIR"] = fdir
        family = font_family_name(pick_font())
        if not family:
            fail(f"font_family_name() must parse the exact family from "
                 f"{pick_font()}")
        ass_b = synthetic_ass(os.path.join(td, "probe_b.ass"), family)
        json.dump({"style": "viral_high_contrast", "cues": [CUE], "events": 1,
                   "ass_path": os.path.abspath(ass_b)},
                  open(os.path.join(reports, "captions_report.json"), "w"))

        diff_b = qc.differential_caption_check(clean, ass_b, [CUE], fontsdir=fdir)
        if diff_b["passed"] or diff_b.get("reason"):
            fail(f"fontsdir leg must be MEASURABLE (no font reason), got "
                 f"passed={diff_b['passed']} reason={diff_b.get('reason')!r}")
        if diff_b["max_rel_delta"] < 0.25:
            fail(f"uncaptioned video must show a huge injected-edge delta, "
                 f"got {diff_b}")
        ok(f"measurable differential: uncaptioned REDs at rel "
           f"{diff_b['max_rel_delta']} (no font reason)")

        capped = burn(clean, ass_b, fdir, os.path.join(td, "capped.mp4"))
        res2, _, _ = qc.check(capped, plan, reports, ass=ass_b, fontsdir=fdir)
        v2 = verdict(res2)
        if not v2["passed"]:
            fail(f"captioned final must PASS with resolvable fonts "
                 f"(detail: {v2['detail']})")
        if "differential" not in v2["detail"]:
            fail(f"pass must come from the differential path "
                 f"(detail: {v2['detail']})")
        ok("captioned final passes via the measurable differential path")

    print("W2 PROBE: PASS (self-test guards the differential; unmeasurable "
          "is RED; fontsdir leg stays measurable)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"W2 PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
