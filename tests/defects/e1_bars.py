#!/usr/bin/env python3
"""E1: scope-letterbox bars ride through cover_crop.

Audit: 20/23 delivered segment windows show edge-band Y=16-18 (Sintel mixes
2.35:1 scope shots with full-frame shots; make_proxy.sh cropdetect samples only
the first 90 frames -> one meta-level active_crop for the whole video, and
segments carry no per-shot active region).

Fix contract:
  - scripts/cineforge/bar_map.py builds a per-scene time->active-region map
    (cropdetect limit=24 reset-per-frame on the proxy, scene-segmented)
  - each timeline segment carries its own active_crop (source-res w/h/x/y)
  - render_segments.py pre-crops PER SEGMENT; bars vanish for scope AND
    full-frame shots

Probe: renders ONE scope-shot segment offline from a synthetic letterboxed
source. On HEAD the bars ride through (edge-band Y < 25) -> probe FAILS.
After fix, the bar-map-attached render is bar-free -> probe PASSES.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def synth_scope_source(path, dur=6.0, w=640, h=360):
    """Bright moving gradient with baked 2.35:1-style bars (25% top, 25% bottom)."""
    vf = ("gradients=s=%dx%d:d=%.1f:c0=0x204060:c1=0xF0D080,format=yuv420p,"
          "drawbox=x=0:y=0:w=iw:h=%d:color=black:t=fill,"
          "drawbox=x=0:y=ih-%d:w=iw:h=%d:color=black:t=fill" % (w, h, dur, h // 4, h // 4, h // 4))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
           "-f", "lavfi", "-i", "sine=frequency=330:duration=%.1f" % dur,
           "-map", "0:v", "-map", "1:a", "-t", str(dur), "-r", "30",
           "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
           "-c:a", "aac", path]
    subprocess.run(cmd, check=True)
    return path


def edge_band_y(video, band="top"):
    """Mean luma of the top/bottom 8% band of the first frame."""
    if band == "top":
        vf = "crop=iw:ih*0.08:0:0"
    else:
        vf = "crop=iw:ih*0.08:0:ih*0.92"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-ss", "1.0", "-i", video,
                        "-frames:v", "1", "-vf", vf + ",signalstats,metadata=print:"
                        "key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    import re
    m = re.search(r"YAVG=([\d.]+)", p.stdout or "")
    return float(m.group(1)) if m else 0.0


def main():
    with tempfile.TemporaryDirectory() as td:
        src = synth_scope_source(os.path.join(td, "scope_src.mp4"))
        segdir = os.path.join(td, "segs")
        os.makedirs(segdir, exist_ok=True)

        # The fix contract: bar map module exists and can be built for this source.
        try:
            bm = load_module("bar_map_under_test", "scripts/cineforge/bar_map.py")
        except Exception as e:
            fail(f"E1 contract missing: scripts/cineforge/bar_map.py absent "
                 f"({type(e).__name__}: {e}) - per-scene bar map not implemented")

        # 1) build the per-scene bar map from a proxy of the synthetic source
        proxy = os.path.join(td, "proxy.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                        "-vf", "scale=480:270:force_original_aspect_ratio=decrease,setsar=1",
                        "-c:v", "libx264", "-preset", "ultrafast", "-an", proxy], check=True)
        map_path = os.path.join(td, "bar_map.json")
        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "cineforge",
                                                          "bar_map.py"),
                            "--proxy", proxy, "--out", map_path,
                            "--src-w", "640", "--src-h", "360"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            fail(f"bar_map.py failed: {(r.stderr or r.stdout)[-400:]}")
        barmap = json.load(open(map_path))
        scope_scenes = [s for s in barmap.get("scenes", [])
                        if s.get("crop") and s["crop"]["h"] < 0.85 * 360]
        if not scope_scenes:
            fail("bar map found no scope-bar scenes in a fully-letterboxed source "
                 f"(scenes={barmap.get('scenes')})")
        ok(f"bar map: {len(barmap.get('scenes', []))} scenes, "
           f"{len(scope_scenes)} scope-cropped (h<306 of 360)")

        # 2) timeline with ONE segment inside a scope window, carrying its own
        #    active_crop (the E1 fix contract)
        crop = scope_scenes[0]["crop"]
        timeline = {"meta": {"src_w": 640, "src_h": 360, "src_fps": 30.0,
                             "src_dur": 6.0, "out_w": 540, "out_h": 960,
                             "out_fps": 30, "vertical": "cover_crop",
                             "has_audio": True, "active_crop": None},
                    "segments": [{"i": 0, "src_start": scope_scenes[0]["t0"] + 0.2,
                                  "src_dur": 2.0, "out_dur": 2.0, "speed": 1.0,
                                  "zoom": 1.0, "active_crop": crop,
                                  "transition_after": {"type": "none", "dur": 0.0}}]}
        tl_path = os.path.join(td, "timeline.json")
        json.dump(timeline, open(tl_path, "w"))

        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "montage",
                                                          "render_segments.py"),
                            "--source", src, "--timeline", tl_path,
                            "--outdir", segdir, "--jobs", "1", "--crf", "23",
                            "--preset", "ultrafast"], capture_output=True, text=True)
        if r.returncode != 0:
            fail(f"render_segments.py failed with per-segment active_crop: "
                 f"{(r.stderr or r.stdout)[-500:]}")
        seg = os.path.join(segdir, "seg_000.mp4")
        if not os.path.isfile(seg):
            fail("rendered segment missing")

        top = edge_band_y(seg, "top")
        bot = edge_band_y(seg, "bottom")
        if top < 25 or bot < 25:
            fail(f"E1 present: bars ride through cover_crop even with per-segment "
                 f"active_crop {crop} (edge-band Y top={top:.0f} bottom={bot:.0f}, need >=25)")
        ok(f"per-segment active_crop kills the bars: edge-band Y top={top:.0f} "
           f"bottom={bot:.0f} (>=25)")

        # 3) full-frame shots must stay intact: a segment outside scope windows
        full_scenes = [s for s in barmap.get("scenes", []) if not s.get("crop")]
        synth_ff = synth_scope_source(os.path.join(td, "ff_src.mp4"))  # same synth = all scope
        # build a truly full-frame source (no bars) and confirm map marks it full
        ff = os.path.join(td, "really_full.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "gradients=s=640x360:d=4:c0=0x204060:c1=0xF0D080",
                        "-f", "lavfi", "-i", "sine=frequency=330:duration=4",
                        "-map", "0:v", "-map", "1:a", "-t", "4", "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", ff],
                       check=True)
        proxy2 = os.path.join(td, "proxy2.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", ff,
                        "-vf", "scale=480:270:force_original_aspect_ratio=decrease,setsar=1",
                        "-c:v", "libx264", "-preset", "ultrafast", "-an", proxy2], check=True)
        map2 = os.path.join(td, "bar_map2.json")
        r2 = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "cineforge",
                                                          "bar_map.py"),
                             "--proxy", proxy2, "--out", map2,
                             "--src-w", "640", "--src-h", "360"],
                            capture_output=True, text=True)
        if r2.returncode != 0:
            fail(f"bar_map.py failed on full-frame source: {(r2.stderr or r2.stdout)[-300:]}")
        barmap2 = json.load(open(map2))
        cropped2 = [s for s in barmap2.get("scenes", []) if s.get("crop")]
        if cropped2:
            fail(f"bar map false-positives on a full-frame source: {cropped2[:2]}")
        ok("full-frame source maps to no crop (no false bars introduced)")

    print("E1 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
