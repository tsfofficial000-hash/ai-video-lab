#!/usr/bin/env python3
"""Stage 6: edit decision engine -> reports/edit_plan.json (+ out/timeline.json for engine)
Style-aware: hook selection, beat/scene aligned cuts, pacing per mood, ducking plan."""
import argparse
import json
import os

REPO_ROOT = __import__("os").path.abspath(
    __import__("os").path.join(__file__, "..", "..", ".."))
from utils import jdump, jload, record_stage
from selection import Selector, luma_profile_ffmpeg
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


def build_timeline(source_meta, beats, style_cfg, style, target_len, luma=None,
                    luma_cache=None):
    """Reuse proven montage timeline logic; emit engine-compatible timeline.json.
    D3: selection is forward-only, luma-gated, overlap-free (see selection.Selector).
    `luma` = optional [{t,y}] profile; when absent it is computed from the source
    (cached at luma_cache / reports/luma.json) so the gate always has real data."""
    dur = source_meta["duration"]
    src_path = source_meta.get("path")
    if luma is None:
        cache = luma_cache or "reports/luma.json"
        luma = luma_profile_ffmpeg(src_path, fps=2, cache=cache) if src_path else []
    print(f"[plan] luma profile: {len(luma)} samples from {src_path!r} "
          f"(gate {'ACTIVE' if luma else 'INACTIVE - no gating this run'})", flush=True)
    beats_list = beats.get("beats") or []
    if len(beats_list) < 8:   # beatless/near-beatless source -> uniform grid fallback
        beat_period = 1.35
        beats_list = [i * beat_period for i in range(int(dur / beat_period) + 1)]
    tempo = beats.get("tempo") or (60.0 / 1.35)
    beat_period = 60.0 / max(tempo, 40.0)
    pacing = style_cfg.get("pacing", "energetic")

    # G7: cut density driven by the style band (cuts/second, spec 2.4)
    band = style_cfg.get("cuts_band") or [1.2, 2.0]
    cps_target = (band[0] + band[1]) / 2.0
    base_out = 1.0 / cps_target
    if style_cfg.get("cut_style") == "beat_grid" and len(beats_list) >= 8:
        # snap to a quarter-beat-compatible multiplier to keep beat alignment
        mults = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0]
        k = min(mults, key=lambda m: abs(m * beat_period - base_out))
        base_out = k * beat_period
    base_out = round(min(max(base_out, 0.55), 6.0), 3)
    achieved_cps = 1.0 / base_out
    if not (band[0] - 0.05 <= achieved_cps <= band[1] + 0.05):
        # clamp into band: pick base_out at band edge
        base_out = round(min(max(base_out, 1.0 / band[1]), 1.0 / band[0]), 3)
        achieved_cps = 1.0 / base_out

    n_target = max(6, int(round(target_len / base_out)))

    sel = Selector(beats_list, dur, luma=luma, min_y=36.0)

    # ---- scarcity-aware sizing (G3 no-reuse vs G7 band vs target_len) ----
    # When clean candidates cannot fill the target at the style's density,
    # hold cps inside the band by solving out_dur from the capacity equation
    # and retiming segments by the resulting small factor. Never wrap, never
    # duplicate beyond the <=0.3s crossfade-hidden overlap (G3).
    n_cap = len(sel.candidates)
    scarcity = bool(sel.candidates) and n_cap * base_out < target_len * 0.95 \
        and n_target > n_cap
    if scarcity:
        # Scarcity solver: n candidates is the hard capacity (G3 no-reuse), so
        # every candidate hosts one segment. Sizing contract:
        #   cps = n / (n*out - (n-1)*fade) >= band[0]*1.05  (margin for rounding)
        #   src_span = typical candidate spacing + 0.28s deliberate overlap,
        #   hidden inside the 0.18s crossfades (pick() enforces <=0.3s real)
        # out_dur is solved from the cps constraint; speed lands within +/-7%
        # of 1.0 (imperceptible retiming).
        n_target = min(n_target, n_cap)
        print(f"[plan] scarcity solver: {n_cap} candidates cannot fill "
              f"{target_len:.0f}s at {1.0/base_out:.2f}cps -> full-capacity walk "
              f"with solved out_dur", flush=True)

    segs = []
    cursor = sel.candidates[0] if sel.candidates else 1.5
    peaks = [p for p in (beats.get("energy_peak_starts") or [])
             if any(c - 1.0 <= p <= c + 1.0 for c in sel.candidates)]
    hero_t = peaks[0] if (peaks and pacing in ("energetic", "fast")) else None
    hero2_t = peaks[1] if len(peaks) > 1 and pacing in ("energetic", "fast") else None
    hero_used = hero2_used = False

    for k in range(n_target):
        if scarcity:
            # capacity equation: cps = n/(n*out - (n-1)*fade) >= band*1.08.
            # Renderer law: output = min(out_dur, src/speed) -> we store
            # src_dur=0.73 explicitly and speed=src/out (<=1, subtle slow-mo)
            # so src/speed == out_dur exactly: no trim waste, spans consistent.
            out_dur = round(min(max((n_cap / (band[0] * 1.08)
                                     + (n_cap - 1) * 0.18) / n_cap, 0.4), 5.0), 3)
        elif k == 0:
            out_dur = base_out * 1.9
        elif k == n_target - 1:
            out_dur = base_out * 2.1
        else:
            wiggle = [1.0, 0.85, 0.75, 1.1, 0.9, 0.8][k % 6]
            out_dur = base_out * wiggle
        out_dur = round(min(max(out_dur, 0.4), 5.0), 3)

        speed = 1.0
        if scarcity:
            # span/speed/out consistent: src_dur stored explicitly below;
            # overlap = 0.73 - min candidate spacing (0.44) = 0.29 <= 0.3 (G3)
            src_span = 0.73
            speed = round(max(0.55, min(1.0, src_span / out_dur)), 3)
        else:
            if hero_t is not None and not hero_used and abs(cursor - hero_t) <= beat_period * 1.5:
                speed = 0.5
            elif hero2_t is not None and not hero2_used and abs(cursor - hero2_t) <= beat_period * 1.5:
                speed = 1.25
            src_span = out_dur / speed
        start = sel.pick(cursor, src_span)
        if start is None:
            break                      # D3: never wrap - stop filling instead
        if speed == 0.5:
            hero_used = True
        elif speed == 1.25:
            hero2_used = True
        zoom = ([1.0, 1.08, 1.0, 1.13, 1.0, 1.06][k % 6]
                if style_cfg.get("cut_style") == "beat_grid" else 1.0)
        segs.append({"i": k, "src_start": round(start, 3), "out_dur": out_dur,
                     "speed": speed, "zoom": zoom,
                     **({"src_dur": src_span} if scarcity else {})})
        # scarcity mode: let the next pick reach the adjacent candidate; the
        # resulting <=0.28s source overlap is consumed deliberately and hidden
        # inside the crossfade (pick() still enforces the G3 <=0.3s rule)
        cursor = start + src_span - (0.28 if scarcity else 0.0) \
            + (0.0 if scarcity else base_out * 0.3)

    # reindex after possible early stop
    for j, s in enumerate(segs):
        s["i"] = j
    audit = sel.audit(len(segs))
    if len(segs) < 6:
        print(f"[plan] WARNING: only {len(segs)} clean segments available "
              f"(luma gate dropped {audit['n_dropped_luma']})", flush=True)

    for s in segs:
        if "src_dur" not in s:  # scarcity segs already carry consistent spans
            s["src_dur"] = round(min(s["out_dur"] / s["speed"],
                                     max(0.4, dur - 0.25 - s["src_start"])), 3)
            s["out_dur"] = round(s["src_dur"] * s["speed"], 3)

    # ---- motion-variance interleave (creative review r1: desert tail sag) ----
    # Motion score per segment = mean |dY| of the luma profile inside its span.
    # Reorder so static shots spread between action beats instead of clumping
    # (same spans, different presentation order: G3/G7 unaffected).
    if luma and len(segs) > 5:
        def motion(s):
            ys = [q["y"] for q in luma
                  if s["src_start"] - 0.2 <= q["t"] <= s["src_start"] + s["src_dur"] + 0.2]
            return (sum(abs(b - a) for a, b in zip(ys, ys[1:])) / max(len(ys) - 1, 1)
                    if len(ys) > 1 else 0.0)
        by_motion = sorted(segs, key=motion, reverse=True)
        order, lo_i, hi_i = [], 0, len(by_motion) - 1
        while lo_i <= hi_i:                    # strongest, weakest, 2nd, 2nd-weak...
            order.append(by_motion[lo_i]); lo_i += 1
            if lo_i <= hi_i:
                order.append(by_motion[hi_i]); hi_i -= 1
        segs[:] = order
        for j, s in enumerate(segs):
            s["i"] = j

    soft = style_cfg.get("transitions") == "soft_fades"
    per_section = max(6, len(segs) // 3)
    # spec 2.4: hard cut default (0.05 pseudo = 1-2 frames), fade <= 0.18,
    # fadewhite ONLY at section boundaries <= 2 frames (0.067 @30fps),
    # fadeblack ONLY as the final transition <= 0.4s
    flash_dur = round(2.0 / 30.0, 3)
    section_times = []
    cum = 0.0
    for k in range(len(segs) - 1):
        cum += segs[k]["out_dur"]
        if scarcity:
            # 0.18s crossfades hide the deliberate source overlap (see solver)
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.18}
        elif soft:
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.5}
        elif k == 0:
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.18}
        elif (k + 1) == len(segs) - 1:
            # G1 2% black budget: scale the outro fade with runtime
            est_total = sum(x["out_dur"] for x in segs)
            fb = round(min(0.4, max(0.12, est_total * 0.018)), 3)
            segs[k]["transition_after"] = {"type": "fadeblack", "dur": fb}
        elif (k + 1) % per_section == 0:
            segs[k]["transition_after"] = {"type": "fadewhite", "dur": flash_dur}
            section_times.append(round(cum, 2))
        else:
            segs[k]["transition_after"] = {"type": "fade", "dur": 0.05}
    if segs:
        segs[-1]["transition_after"] = {"type": "none", "dur": 0.0}

    # G7 metric: median |cut - nearest beat| in ms (cuts sit on the beat grid)
    import statistics
    grid = sorted(set(round(b, 3) for b in beats_list))
    devs = [min((abs(s["src_start"] - b) for b in grid), default=0.5) for s in segs]
    beat_align_ms = round(1000 * statistics.median(devs), 1) if devs else 0.0
    audit["beat_alignment_ms"] = beat_align_ms
    audit["section_flash_times"] = section_times
    audit["cut_density_target_cps"] = round(cps_target, 2)
    return segs, audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--out", default="out")
    ap.add_argument("--style", default="beat_montage")
    ap.add_argument("--target-len", type=float, default=None)
    ap.add_argument("--mood", default="cinematic")
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

    source_meta = dict(meta, path=os.environ.get("CF_SOURCE_PATH") or meta.get("path"))
    segments, audit = build_timeline(source_meta, beats, style_cfg, a.style, target,
                                     luma_cache=os.path.join(a.reports, "luma.json"))
    total = sum(s["out_dur"] for s in segments) - sum(
        s["transition_after"]["dur"] for s in segments[:-1])
    cps = round(len(segments) / total, 2) if total else 0.0
    section_times = audit.get("section_flash_times", [])

    # synthesized SFX plan (zero downloads): impact at hook, whoosh at section flashes
    sfx_events = []
    if style_cfg.get("pacing") in ("energetic", "fast"):
        sfx_events.append({"t": 0.0, "kind": "impact"})
        sfx_events += [{"t": t, "kind": "whoosh"} for t in section_times]
        peaks = beats.get("energy_peak_starts") or []
        if peaks and len(segments) > 4:
            hero_out = next((sum(s2["out_dur"] for s2 in segments[:i])
                             for i, s2 in enumerate(segments)
                             if abs(s2["src_start"] - peaks[0]) < 0.5), None)
            if hero_out and hero_out > 1.5:
                sfx_events.append({"t": round(hero_out - 1.2, 2), "kind": "riser"})

    hook_text = pick_hook(transcript, beats, style_cfg)
    # resilience: an empty transcript must never ship a hookless open
    # (creative loop draft 37886393173: silent transcribe fail -> hook=no -> no typography)
    if not hook_text:
        hook_text = a.title or "MONTAGE"
    plan = {
        "style": a.style,
        "mood": a.mood,
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
        "cut_density_cps": cps,
        "cuts_band": style_cfg.get("cuts_band"),
        "beat_alignment_ms": audit.get("beat_alignment_ms", 0.0),
        "sfx_events": sfx_events,
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
                    "preview": False, "n_segments": len(segments),
                    "vertical": plan["vertical_plan"],
                    "suppress_title": bool(hook_text),
                    "active_crop": meta.get("active_crop"),
                    "selection_audit": audit},
           "segments": segments}, f"{a.out}/timeline.json")
    jdump(audit, f"{a.reports}/selection_audit.json")
    record_stage(a.reports, "06-edit-decision", "success", t0=t0,
                 optimization_applied="D3 selection: luma gate + forward-only + overlap cap",
                 optimization_result=(f"candidates={audit['n_candidates']} "
                                      f"selected={audit['n_selected']} "
                                      f"dropped_luma={audit['n_dropped_luma']}"))
    print(f"plan: {len(segments)} segs, {total:.1f}s, hook={bool(hook_text)}, "
          f"grade={plan['color_grade']}, audit={audit['n_selected']}/"
          f"{audit['n_candidates']} luma_dropped={audit['n_dropped_luma']}")


if __name__ == "__main__":
    main()
