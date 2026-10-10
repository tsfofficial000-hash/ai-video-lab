#!/usr/bin/env python3
"""Creative-review evidence: 4x4 contact sheet of a rendered edit + measured
band/luma scan rows (v2.1 Phase D). Used by the agent's visual self-review:
every grid cell is timestamped so complaints can cite exact times.

Usage: contact_sheet.py --video out/final.mp4 --out media/contact_final.jpg
       [--cols 4] [--rows 4] [--json reports/contact_scan.json]
"""
import argparse
import json
import re
import subprocess


def ffprobe_dur(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(p.stdout.strip().splitlines()[0])
    except Exception:
        return 0.0


def scan(video, dur, n=16):
    """2fps YAVG + edge-band YAVG summary rows at the contact-sheet times."""
    rows = []
    for i in range(n):
        t = min(dur - 0.05, dur * (i + 0.5) / n)
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
             "-vf", "scale=270:480,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-,"
                    "crop=iw:ih*0.08:0:0,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-,"
                    "crop=iw:ih*0.08:0:ih*0.92,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
             "-f", "null", "-"], capture_output=True, text=True)
        ys = [float(m) for m in re.findall(r"YAVG=([\d.]+)", p.stdout or "")]
        rows.append({"t": round(t, 2),
                     "y": round(ys[0], 1) if len(ys) > 0 else None,
                     "band_top": round(ys[1], 1) if len(ys) > 1 else None,
                     "band_bottom": round(ys[2], 1) if len(ys) > 2 else None})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    dur = ffprobe_dur(a.video)
    fps = 1.0 / (dur / (a.cols * a.rows))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video,
                    "-vf", f"fps={fps:.4f},scale=270:480,tile={a.cols}x{a.rows}",
                    "-frames:v", "1", "-q:v", "3", a.out], check=True)
    print(f"contact sheet -> {a.out} ({a.cols}x{a.rows} grid, {dur:.1f}s source)")
    if a.json:
        rows = scan(a.video, dur, a.cols * a.rows)
        json.dump({"video": a.video, "duration": round(dur, 2), "scan": rows},
                  open(a.json, "w"), indent=1)
        dark = [r for r in rows if (r["y"] or 255) < 16]
        bars = [r for r in rows if min(r["band_top"] or 255, r["band_bottom"] or 255) < 25]
        print(f"scan: {len(rows)} samples, {len(dark)} dark(Y<16), "
              f"{len(bars)} barred-edge samples -> {a.json}")
        for r in rows:
            print(f"  t={r['t']:>5} Y={r['y']} top={r['band_top']} bot={r['band_bottom']}")


if __name__ == "__main__":
    main()
