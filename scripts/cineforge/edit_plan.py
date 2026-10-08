#!/usr/bin/env python3
"""Stage 6: edit decision engine -> reports/edit_plan.json (+ out/timeline.json for engine)
Style-aware: hook selection, beat/scene aligned cuts, pacing per mood, ducking plan."""
import argparse
import json

REPO_ROOT = __import__("os").path.abspath(
    __import__("os").path.join(__file__, "..", ".."))
from utils import jdump, jload, record_stage
import time


def pick_hook(transcript, beats, style):
    """Return hook text or None. Strongest sentence = highest energy window overlap."""
    if not transcript or transcript.get("transcript_empty"):
        return None
    segs = transcript.get("segments", [])
    if not segs:
        return None
    peaks = beats.get("energy_peak_starts", [])
    def score(s):
        dur = max(s["end"] - s["start"], 0.3)
        base = min(len(s["text"]) / 60.0, 1.0)          # substantial but short
        energy = sum(1 for p in peaks if p <= s["end"] and p >= s["start"] - 1.0)
        excl = 2.0 if any(w in s["text"].lower() for w in ("never", "secret", "why", "how", "best", "insane")) else 0
        return base + energy * 0.5 + excl + (0.5 if dur < 4 else 0)
    best = max(segs, key=score)
    return best["text"].strip()[:90]


def build_timeline(source_meta, beats, style_cfg, style, target_len):
    """Reuse proven montage timeline logic; emit engine-compatible timeline.json."""
    dur = source_meta["duration"]
    beats_list = beats.get("beats") or []
    if not beats_list:
        beat_period = 1.35
        beats_list = [i * beat_period for i in range(int(dur / beat_period) + 1)]
    tempo = beats.get("tempo") or (60.0 / 1.35)
    beat_period = 60.0 / max(tempo, 40.0)
    pacing = style_cfg.get("pacing", "energetic")
    mult = {"slow": 2.6, "smooth": 1.8, "speech": 2.2, "fast": 1.0, "energetic": 1.4}.get(pacing, 1.4)
    base_out = min(max(beat_period * mult, 0.55), 4.2)

    usable = [b for b in sorted(set(round(b, 3) for b in beats_list)) if 1.5 <= b <= dur - 2.0]
    if not usable:
        usable = [0.5 + i * base_out for i in range(int((dur - 2) / base_out))]
    n_target = max(6, int(round(target_len / base_out)))

    segs = []
    cursor = usable[0]
    for k in range(n_target):
        if k == 0:
            out_dur = base_out * 1.9
        elif k == n_target - 1:
            out_dur = base_out * 2.1
        else:
            wiggle = [1.0, 0.85, 0.75, 1.1, 0.9, 0.8][k % 6]
            out_dur = base_out * wiggle
        out_dur = round(min(max(out_dur, 0.55), 5.0), 3)
        cands = [b for b in usable if b >= cursor] or usable
        start = cands[0]
        cursor = start + out_dur + base_out * 0.3
        if cursor > dur - 1.6:
            cursor = usable[0] + 0.37
        zoom = ([1.0, 1.08, 1.0, 1.13, 1.0, 1.06][k % 6]
                if style_cfg.get("cut_style") == "beat_grid" else 1.0)
        segs.append({"i": k, "src_start": round(start, 3), "out_dur": out_dur,
                     "speed": 1.0, "zoom": zoom})

    # hero slow-mo at strongest energy peak (energetic styles only)
    peaks = beats.get("energy_peak_starts", [])
    if peaks and pacing in ("energetic", "fast") and len(segs) > 4:
        idx = min(range(len(segs)), key=lambda j: abs(segs[j]["src_start"] - peaks[0]))
        segs[idx]["speed"] = 0.5
        segs[idx]["zoom"] = max(segs[idx]["zoom"], 1.12)
        if len(peaks) > 1:
            j = min(range(len(segs)), key=lambda q: abs(segs[q]["src_start"] - peaks[1]))
            if segs[j]["speed"] == 1.0:
                segs[j]["speed"] = 1.25

    for s in segs:
        s["src_dur"] = round(min(s["out_dur"] / s["speed"], max(0.4, dur - 0.25 - s["src_start"])), 3)
        s["out_dur"] = round(s["src_dur"] * s["speed"], 3)

    soft = style_cfg.get("transitions") == "soft_fades"
    per_section = max(6, len(segs) // 3)
    for k in range(len(segs) - 1):
        if soft:
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.5}
        elif k == 0:
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.18}
        elif (k + 1) == len(segs) - 1:
            segs[k]["transition_after"] = {"type": "fadeblack", "dur": 0.3}
        elif (k + 1) % per_section == 0:
            segs[k]["transition_after"] = {"type": style_cfg.get("section_flash", "fadewhite"), "dur": 0.14}
        else:
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.05}
    segs[-1]["transition_after"] = {"type": "none", "dur": 0.0}
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--out", default="out")
    ap.add_argument("--style", default="beat_montage")
    ap.add_argument("--target-len", type=float, default=None)
    ap.add_argument("--title", default="MONTAGE")
    a = ap.parse_args()

    t0 = time.time()
    styles = jload(REPO_ROOT + "/configs/styles.json", {})
    style_cfg = styles.get(a.style, styles["beat_montage"])
    meta = jload(f"{a.reports}/source_metadata.json")
    beats = jload(f"{a.reports}/beats.json", {})
    transcript = jload(f"{a.reports}/transcript.json", {})
    audio = jload(f"{a.reports}/audio_analysis.json", {})

    dur = meta["duration"]
    lo, hi = style_cfg.get("target_range", [25, 60])
    target = a.target_len or max(lo, min(hi, dur * 0.55))
    target = min(target, max(10, dur - 2))

    segments = build_timeline(meta, beats, style_cfg, a.style, target)
    total = sum(s["out_dur"] for s in segments) - sum(
        s["transition_after"]["dur"] for s in segments[:-1])

    hook_text = pick_hook(transcript, beats, style_cfg)
    plan = {
        "style": a.style,
        "target_duration": round(total, 2),
        "aspect_ratio": "9:16",
        "fps": 30,
        "resolution": "1080x1920",
        "hook": {
            "type": style_cfg.get("hook", "title_card"),
            "text": hook_text,
            "seconds": [0, min(3.0, total / 4)],
        },
        "segments": segments,
        "cut_points": [s["src_start"] for s in segments],
        "transition_types": list({s["transition_after"]["type"] for s in segments[:-1]}),
        "music_cut_alignment": "beat_grid" if beats.get("beats") else "uniform_grid",
        "caption_style": style_cfg.get("captions"),
        "color_grade": style_cfg.get("grade", "natural"),
        "b_roll_suggestions": [],
        "sfx_suggestions": ["whoosh_on_section_flash", "impact_on_hook"] if style_cfg.get("pacing") in ("energetic", "fast") else [],
        "audio_ducking_plan": {
            "mode": "keep_source" if style_cfg.get("music") == "keep_source" else "sidechain_duck",
            "music": "media/music.mp3" if style_cfg.get("music") in ("duck_or_mix", "under_bed") else None,
            "duck_to_db": -14,
        },
        "fallback_plan": jload(REPO_ROOT + "/configs/fallbacks.json", {}).get("rules", []),
        "vertical_plan": style_cfg.get("vertical", "blurred_bg_fill"),
        "letterbox": style_cfg.get("letterbox", False),
        "title_main": (a.title or "MONTAGE").upper()[:38],
        "title_sub": "AI VIDEO LAB",
        "dead_air_removed": audio.get("silence_ratio", 0) > 0.15,
        "source_duration": round(dur, 2),
    }
    jdump(plan, f"{a.reports}/edit_plan.json")
    # engine-compatible timeline (proven montage code path)
    jdump({"meta": {"src_w": meta["width"], "src_h": meta["height"],
                    "src_fps": meta["fps"], "src_dur": dur,
                    "out_w": 1080, "out_h": 1920, "out_fps": 30,
                    "target_dur": round(total, 2), "tempo": beats.get("tempo", 0),
                    "title_main": plan["title_main"], "title_sub": plan["title_sub"],
                    "preview": False, "n_segments": len(segments)},
           "segments": segments}, f"{a.out}/timeline.json")
    record_stage(a.reports, "06-edit-decision", "success", t0=t0)
    print(f"plan: {len(segments)} segs, {total:.1f}s, hook={bool(hook_text)}, grade={plan['color_grade']}")


if __name__ == "__main__":
    main()
