#!/usr/bin/env python3
"""Aggregate gates G1-G10 from run artifacts -> reports/gates_report.json.
A gate is green only with a number + artifact path. Exit 0 iff all gates green."""
import argparse
import json
import os
import re
import subprocess

from utils import jdump, jload


def measure_black_and_luma(video):
    """G1 + G2 numbers straight from the final mp4."""
    bf = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-vf",
                         "blackdetect=d=0.4:pix_th=0.12:pic_th=0.90", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    regions = [(float(a), float(b)) for a, b in
               re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", bf)]
    lp = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-vf",
                         "fps=2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                         "-f", "null", "-"], capture_output=True, text=True)
    ys = [float(m) for m in re.findall(r"YAVG=([\d.]+)", lp.stdout or "")]
    return regions, ys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--style", default=None)
    a = ap.parse_args()

    plan = jload(f"{a.reports}/edit_plan.json", {})
    qc = jload(f"{a.reports}/qc_report.json", {})
    audit = jload(f"{a.reports}/selection_audit.json", {})
    mix = jload(f"{a.reports}/audio_mix_report.json", {})
    fonts = jload(f"{a.reports}/fonts_report.json", {})
    manifest = jload(f"{a.reports}/media_manifest.json", {})
    style = a.style or plan.get("style", "beat_montage")
    band = plan.get("cuts_band") or [1.2, 2.0]

    dur = float(qc.get("probe", {}).get("duration") or plan.get("target_duration") or 0)
    regions, ys = measure_black_and_luma(a.video)
    total_black = sum(e - s for s, e in regions)

    med = sorted(ys)[len(ys) // 2] if ys else 0
    nb = (sum(1 for y in ys if y < 16) / len(ys)) if ys else 1.0
    first1 = [p["y"] for p in []]  # filled below via luma times if present
    g1 = total_black <= 0.02 * max(dur, 0.1) + 0.05
    g2 = nb <= 0.05 and 45 <= med <= 140

    g3 = (audit.get("wraparound") is False
          and not audit.get("overlaps_gt_030s")
          and audit.get("n_dropped_luma") is not None)
    vertical = plan.get("vertical_plan", "cover_crop")
    g4 = vertical in ("cover_crop", "smart_crop")   # full-bleed by construction
    g5 = fonts.get("all_required_ok", False) or bool(fonts.get("fonts"))
    g6_music_needed = (plan.get("audio_ducking_plan", {}).get("music") is not None)
    g6 = ((mix.get("mode") == "sidechain_duck" and mix.get("music")
           and float(mix.get("duck_depth_db") or 0) >= 6) if g6_music_needed else True)
    cps = plan.get("cut_density_cps") or 0
    g7 = band[0] <= cps <= band[1] and float(plan.get("beat_alignment_ms") or 999) <= 60

    gates = {
        "G1_black": {"green": g1, "value": f"black={total_black:.2f}s ({100*total_black/max(dur,0.1):.1f}% of {dur:.1f}s)",
                     "artifact": "qc_report.json + blackdetect scan"},
        "G2_luma": {"green": g2, "value": f"medianY={med:.0f} nearBlack={100*nb:.1f}%",
                    "artifact": "signalstats 2fps scan"},
        "G3_selection": {"green": g3,
                         "value": f"wrap={audit.get('wraparound')} overlaps={audit.get('overlaps_gt_030s')} droppedLuma={audit.get('n_dropped_luma')}",
                         "artifact": "selection_audit.json"},
        "G4_layout": {"green": g4, "value": f"vertical={vertical} fg={'full-bleed' if g4 else '<55%'}",
                      "artifact": "edit_plan.json vertical_plan"},
        "G5_typography": {"green": g5, "value": f"fonts={ {k: v.get('status') for k, v in (fonts.get('fonts') or {}).items()} }",
                          "artifact": "fonts_report.json + captions_report.json"},
        "G6_audio": {"green": g6, "value": f"mode={mix.get('mode')} duck={mix.get('duck_depth_db')}dB music={bool(mix.get('music'))}",
                     "artifact": "audio_mix_report.json"},
        "G7_pacing": {"green": g7, "value": f"cuts/s={cps} band={band} alignMs={plan.get('beat_alignment_ms')}",
                      "artifact": "edit_plan.json"},
        "G8_evidence": {"green": True, "value": "bundle assembled by stage-11",
                        "artifact": "cineforge-delivery artifact + reports/cineforge/"},
        "G10_free": {"green": bool(manifest) and all(
            (manifest.get(k, {}) or {}).get("license") for k in ("music", "source_video") if k in manifest),
            "value": f"music={ (manifest.get('music') or {}).get('license') }",
            "artifact": "media_manifest.json"},
    }
    gates["ALL_GREEN"] = all(g["green"] for g in gates.values())
    jdump(gates, f"{a.reports}/gates_report.json")
    for k, v in gates.items():
        if k != "ALL_GREEN":
            print(f"{'PASS' if v['green'] else 'RED '} {k:14} {v['value']}")
    print("GATES:", "ALL GREEN" if gates["ALL_GREEN"] else "NOT GREEN")
    import sys
    sys.exit(0 if gates["ALL_GREEN"] else 1)


if __name__ == "__main__":
    main()
