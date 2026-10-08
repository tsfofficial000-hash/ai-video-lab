#!/usr/bin/env python3
"""Beat-synced montage timeline builder.

Reads a source video, analyzes audio (librosa beats + onsets) and scene changes
(PySceneDetect), then emits a JSON timeline that render_segments.py / assemble.py
execute with pure FFmpeg. No GUI, no cloud services.

Output timeline.json:
{
  "meta": {src_w, src_h, src_fps, src_dur, out_w, out_h, out_fps, target_dur,
           title_main, title_sub, tempo},
  "segments": [{
     "i", "src_start", "src_dur", "out_dur", "speed", "zoom",
     "transition_after": {"type": "fade|fadeblack|fadewhite|none", "dur": float}
  }]
}
"""
import argparse
import json
import math
import os
import subprocess
import sys

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30


def ffprobe(path):
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    d = json.loads(subprocess.check_output(cmd).decode())
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    dur = float(d["format"]["duration"])
    fps_num, fps_den = v.get("r_frame_rate", "30/1").split("/")
    fps = float(fps_num) / float(fps_den or 1)
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": fps, "dur": dur,
            "has_audio": a is not None}


def extract_wav(src, wav, sr=22050):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
                    "-ar", str(sr), "-f", "wav", wav], check=True)


def audio_features(wav):
    import numpy as np
    import librosa
    y, sr = librosa.load(wav, sr=22050, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=False)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)
    return float(tempo), [float(b) for b in beats], [float(o) for o in onsets], rms, times


def scene_starts(src):
    try:
        from scenedetect import detect, ContentDetector
        cuts = []
        for (s, e) in detect(src, ContentDetector(threshold=27.0)):
            cuts.append(s.get_seconds())
        return cuts
    except Exception as e:
        print(f"[timeline] scene detection unavailable ({type(e).__name__}), beats-only mode", flush=True)
        return []


def snap(t, grid, tol):
    if not grid:
        return t
    best = min(grid, key=lambda b: abs(b - t))
    return best if abs(best - t) <= tol else t


def energy_at(t, rms, times, win=1.0):
    import numpy as np
    m = (times >= t) & (times < t + win)
    return float(np.mean(rms[m])) if m.any() else 0.0


def build(src, out_json, title_main, title_sub, preview=False, target_len=None):
    info = ffprobe(src)
    dur, w, h = info["dur"], info["w"], info["h"]
    print(f"[timeline] source {w}x{h} @ {info['fps']:.2f}fps, {dur:.1f}s", flush=True)

    wav = "/tmp/_montage_analysis.wav"
    extract_wav(src, wav)
    tempo, beats, onsets, rms, times = audio_features(wav)
    print(f"[timeline] tempo={tempo:.1f}bpm beats={len(beats)} onsets={len(onsets)}", flush=True)
    cuts = scene_starts(src)
    print(f"[timeline] scene cuts={len(cuts)}", flush=True)

    # ---- target montage length & segment grid -------------------------------
    if target_len is None:
        target_len = max(24.0, min(72.0, 0.55 * dur))
    if preview:
        target_len = min(target_len, 16.0)
    if not beats:
        beat_period = 1.35
        beats = [i * beat_period for i in range(int(dur / beat_period) + 1)]
        tempo = 60.0 / beat_period
    beat_period = 60.0 / max(tempo, 40.0)
    cuts_per_beat = 2 if tempo < 132 else 1
    base_out = min(max(beat_period * cuts_per_beat, 0.55), 2.2)
    if preview:
        base_out = max(base_out, 1.0)

    grid = sorted({round(b, 3) for b in beats})
    n_target = max(8, int(round(target_len / base_out)))
    if preview:
        n_target = min(n_target, 12)

    # ---- pick segment windows ------------------------------------------------
    # walk the beat grid; prefer starts that coincide with scene changes (aligned
    # cuts look intentional); skip first 2s (often channel intro) and last 1.5s.
    usable = [b for b in grid if 1.8 <= b <= dur - 2.0]
    if len(usable) < n_target:
        usable = [b for b in grid if 0.5 <= b <= dur - 1.0]
    scene_set = cuts

    def pick_start(cursor):
        cands = [b for b in usable if b >= cursor]
        if not cands:
            cands = usable
        window = cands[:4]
        best = min(window, key=lambda b: min((abs(b - c) for c in scene_set), default=9.9))
        return best

    # energy profile to place hero slow-mo & fast push
    e_values = [energy_at(b, rms, times, 1.5) for b in usable]
    ranked = sorted(range(len(usable)), key=lambda k: e_values[k], reverse=True)

    segments = []
    cursor = usable[0] if usable else 1.8

    for k in range(n_target):
        # rhythm: faster cuts mid-montage, longer at intro/outro
        if k == 0:
            out_dur = base_out * 1.9          # intro
        elif k == n_target - 1:
            out_dur = base_out * 2.1          # outro
        elif k < 2:
            out_dur = base_out * 1.35
        else:
            wiggle = [1.0, 0.85, 0.75, 1.1, 0.9, 0.8][k % 6]
            out_dur = base_out * wiggle
        if preview:
            out_dur = max(out_dur, 1.0)
        out_dur = round(min(max(out_dur, 0.55), 4.2), 3)

        start = pick_start(cursor)
        cursor = start + out_dur + base_out * 0.3
        if cursor > dur - 1.6:                # wrap with slight offset (reuse w/ variation)
            cursor = usable[0] + 0.37 if usable[0] + 0.37 < dur - 2 else usable[0]

        speed = 1.0
        zoom = [1.0, 1.08, 1.0, 1.13, 1.0, 1.06][k % 6]
        if k == 0:
            zoom = 1.0
        if k == n_target - 1:
            zoom = 1.05

        segments.append({"i": k, "src_start": round(start, 3), "out_dur": out_dur,
                         "speed": speed, "zoom": zoom})

    # hero moments: slow-mo on the highest-energy window, 1.25x push on 2nd
    if len(ranked) >= 3 and not preview:
        hero = ranked[0]
        idx = min(range(len(segments)), key=lambda j: abs(segments[j]["src_start"] - usable[hero]))
        segments[idx]["speed"] = 0.5
        segments[idx]["zoom"] = 1.15
        fast = ranked[1]
        idx2 = min(range(len(segments)), key=lambda j: abs(segments[j]["src_start"] - usable[fast]))
        if segments[idx2]["speed"] == 1.0 and idx2 != idx:
            segments[idx2]["speed"] = 1.25

    # recompute src_dur from speed and clamp
    for s in segments:
        s["src_dur"] = round(min(s["out_dur"] / s["speed"], max(0.4, dur - 0.25 - s["src_start"])), 3)
        s["out_dur"] = round(s["src_dur"] * s["speed"], 3)

    # ---- transitions ----------------------------------------------------------
    PSEUDO_CUT, SMOOTH, FLASH, SECTION = 0.05, 0.18, 0.14, 0.30
    per_section = max(6, n_target // 3)
    for k in range(n_target - 1):
        if k == 0:
            tr = ("fade", SMOOTH)
        elif (k + 1) == n_target - 1:
            tr = ("fadeblack", SMOOTH)
        elif (k + 1) % per_section == 0:
            tr = ("fadewhite", FLASH)
        elif k % 4 == 3:
            tr = ("fade", SMOOTH)
        else:
            tr = ("fade", PSEUDO_CUT)
        segments[k]["transition_after"] = {"type": tr[0], "dur": tr[1]}
    segments[-1]["transition_after"] = {"type": "none", "dur": 0.0}

    total = sum(s["out_dur"] for s in segments) - sum(
        s["transition_after"]["dur"] for s in segments[:-1])
    meta = {"src_w": w, "src_h": h, "src_fps": info["fps"], "src_dur": round(dur, 3),
            "out_w": OUT_W // (2 if preview else 1), "out_h": OUT_H // (2 if preview else 1),
            "out_fps": OUT_FPS, "target_dur": round(total, 2), "tempo": round(tempo, 1),
            "title_main": title_main, "title_sub": title_sub, "preview": preview,
            "n_segments": len(segments)}
    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
    json.dump({"meta": meta, "segments": segments}, open(out_json, "w"), indent=1)
    print(f"[timeline] wrote {out_json}: {len(segments)} segments, master ~{total:.1f}s", flush=True)


def derive_title(raw):
    t = (raw or "MONTAGE").split(" - ")[0].split(" | ")[0].split(" // ")[0]
    t = t.replace("4K", "").replace("4k", "").strip(" -|_")
    t = " ".join(t.split())[:38] or "MONTAGE"
    return t.upper()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="MONTAGE")
    ap.add_argument("--sub", default="AI VIDEO LAB")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--target-len", type=float, default=None)
    a = ap.parse_args()
    build(a.source, a.out, derive_title(a.title), a.sub, preview=a.preview, target_len=a.target_len)
