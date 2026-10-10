#!/usr/bin/env python3
"""Stage 10: QC + auto-repair -> reports/qc_report.json
Checks: existence, probe, duration, resolution, fps, audio, loudness, black frames,
silence, captions presence, size, hook motion. Repairs: remux/rescale/renormalize."""
import argparse
import json
import os
import re
import subprocess
import sys

from utils import jdump, jload, ffprobe_json, record_stage
import time


def parse_blackdetect(stderr):
    """Parse ffmpeg blackdetect lines. ffmpeg prints `black_start:0` (no space),
    so the separator must allow optional whitespace (defect D1)."""
    return [(float(a), float(b)) for a, b in re.findall(
        r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", stderr)]


def luma_profile(path, fps=2):
    """2fps YAVG sample -> [{t, y}] (gate G2 + G1 first-second rule)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf",
                        f"fps={fps},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    times, ys = [], []
    for ln in (p.stdout or "").splitlines():
        mt = re.search(r"pts_time:([\d.]+)", ln)
        my = re.search(r"YAVG=([\d.]+)", ln)
        if mt:
            times.append(float(mt.group(1)))
        if my:
            ys.append(float(my.group(1)))
    return [{"t": t, "y": y} for t, y in zip(times, ys)]


def caption_band_white_ratio(path, t, band=(0.60, 0.92), white=232):
    """Fraction of near-white pixels in the caption band at time t (D6).
    geq masks pixels >= white to 255, else 0; YAVG/255 then equals the ratio.
    Threshold 232: compressed bold-white caption cores survive well above it
    (measured 6.5% ratio on burned text) while normal footage stays near 0."""
    vf = (f"crop=iw:ih*{band[1]-band[0]:.2f}:0:ih*{band[0]:.2f},"
          "geq=lum='if(gt(lum(X,Y)," + str(white) + "),255,0)':cb=128:cr=128,"
          "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-")
    p = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(t), "-i", path,
                        "-frames:v", "1", "-vf", vf, "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"YAVG=([\d.]+)", p.stdout or "")
    return (float(m.group(1)) / 255.0) if m else 0.0


def _band_edge_density(path, t, band, vf_prefix=""):
    """Mean sobel edge magnitude of the caption band at time t."""
    vf = (vf_prefix + "format=gray,"
          f"crop=iw:ih*{band[1]-band[0]:.2f}:0:ih*{band[0]:.2f},"
          "sobel,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-")
    p = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(t), "-i", path,
                        "-frames:v", "1", "-vf", vf, "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"YAVG=([\d.]+)", p.stdout or "")
    return float(m.group(1)) if m else 0.0


def differential_caption_check(video, ass, cues, fontsdir=None,
                               band=(0.60, 0.92), max_rel_delta=0.25):
    """N1: DIFFERENTIAL caption burn-existence (replaces the absolute white
    ratio, which false-passes on bright in-band content).

    Method: re-burn the ASS onto the final at each cue time and measure the
    sobel edge-density delta in the caption band vs the untouched frame:
      - text already burned -> re-burn is ~idempotent -> tiny relative delta
        -> PASS (measured: 4% on crf23 text)
      - text absent -> the burn injects full glyph edges -> huge delta
        -> FAIL (measured: 595%; the bright band itself contributes 0 delta)
    """
    if not ass or not os.path.isfile(ass):
        return {"passed": False, "deltas": [], "rel_deltas": [], "max_delta": 0.0,
                "max_rel_delta": 0.0, "threshold": max_rel_delta,
                "reason": "ass missing - differential not measurable"}
    if not any("Dialogue" in ln for ln in open(ass, errors="ignore")):
        return {"passed": False, "deltas": [], "rel_deltas": [], "max_delta": 0.0,
                "max_rel_delta": 0.0, "threshold": max_rel_delta,
                "reason": "ass has no Dialogue events - nothing was ever burned"}
    burn_vf = f"ass={ass}" + (f":fontsdir={fontsdir}" if fontsdir else "") + ","
    deltas, rels = [], []
    for t in list(cues)[:3]:
        nob = _band_edge_density(video, t, band)
        brn = _band_edge_density(video, t, band, burn_vf)
        d = abs(brn - nob)
        deltas.append(round(d, 3))
        rels.append(d / max(nob, 5.0))
    n_changed = sum(1 for r in rels if r >= max_rel_delta)
    return {"passed": bool(rels) and n_changed == 0,
            "deltas": deltas,
            "rel_deltas": [round(r, 4) for r in rels],
            "max_delta": max(deltas) if deltas else 0.0,
            "max_rel_delta": round(max(rels), 4) if rels else 0.0,
            "threshold": max_rel_delta}


def check(path, plan, reports, ass=None, fontsdir=None):
    p = ffprobe_json(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    dur = float(p["format"]["duration"])
    size = int(p["format"]["size"])
    results, repairs = [], []

    def ok(name, passed, detail=""):
        results.append({"check": name, "passed": bool(passed), "detail": detail})

    ok("file_exists", v is not None, f"{size/1e6:.1f}MB")
    ok("probe_ok", p is not None)
    tgt = plan.get("target_duration", 45)
    ok("duration_in_range", 0.5 * tgt <= dur <= 1.6 * tgt + 5, f"{dur:.2f}s vs target {tgt}s")
    ok("resolution_correct", v and f"{v['width']}x{v['height']}" == plan.get("resolution", "1080x1920"),
       f"{v['width']}x{v['height']}" if v else "?")
    ok("fps_correct", v and abs((v.get("avg_frame_rate") or "30/1").split("/")[0].__class__ and
       (lambda fr: eval(fr))(v["avg_frame_rate"]) - plan.get("fps", 30)) < 1.5,
       v["avg_frame_rate"] if v else "?")
    ok("audio_exists", a is not None)

    # loudness scan (integrated)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                          "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"\{[\s\S]*?\}", err)
    ln = json.loads(m.group(0)) if m else {}
    if ln:
        ii = float(ln.get("input_i", -70) or -70)
        ok("loudness_reasonable", -30 < ii < -6, f"input_i={ii}dB")
    else:
        ok("loudness_reasonable", False, "loudnorm scan failed")

    # G1: whole-file blackdetect gate (D1: regex fixed, full scan - no head-only truncation)
    bf = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf",
                         "blackdetect=d=0.4:pix_th=0.12:pic_th=0.90", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    blacks = parse_blackdetect(bf)
    total_black = sum(e - s for s, e in blacks)
    longest = max((e - s for s, e in blacks), default=0.0)
    tail_ok = True
    if blacks:
        ls, le = blacks[-1]
        if le >= dur - 0.25 and le - ls <= 0.5:
            longest_eff = max((e - s for s, e in blacks[:-1]), default=0.0)
            tail_ok = True
        else:
            longest_eff = longest
    else:
        longest_eff = 0.0
    g1 = (total_black <= 0.02 * dur + 0.05) and longest_eff <= 0.6 and tail_ok
    ok("black_budget_g1", g1,
       f"{len(blacks)} regions, total {total_black:.2f}s ({100 * total_black / max(dur, 0.1):.1f}%), "
       f"longest {longest:.2f}s (final fadeblack exempt <=0.5s)")

    # G2: luma profile (near-black ratio, median band, blown highlights)
    prof = luma_profile(path, fps=2)
    if prof:
        ys = [s["y"] for s in prof]
        ys_sorted = sorted(ys)
        med = ys_sorted[len(ys_sorted) // 2]
        nb = sum(1 for y in ys if y < 16) / len(ys)
        blown = 0
        for y in ys:
            blown = blown + 1 if y > 250 else 0
            if blown > 1:  # >2 consecutive samples at 2fps
                break
        first1 = [s["y"] for s in prof if s["t"] <= 1.0]
        first1_mean = sum(first1) / len(first1) if first1 else 0.0
        g2 = nb <= 0.05 and 45 <= med <= 140 and blown <= 1 and first1_mean >= 25
        ok("luma_profile_g2", g2,
           f"median={med:.0f} near-black={100 * nb:.1f}% blown={blown} first1sY={first1_mean:.0f}")
    else:
        ok("luma_profile_g2", False, "luma scan failed")

    # silent final
    if a:
        sl = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                             "silencedetect=noise=-45dB:d=2", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
        tail_silent = bool(re.search(rf"silence_start: {float(max(0, dur - 3)):.2f}", sl))
        ok("not_silent_tail", not tail_silent, "intentional fade excluded (2s threshold)")

    ok("size_reasonable", size / 1e6 < 220, f"{size/1e6:.1f}MB < 220MB")

    # G5: captions burn-existence (D6 pixel test, N1 differential upgrade:
    # bright in-band content can no longer false-pass the absolute ratio)
    if not plan.get("caption_style"):
        ok("captions_burned", True, "n/a (plan has no caption_style)")
    else:
        cr = jload(reports + "/captions_report.json", {}) if reports else {}
        cues = cr.get("cues")
        if cues:
            # sample where text is fully visible: never inside the deliberate
            # outro fadeblack (G1 already exempts that window from G1 scoring)
            fb = 0.4
            for s in (plan.get("segments") or [])[:-1]:
                t = (s.get("transition_after") or {}).get("type")
                if t == "fadeblack":
                    fb = max(fb, float((s.get("transition_after") or {}).get("dur") or 0.4))
            win = max(0.1, dur - fb - 0.25)
            cues = [min(max(c, 0.1), win) for c in cues][:3]
            cues = sorted(set(cues))
            diff = differential_caption_check(path, ass, cues, fontsdir=fontsdir)
            if ass and os.path.isfile(ass):
                ok("captions_burned", bool(diff["passed"]),
                   f"differential re-burn edge delta at cues: "
                   + ", ".join(f"{c}s={r:.3f}" for c, r in zip(cues, diff["deltas"]))
                   + f" (max rel {diff['max_rel_delta']:.3f} vs threshold "
                     f"{diff['threshold']}; small delta = text already burned)")
            else:
                ratios = [(c, caption_band_white_ratio(path, c)) for c in cues]
                if len(ratios) < 3:
                    # sparse-speech edit: pad the sample set with hook-card band
                    # samples so the burn-existence test stays 3-point measurable
                    for t in (0.8, 1.6):
                        t2 = min(t, dur - 0.1)
                        if all(abs(t2 - c) > 0.15 for c, _ in ratios):
                            ratios.append((t2, caption_band_white_ratio(path, t2, band=(0.16, 0.52))))
                hits = [(c, r) for c, r in ratios if r >= 0.003]
                ok("captions_burned", len(hits) >= 2,
                   f"absolute white-pixel ratio (differential n/a - no ass): "
                   + ", ".join(f"{c}s={r:.3%}" for c, r in ratios) +
                   f" ({len(hits)}/{len(ratios)} samples show burned text)")
        else:
            # no speech cues in this edit (sparse-dialogue source): the burned
            # typography that MUST exist is the hook card -> differential on
            # the hook band, falling back to the absolute ratio when no ass
            hook_t = [max(0.4, min(dur - 0.1, t)) for t in (0.8, 1.6)]
            band = (max(0.05, (plan.get("hook", {}).get("seconds") or [0, 2.5])[0] * 0 + 0.16), 0.52)
            if ass and os.path.isfile(ass):
                diff = differential_caption_check(path, ass, hook_t, fontsdir=fontsdir,
                                                  band=band)
                ok("captions_burned", bool(diff["passed"]),
                   "hook-card differential re-burn test (no speech cues): "
                   f"rel deltas {diff['rel_deltas']} (threshold {diff['threshold']})")
            else:
                ratios = [(c, caption_band_white_ratio(path, c, band=band)) for c in hook_t]
                hits = [(c, r) for c, r in ratios if r >= 0.003]
                ok("captions_burned", len(hits) >= 1,
                   "hook-card pixel test (no speech cues): " +
                   ", ".join(f"{c}s={r:.3%}" for c, r in ratios) +
                   f" ({len(hits)}/2 hook samples show burned text, band {band})")
    return results, repairs, {"duration": dur, "size": size, "loudnorm": ln}


def repair(path, results, out):
    """Minimal auto-repairs for common failures."""
    if any(r["check"] == "audio_exists" and not r["passed"] for r in results):
        return path, "no audio stream - cannot auto-repair without source"
    if any(r["check"] == "loudness_reasonable" and not r["passed"] for r in results):
        p2 = out.replace(".mp4", "_ln.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-af",
                        "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "copy", "-c:a", "aac",
                        "-movflags", "+faststart", p2], check=True)
        return p2, "loudness renormalized"
    if any(r["check"] == "size_reasonable" and not r["passed"] for r in results):
        p2 = out.replace(".mp4", "_sm.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast", "-c:a", "copy",
                        "-movflags", "+faststart", p2], check=True)
        return p2, "recompressed crf23"
    return path, "no repair needed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--plan", default="reports/edit_plan.json")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--ass", default=None,
                    help="captions.ass used by the differential burn test (N1)")
    ap.add_argument("--fontsdir", default=None, help="fonts dir for the re-burn")
    a = ap.parse_args()

    t0 = time.time()
    plan = jload(a.plan, {})
    results, repairs, extra = check(a.video, plan, a.reports, ass=a.ass,
                                    fontsdir=a.fontsdir)
    failed = [r for r in results if not r["passed"]]
    status, path = ("pass", a.video)
    if failed:
        path2, note = repair(a.video, results, a.video)
        if path2 != a.video:
            re_results, _, _ = check(path2, plan, a.reports)
            results = re_results
            repairs.append(note)
            path = path2
            failed = [r for r in results if not r["passed"]]
        status = "pass_after_repair" if not failed else "fail"
        if note and path2 == a.video:
            repairs.append(note)

    report = {"status": status, "final_path": path, "checks": results,
              "repairs": repairs, "probe": extra}
    jdump(report, f"{a.reports}/qc_report.json")
    record_stage(a.reports, "10-quality-control", status if status != "fail" else "fail", t0=t0)
    print(json.dumps({"status": status, "failed": [f["check"] for f in failed],
                      "repairs": repairs,
                      "details": {r["check"]: r["detail"] for r in results}}))
    sys.exit(0 if status != "fail" else 2)


if __name__ == "__main__":
    main()
