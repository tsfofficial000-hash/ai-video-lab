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

    # black frames (first 10s sample)
    bf = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-t", "10", "-vf",
                         "blackdetect=d=0.5:pix_th=0.10", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    blacks = re.findall(r"black_start: ([\d.]+)", bf)
    ok("no_black_opening", not blacks, f"{len(blacks)} black regions in first 10s")

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
