#!/usr/bin/env python3
"""Per-scene baked-letterbox map (defect E1).

make_proxy.sh used to run cropdetect over the first 90 frames only and attach
ONE meta-level active_crop to the whole source - so scope shots kept their
bars (Sintel mixes 2.35:1 with full-frame) or full-frame shots were wrongly
cropped. This module builds a TIME->ACTIVE-REGION map instead:

  ffmpeg cropdetect limit=24 round=2 reset=1 on the PROXY (per-frame reset)
    -> per-frame crop suggestions with pts_time
  PySceneDetect (proxy-res) scene segmentation (ffmpeg scene-score fallback)
    -> modal crop per scene
  scenes whose modal crop is (near-)full-frame map to crop=None
  crops scaled to SOURCE resolution (even-rounded) with x/y offsets

Output reports/bar_map.json:
{
  "proxy_w": 480, "proxy_h": 270, "src_w": 1920, "src_h": 1080,
  "scene_cuts": [t...],
  "scenes": [{"t0": 0.0, "t1": 3.5, "n": 84, "crop": {"w","h","x","y"} | null}],
  "meta_crop": {...} | null          # global modal crop (back-compat)
}

Helpers:
  crop_for_time(t, bar_map) -> crop dict | None
  attach_segments(segments, bar_map) -> attaches seg["active_crop"] per segment
  (midpoint of the segment's source span decides the region - a segment that
  starts exactly on a cut inherits the scene it mostly shows)
"""
import argparse
import json
import os
import re
import subprocess
from collections import Counter


def even(x):
    x = int(round(x))
    return x - (x % 2)


def ffprobe_dims(path):
    d = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", path]).decode())
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return int(v["width"]), int(v["height"])


def frame_crops(proxy, limit=24):
    """[(t, (w,h,x,y))] per-frame cropdetect suggestions on the proxy."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", proxy, "-vf",
                        f"cropdetect=limit={limit}:round=2:reset=1",
                        "-f", "null", "-"], capture_output=True, text=True)
    out = []
    for ln in (p.stderr or "").splitlines():
        if "crop=" not in ln:
            continue
        mt = re.search(r"\bt:([\d.]+)", ln)
        mc = re.search(r"crop=(\d+):(\d+):(\d+):(\d+)", ln)
        if mt and mc:
            t = float(mt.group(1))
            out.append((t, tuple(int(x) for x in mc.groups())))
    return out


def scene_cuts_scenedetect(proxy, threshold=27.0):
    try:
        from scenedetect import detect, ContentDetector
        return [s.get_seconds() for (s, e) in detect(proxy, ContentDetector(threshold=threshold))]
    except Exception as e:
        print(f"[bar_map] scenedetect unavailable ({type(e).__name__}) - ffmpeg scene fallback",
              flush=True)
        return scene_cuts_ffmpeg(proxy)


def scene_cuts_ffmpeg(proxy, thr=0.27):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", proxy, "-vf",
                        f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True)
    cuts = []
    for ln in (p.stderr or "").splitlines():
        m = re.search(r"pts_time:([\d.]+)", ln)
        if m and "showinfo" not in ln[:30]:
            cuts.append(float(m.group(1)))
    return sorted(set(round(c, 2) for c in cuts))


def build(proxy, out_path, src_w=None, src_h=None, meta=None, max_scan=900.0):
    pw, ph = ffprobe_dims(proxy)
    crops = frame_crops(proxy)
    if not crops:
        raise RuntimeError("cropdetect produced no frames - proxy broken?")
    dur = crops[-1][0] + 0.05
    cuts = [c for c in scene_cuts_scenedetect(proxy) if 0.2 < c < min(dur, max_scan)]
    bounds = [0.0] + cuts + [dur + 1.0]
    scenes = []
    for i in range(len(bounds) - 1):
        t0, t1 = bounds[i], bounds[i + 1]
        window = [(t, c) for t, c in crops if t0 <= t < t1]
        if not window:
            continue
        modal = Counter(c for _, c in window).most_common(1)[0][0]
        w, h, x, y = modal
        full = w >= 0.97 * pw and h >= 0.97 * ph
        crop = None if full else {"w": w, "h": h, "x": x, "y": y}
        scenes.append({"t0": round(t0, 2), "t1": round(t1, 2),
                       "n": len(window), "crop": crop})
    # scale proxy coords -> source coords
    if src_w is None or src_h is None:
        src_w, src_h = pw, ph
    if meta and os.path.isfile(meta):
        try:
            m = json.load(open(meta))
            src_w = m.get("width") or src_w
            src_h = m.get("height") or src_h
        except Exception:
            pass
    sx, sy = src_w / float(pw), src_h / float(ph)
    for s in scenes:
        if s["crop"]:
            c = s["crop"]
            s["crop"] = {"w": even(c["w"] * sx), "h": even(c["h"] * sy),
                         "x": even(c["x"] * sx), "y": even(c["y"] * sy)}
    modal_all = Counter(c for _, c in crops).most_common(1)[0][0]
    gw, gh, gx, gy = modal_all
    meta_crop = None if (gw >= 0.97 * pw and gh >= 0.97 * ph) else \
        {"w": even(gw * sx), "h": even(gh * sy), "x": even(gx * sx), "y": even(gy * sy)}
    result = {"proxy_w": pw, "proxy_h": ph, "src_w": src_w, "src_h": src_h,
              "scene_cuts": [round(c, 2) for c in cuts],
              "scenes": scenes, "meta_crop": meta_crop}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    json.dump(result, open(out_path, "w"), indent=1)
    n_cropped = sum(1 for s in scenes if s["crop"])
    print(f"[bar_map] {len(scenes)} scenes, {n_cropped} scope-cropped, "
          f"meta_crop={meta_crop} -> {out_path}", flush=True)
    return result


def crop_for_time(t, bar_map):
    """Active-region crop (source coords) at source time t, or None if full-frame."""
    for s in bar_map.get("scenes", []):
        if s["t0"] <= t < s["t1"]:
            return s.get("crop")
    return bar_map.get("meta_crop")


def meaningful(crop, src_w, src_h):
    """A crop worth pre-applying (not the full frame)."""
    if not crop:
        return False
    return crop["w"] <= 0.97 * src_w or crop["h"] <= 0.97 * src_h


def attach_segments(segments, bar_map):
    """E1 fix: every segment carries its own active_crop (source-res w/h/x/y)."""
    src_w = bar_map.get("src_w", 0)
    src_h = bar_map.get("src_h", 0)
    attached = 0
    for seg in segments:
        mid = float(seg["src_start"]) + 0.5 * float(seg.get("src_dur") or 0.0)
        crop = crop_for_time(mid, bar_map)
        if meaningful(crop, src_w, src_h):
            seg["active_crop"] = crop
            attached += 1
        else:
            seg.pop("active_crop", None)   # full-frame scene: no pre-crop
    return attached


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--src-w", type=int, default=None)
    ap.add_argument("--src-h", type=int, default=None)
    ap.add_argument("--meta", default=None,
                    help="source_metadata.json to source real dims from")
    a = ap.parse_args()
    build(a.proxy, a.out, src_w=a.src_w, src_h=a.src_h, meta=a.meta)
