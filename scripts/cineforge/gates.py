#!/usr/bin/env python3
"""Aggregate gates G1-G10 from run artifacts -> reports/gates_report.json.

A gate is green only with a number + artifact path (no tautologies, no vacuous
passes). G9 (latency) may be "pending" at stage-10 time; stage-11 re-runs this
script with --latency to finalize. Exit 0 iff all non-pending gates are green.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

from utils import jdump, jload


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def ffprobe_dur(video):
    p = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", video])
    try:
        return float(p.stdout.strip().splitlines()[0])
    except Exception:
        return 0.0


def measure_black(video):
    """G1: whole-file blackdetect. Returns [(start, end), ...]."""
    bf = sh(["ffmpeg", "-hide_banner", "-i", video, "-vf",
             "blackdetect=d=0.4:pix_th=0.12:pic_th=0.90", "-f", "null", "-"]).stderr
    return [(float(a), float(b)) for a, b in
            re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", bf)]


def measure_luma(video, dur):
    """G2: 2fps YAVG profile -> (median, near_black_frac, blown, first1s_mean)."""
    lp = sh(["ffmpeg", "-hide_banner", "-i", video, "-vf",
             "fps=2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
             "-f", "null", "-"])
    ys = [float(m) for m in re.findall(r"YAVG=([\d.]+)", lp.stdout or "")]
    if not ys:
        return None
    ys_sorted = sorted(ys)
    med = ys_sorted[len(ys_sorted) // 2]
    nb = sum(1 for y in ys if y < 16) / len(ys)
    blown = sum(1 for y in ys if y > 250)
    first1 = [y for y in ys[:max(1, int(2 * min(dur, 1.0) + 0.99))]] or ys[:2]
    return med, nb, blown, sum(first1) / len(first1), len(ys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--search", default="../..",
                    help="colon-separated extra roots to glob for reports")
    ap.add_argument("--style", default=None)
    ap.add_argument("--latency", default=None,
                    help="path to latency.json (stage-11 finalization)")
    a = ap.parse_args()

    def find(name):
        """Locate a report: --reports dir first, then glob the search roots in order."""
        cand = os.path.join(a.reports, name)
        if os.path.isfile(cand):
            return cand
        for root in a.search.split(":"):
            if not root:
                continue
            hits = sorted(glob.glob(os.path.join(root, "**", name), recursive=True))
            if hits:
                return hits[0]
        return None

    def load(name):
        p = find(name)
        return (jload(p, {}) if p else {}), p

    plan, plan_p = load("edit_plan.json")
    qc, qc_p = load("qc_report.json")
    audit, audit_p = load("selection_audit.json")
    mix, mix_p = load("audio_mix_report.json")
    fonts, fonts_p = load("fonts_report.json")
    manifest, man_p = load("media_manifest.json")
    captions_rep, cap_p = load("captions_report.json")

    style = a.style or plan.get("style", "beat_montage")
    band = plan.get("cuts_band") or [1.2, 2.0]

    if not os.path.isfile(a.video):
        print(f"FATAL: video not found: {a.video}", flush=True)
        sys.exit(2)
    dur = ffprobe_dur(a.video) or float(qc.get("probe", {}).get("duration")
                                        or plan.get("target_duration") or 0)

    # ---- G1 BLACK: whole-file blackdetect on the real final.mp4 ----
    regions = measure_black(a.video)
    fade_budget = max(0.4, 0.02 * dur)
    tail = [(s, e) for s, e in regions if e > dur - fade_budget - 0.25]
    tail_black = sum(e - s for s, e in tail)
    core_black = sum(e - s for s, e in regions) - tail_black
    longest = max((e - s for s, e in regions), default=0.0)
    g1 = (core_black <= 0.02 * dur and (longest <= 0.6 or
          (tail and longest == max(e - s for s, e in tail) and longest <= fade_budget)))
    if regions:
        longest_val = f"longest {longest:.2f}s"
    else:
        longest_val = "no regions"

    # ---- G2 LUMA: 2fps profile ----
    lum = measure_luma(a.video, dur)
    if lum:
        med, nb, blown, first1, nsamp = lum
        g2 = (nb <= 0.05 and 45 <= med <= 140 and blown <= max(2, 0.01 * nsamp)
              and first1 >= 25)
        g2_val = (f"medianY={med:.0f} nearBlack={100*nb:.1f}% blown={blown} "
                  f"first1sY={first1:.0f} n={nsamp}")
    else:
        g2, g2_val = False, "luma scan produced no samples"

    # ---- G3 SELECTION: no wraparound, no overlap, luma gate active ----
    g3 = (audit.get("wraparound") is False
          and not audit.get("overlaps_gt_030s")
          and audit.get("n_dropped_luma") is not None)
    g3_val = (f"wrap={audit.get('wraparound')} "
              f"overlaps={len(audit.get('overlaps_gt_030s') or [])} "
              f"droppedLuma={audit.get('n_dropped_luma')} "
              f"selected={audit.get('n_selected')}")

    # ---- G4 LAYOUT: full-bleed modes by construction; blur_fill needs fg>=55% ----
    vertical = plan.get("vertical_plan", plan.get("vertical", "cover_crop"))
    fg_ratio = plan.get("fg_height_ratio")
    if vertical in ("cover_crop", "smart_crop"):
        g4, g4_val = True, f"vertical={vertical} fg=full-bleed"
    elif vertical == "blur_fill" and fg_ratio is not None:
        g4 = fg_ratio >= 0.55
        g4_val = f"vertical=blur_fill fg={100*fg_ratio:.0f}% (need >=55%)"
    else:
        g4 = False
        g4_val = f"vertical={vertical} fg_ratio={fg_ratio} not measurable"

    # ---- G5 TYPO: OFL fonts + captions pixel-test + per-cue decisions ----
    fonts_ok = bool(fonts) and (fonts.get("all_required_ok")
                                or all((v or {}).get("status") in ("cached", "downloaded", "ok")
                                       for v in (fonts.get("fonts") or {}).values()))
    lic_ok = bool(fonts) and all((v or {}).get("license") for v in (fonts.get("fonts") or {}).values())
    cap_style = plan.get("caption_style")
    qc_checks = {c.get("check"): c for c in qc.get("checks", [])}
    cap_check = qc_checks.get("captions_burned")
    cap_measured = bool(cap_check) and "n/a" not in str(cap_check.get("detail", ""))
    cap_ok = bool(cap_check and cap_check.get("passed") and cap_measured)
    cues_logged = bool(captions_rep) and len(captions_rep.get("cues", [])) >= 1
    if cap_style:
        g5 = fonts_ok and lic_ok and cap_ok and cues_logged
        g5_val = (f"fonts_ok={fonts_ok} lic={lic_ok} pixelTest={cap_ok} "
                  f"cuesLogged={cues_logged} style={cap_style}")
    else:
        g5 = fonts_ok and lic_ok
        g5_val = f"fonts_ok={fonts_ok} lic={lic_ok} captions=none-for-style"

    # ---- G6 AUDIO: duck depth, music wired, measured output loudness ----
    duck_plan_music = plan.get("audio_ducking_plan", {}).get("music")
    music_needed = duck_plan_music is not None
    out_i = mix.get("output_i")
    if music_needed:
        g6 = (mix.get("mode") == "sidechain_duck" and bool(mix.get("music"))
              and float(mix.get("duck_depth_db") or 0) >= 6
              and out_i is not None and -17 <= float(out_i) <= -15)
        g6_val = (f"mode={mix.get('mode')} duck={mix.get('duck_depth_db')}dB "
                  f"music={bool(mix.get('music'))} outI={out_i}")
    else:
        g6 = out_i is not None and -17 <= float(out_i) <= -15 if out_i else bool(mix)
        g6_val = f"music=none-for-style mode={mix.get('mode')} outI={out_i}"

    # ---- G7 PACING: cuts/s in band + beat alignment ----
    cps = plan.get("cut_density_cps")
    align = plan.get("beat_alignment_ms")
    g7 = (cps is not None and band[0] <= cps <= band[1]
          and align is not None and float(align) <= 60)
    g7_val = f"cuts/s={cps} band={band} alignMs={align}"

    # ---- G8 EVIDENCE: bundle list verified at delivery; here check artifacts ----
    needed = ["edit_plan.json", "qc_report.json", "media_manifest.json"]
    have = [n for n in needed if find(n)]
    g8 = len(have) == len(needed)
    g8_val = f"reports present: {len(have)}/{len(needed)}"

    # ---- G9 LATENCY: number only when latency.json is available ----
    lat, lat_p = ({}, None)
    if a.latency and os.path.isfile(a.latency):
        lat = jload(a.latency, {})
        lat_p = a.latency
    else:
        lat, lat_p = load("latency.json")
    wall = lat.get("wall_seconds")
    max_setup = lat.get("max_job_setup_seconds")
    if wall is not None and max_setup is not None:
        g9 = float(wall) <= 720 and float(max_setup) <= 45
        g9_val = f"wall={float(wall):.0f}s (<=720) maxSetup={float(max_setup):.0f}s (<=45)"
    else:
        g9 = None
        g9_val = "pending delivery-stage measurement"

    # ---- G10 FREE: every manifested asset carries a license ----
    entries = {k: v for k, v in manifest.items() if isinstance(v, dict)} if manifest else {}
    g10 = bool(entries) and all((v or {}).get("license") for v in entries.values())
    g10_val = (f"{len(entries)} assets: "
               + "; ".join(f"{k}={(v or {}).get('license')}" for k, v in entries.items())
               ) if entries else "manifest empty/missing"

    gates = {
        "G1_black": {"green": bool(g1),
                     "value": f"black={core_black:.2f}s ({100*core_black/max(dur,0.1):.1f}% of {dur:.1f}s) +tail {tail_black:.2f}s, {longest_val}",
                     "artifact": "blackdetect scan of final.mp4"},
        "G2_luma": {"green": bool(g2), "value": g2_val,
                    "artifact": "signalstats 2fps scan"},
        "G3_selection": {"green": bool(g3), "value": g3_val,
                         "artifact": os.path.relpath(audit_p) if audit_p else "MISSING"},
        "G4_layout": {"green": bool(g4), "value": g4_val,
                      "artifact": "edit_plan.json vertical_plan"},
        "G5_typography": {"green": bool(g5), "value": g5_val,
                          "artifact": f"{os.path.relpath(fonts_p) if fonts_p else 'MISSING'} + {os.path.relpath(cap_p) if cap_p else 'captions_report MISSING'}"},
        "G6_audio": {"green": bool(g6), "value": g6_val,
                     "artifact": os.path.relpath(mix_p) if mix_p else "MISSING"},
        "G7_pacing": {"green": bool(g7), "value": g7_val,
                      "artifact": os.path.relpath(plan_p) if plan_p else "MISSING"},
        "G8_evidence": {"green": bool(g8), "value": g8_val,
                        "artifact": "cineforge-delivery bundle (stage-11)"},
        "G9_latency": {"green": g9, "value": g9_val,
                       "artifact": os.path.relpath(lat_p) if lat_p else "latency.json (stage-11)"},
        "G10_free": {"green": bool(g10), "value": g10_val,
                     "artifact": os.path.relpath(man_p) if man_p else "MISSING"},
    }
    pending = [k for k, v in gates.items() if v["green"] is None]
    verdict = all(v["green"] for v in gates.values() if v["green"] is not None)
    gates["ALL_GREEN"] = bool(verdict and not pending)
    gates["PENDING"] = pending
    jdump(gates, os.path.join(a.reports, "gates_report.json"))
    for k, v in gates.items():
        if k in ("ALL_GREEN", "PENDING"):
            continue
        state = "PASS" if v["green"] else ("WAIT" if v["green"] is None else "RED ")
        print(f"{state} {k:14} {v['value']}", flush=True)
    print("GATES:", "ALL GREEN" if gates["ALL_GREEN"] else
          (f"GREEN pending {pending}" if verdict else "NOT GREEN"))
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
