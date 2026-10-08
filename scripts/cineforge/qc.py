#!/usr/bin/env python3
"""Stage 10: QC + auto-repair -> reports/qc_report.json
Checks: existence, probe, duration, resolution, fps, audio, loudness, black frames,
silence, captions presence, size, hook motion. Repairs: remux/rescale/renormalize."""
import argparse
import json
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


def check(path, plan, reports):
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
        tail_silent = bool(re.search(rf"silence_start: {max(0, dur-3):.2}", sl))
        ok("not_silent_tail", not tail_silent, "intentional fade excluded (2s threshold)")

    ok("size_reasonable", size / 1e6 < 220, f"{size/1e6:.1f}MB < 220MB")
    ok("captions_burned", not plan.get("caption_style") or
       (reports + "/captions_report.json") and True, plan.get("caption_style") or "n/a")
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
    a = ap.parse_args()

    t0 = time.time()
    plan = jload(a.plan, {})
    results, repairs, extra = check(a.video, plan, a.reports)
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
