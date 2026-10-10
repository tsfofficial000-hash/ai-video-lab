#!/usr/bin/env python3
"""E2: G4 layout gate passes 'by construction'.

Audit: gates.py `if vertical in ("cover_crop", "smart_crop"): g4 = True` never
looks at pixels - that is how E1 shipped green.

Fix contract: G4 becomes MEASURED - 2 fps sample; crop top 8% and bottom 8%
bands; in full-bleed modes >= 95% of samples must have band-mean Y >= 25;
report bar_fraction. blur_fill path keeps fg_ratio >= 55%.

Probe: renders a letterboxed 'final' whose edge bands are dark, runs gates.py
on a plan claiming cover_crop, and asserts G4 goes RED. A clean full-bleed
final must stay GREEN. On HEAD G4 is green for BOTH -> green-by-construction
defect present -> probe FAILS.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def synth(video, barred, dur=6.0, w=540, h=960):
    if barred:
        vf = ("gradients=s=%dx%d:d=%.1f:c0=0x204060:c1=0xF0D080,format=yuv420p,"
              "drawbox=x=0:y=0:w=iw:h=%d:color=black:t=fill,"
              "drawbox=x=0:y=ih-%d:w=iw:h=%d:color=black:t=fill"
              % (w, h, dur, int(h * 0.12), int(h * 0.12), int(h * 0.12)))
    else:
        vf = "gradients=s=%dx%d:d=%.1f:c0=0x204060:c1=0xF0D080,format=yuv420p" % (w, h, dur)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=%.1f" % dur,
                    "-map", "0:v", "-map", "1:a", "-t", str(dur), "-r", "30",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", video], check=True)
    return video


def band_ys(video):
    """Per-second mean luma of top and bottom 8% bands."""
    ys = {}
    for band, vf in (("top", "crop=iw:ih*0.08:0:0"),
                     ("bottom", "crop=iw:ih*0.08:0:ih*0.92")):
        p = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-vf",
                            "fps=2," + vf + ",signalstats,metadata=print:"
                            "key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
                           capture_output=True, text=True)
        ys[band] = [float(m) for m in re.findall(r"YAVG=([\d.]+)", p.stdout or "")]
    return ys


def fabricate_reports(td, plan_extra=None):
    reports = os.path.join(td, "reports")
    os.makedirs(reports, exist_ok=True)
    plan = {"style": "beat_montage", "mood": "cinematic",
            "target_duration": 6.0, "requested_duration": 6.0,
            "aspect_ratio": "9:16", "fps": 30, "resolution": "540x960",
            "vertical_plan": "cover_crop", "segments": [],
            "cut_density_cps": 1.6, "cuts_band": [1.2, 2.0],
            "beat_alignment_ms": 10.0,
            "hook": {"type": "title_card", "text": "TEST"},
            "audio_ducking_plan": {"mode": "keep_source", "music": None},
            "caption_style": None}
    plan.update(plan_extra or {})
    json.dump(plan, open(os.path.join(reports, "edit_plan.json"), "w"))
    json.dump({"wraparound": False, "overlaps_gt_030s": [], "n_dropped_luma": 0,
               "n_selected": 1, "n_candidates": 2},
              open(os.path.join(reports, "selection_audit.json"), "w"))
    json.dump({"status": "pass", "checks": [], "repairs": []},
              open(os.path.join(reports, "qc_report.json"), "w"))
    json.dump({"synthetic_source": {"license": "CC0 synthetic probe asset"}},
              open(os.path.join(reports, "media_manifest.json"), "w"))
    return reports


def run_gates(video, reports, td):
    out = os.path.join(td, "gates_out")
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "cineforge", "gates.py"),
                        "--video", video, "--reports", reports, "--search", reports],
                       capture_output=True, text=True, cwd=os.path.join(REPO, "scripts", "cineforge"))
    gr = os.path.join(reports, "gates_report.json")
    if not os.path.isfile(gr):
        # gates.py writes relative to its CWD reports dir; fall back to scan
        hits = [os.path.join(dp, "gates_report.json") for dp, _, _ in os.walk(td)]
        gr = hits[0] if hits else None
    if not gr:
        fail(f"gates_report.json not produced ({r.stderr[-300:]})")
    return json.load(open(gr)), r


def main():
    with tempfile.TemporaryDirectory() as td:
        barred = synth(os.path.join(td, "barred.mp4"), barred=True)
        clean = synth(os.path.join(td, "clean.mp4"), barred=False)

        ys = band_ys(barred)
        dark_samples = sum(1 for t, b in zip(ys["top"], ys["bottom"]) if min(t, b) < 25)
        if dark_samples == 0:
            fail("probe setup broken: barred video shows no dark edge bands")
        ok(f"barred video truly has dark edge bands ({dark_samples} dark samples)")

        reports = fabricate_reports(td)
        g_barred, _ = run_gates(barred, reports, td)
        g4_barred = g_barred.get("G4_layout", {})
        if g4_barred.get("green"):
            fail(f"E2 present: G4 green-by-construction - a letterboxed 'final' with "
                 f"{dark_samples} dark edge samples passes cover_crop G4 "
                 f"(value: {g4_barred.get('value')!r}, no pixels were measured)")
        if "bar_fraction" not in json.dumps(g4_barred):
            fail(f"G4 is red for the barred final but does not report bar_fraction "
                 f"(value: {g4_barred.get('value')!r})")
        ok(f"G4 correctly RED for barred final: {g4_barred.get('value')}")

        reports2 = fabricate_reports(os.path.join(td, "r2"))
        g_clean, _ = run_gates(clean, reports2, td)
        g4_clean = g_clean.get("G4_layout", {})
        if not g4_clean.get("green"):
            fail(f"G4 must stay GREEN for a genuinely full-bleed final "
                 f"(value: {g4_clean.get('value')!r})")
        ok(f"G4 correctly GREEN for clean full-bleed final: {g4_clean.get('value')}")

    print("E2 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
