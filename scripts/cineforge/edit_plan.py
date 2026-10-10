#!/usr/bin/env python3
"""Stage 6: edit decision engine -> reports/edit_plan.json (+ out/timeline.json for engine)
Style-aware: hook selection, beat/scene aligned cuts, pacing per mood, ducking plan."""
import argparse
import json
import os
import sys

REPO_ROOT = __import__("os").path.abspath(
    __import__("os").path.join(__file__, "..", "..", ".."))
from utils import jdump, jload, record_stage
from selection import Selector, luma_profile_ffmpeg
import time


def load_bar_map(reports_dir, source_meta):
    """E1: per-scene bar map produced at ingest (make_proxy.sh -> bar_map.py).
    Falls back to the legacy meta-level active_crop when no map exists."""
    p = os.path.join(reports_dir or "reports", "bar_map.json")
    if os.path.isfile(p):
        try:
            return jload(p, {})
        except Exception:
            pass
    ac = source_meta.get("active_crop")
    if ac:
        return {"src_w": source_meta.get("width"), "src_h": source_meta.get("height"),
                "scenes": [], "meta_crop": ac, "legacy": True}
    return None


HOOK_TRAILING_STOP = {"to", "the", "a", "an", "of", "and", "or", "you", "your",
                      "is", "it", "its", "in", "on", "at", "for", "with", "what",
                      "why", "how", "this", "that", "but", "so"}
HOOK_LEADING_STOP = {"to", "the", "a", "an", "of", "and", "or", "but", "so", "is", "it"}


def word_complete(text):
    """A hook is word-complete when its last word is a content word - the
    historic defect was a mid-phrase slice ending on '...TO THE LAND'."""
    import re as _re
    words = _re.findall(r"[A-Za-z0-9']+", text or "")
    return bool(words) and words[-1].lower().strip("'\"") not in HOOK_TRAILING_STOP


def _rule_of(text):
    tl = (text or "").lower()
    if any(w in tl for w in ("what", "why", "how", "who", "when")):
        return "curiosity"
    if any(w in tl for w in ("never", "secret", "best", "insane", "nobody",
                             "escape", "fear", "storm", "last")):
        return "stakes"
    return "punch"


def _clause_candidates(text, rule):
    """Complete phrases from ONE sentence: complete clauses (split at
    punctuation) or edge-trimmed spans. Interior slicing is IMPOSSIBLE by
    construction - the v2.0 hook 'WHAT BRINGS YOU / TO THE LAND' (a prefix
    cut of a 10-word sentence) can never be authored again."""
    import re as _re
    out = []
    for clause in _re.split(r"[,.;:!?]+", text or ""):
        words = clause.split()
        if not words:
            continue
        if len(words) <= 6:
            out.append((" ".join(words), rule))
            continue
        lead = 0
        while lead < len(words) and words[lead].lower().strip("'\"") in HOOK_LEADING_STOP:
            lead += 1
        trail = len(words)
        while trail > lead and words[trail - 1].lower().strip("'\"") in HOOK_TRAILING_STOP:
            trail -= 1
        trimmed = words[lead:trail]
        if 1 <= len(trimmed) <= 6:
            out.append((" ".join(trimmed), rule + "+edge_trim"))
    return out


def hook_candidates(transcript, beats, style_cfg, title):
    """E5: author 3 COMPLETE hook candidates (<= 6 words each) from transcript
    meaning. Rules: curiosity (question words), punch (short + energy overlap),
    stakes (urgency words). Only complete clauses / edge-trimmed spans qualify;
    an empty transcript falls back to the style's mood-hook list."""
    cands, seen = [], set()
    segs = (transcript or {}).get("segments") or []
    peaks = (beats or {}).get("energy_peak_starts") or []

    def score(s):
        dur = max(s["end"] - s["start"], 0.3)
        energy = sum(1 for p in peaks if p <= s["end"] and p >= s["start"] - 1.0)
        return min(len(s["text"]) / 60.0, 1.0) + energy * 0.5 + (0.5 if dur < 4 else 0)

    for s in sorted(segs, key=score, reverse=True):
        for txt, rule in _clause_candidates(s["text"].strip(), _rule_of(s["text"])):
            key = txt.lower()
            if key not in seen and word_complete(txt):
                seen.add(key)
                cands.append({"text": txt, "rule": rule, "src": round(s["start"], 2)})
    if len(cands) < 3:
        moods = style_cfg.get("hook_moods") or [title or "MONTAGE"]
        for m in moods:
            if len(cands) >= 3:
                break
            if m.lower() not in seen:
                seen.add(m.lower())
                cands.append({"text": m, "rule": "mood_hook", "src": None})
    return cands[:3]


def choose_hook(cands, width_chars=30):
    """Width-fit selects among complete candidates; NEVER truncates one.
    Falls back to the shortest candidate when none fits the width budget."""
    texts = [c["text"] if isinstance(c, dict) else str(c) for c in (cands or [])]
    for t in texts:
        if len(t) <= width_chars:
            return t
    return min(texts, key=len) if texts else ""


def _scene_cuts_detect(src_path):
    """E6 fallback when no ingest bar map exists: PySceneDetect on the source."""
    try:
        from scenedetect import detect, ContentDetector
        return [s.get_seconds() for (s, e) in detect(src_path, ContentDetector(threshold=27.0))]
    except Exception as e:
        print(f"[plan] scene detect unavailable ({type(e).__name__}) - no cluster cap",
              flush=True)
        return []


def _scene_of_factory(cuts):
    import bisect
    cs = sorted(cuts)
    def f(t):
        return bisect.bisect_right(cs, float(t)) - 1
    return f


def build_timeline(source_meta, beats, style_cfg, style, target_len, luma=None,
                    luma_cache=None, transcript=None, reports_dir=None,
                    requested_len=None):
    """Reuse proven montage timeline logic; emit engine-compatible timeline.json.
    D3: selection is forward-only, luma-gated, overlap-free (see selection.Selector).
    `luma` = optional [{t,y}] profile; when absent it is computed from the source
    (cached at luma_cache / reports/luma.json) so the gate always has real data.
    reports_dir: where the ingest bar map (E1) lives."""
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

    # ---- scarcity-aware sizing (G3 no-reuse vs G7 band vs target_len) ----
    # E4: the requested duration must never shrink SILENTLY. Ladder of DECLARED
    # relaxations, then an honest impossibility note:
    #   L0 normal params (luma floor 36, scarcity margin 1.08)
    #   L1 scarcity cps margin 1.08 -> 1.05 -> 1.00 (cps band lower edge)
    #   L2 luma floor 36 -> 30 (max -6, logged reason)
    #   L3 still short -> target_impossible note (max achievable, style density)
    requested = requested_len if requested_len else target_len
    goal = 0.80 * float(requested)
    relaxations = []
    reasons = []
    sc_margin = 1.08
    min_y = 36.0

    # ---- E6: scene clusters - max 2 segments per PySceneDetect scene -------
    barmap = load_bar_map(reports_dir, source_meta)
    scene_cuts = list((barmap or {}).get("scene_cuts") or [])
    if not scene_cuts and source_meta.get("path"):
        scene_cuts = _scene_cuts_detect(source_meta.get("path"))
    max_per_scene = style_cfg.get("max_per_scene")
    scene_of = _scene_of_factory(scene_cuts) if scene_cuts else None
    print(f"[plan] scene clusters: {len(scene_cuts)} cuts, max_per_scene={max_per_scene}",
          flush=True)

    def _predict_total(n_cap_, margin_, base_out_, tgt_):
        n_tgt = max(6, int(round(tgt_ / base_out_)))
        if not n_cap_:
            return 0.0, True
        if n_cap_ * base_out_ < tgt_ * 0.95 and n_tgt > n_cap_:
            return n_cap_ / (band[0] * margin_), True
        return min(tgt_, n_tgt * base_out_), False

    sel = Selector(beats_list, dur, luma=luma, min_y=min_y, scene_of=scene_of,
                   max_per_scene=max_per_scene, scene_cuts=scene_cuts)
    n_cap = len(sel.candidates)
    pred, scarcity = _predict_total(n_cap, sc_margin, base_out, target_len)
    if pred < goal and scarcity:
        # L1: cps margin toward the band's lower edge (declared)
        for m, label in ((1.05, "cps_margin_1.05"), (1.00, "cps_band_lower_edge")):
            if n_cap / (band[0] * m) >= goal:
                relaxations.append({"kind": label, "from": sc_margin, "to": m,
                                    "reason": f"reach {goal:.1f}s (80% of "
                                              f"{float(requested):.0f}s requested)"})
                sc_margin = m
                pred = n_cap / (band[0] * m)
                break
    if pred < goal and luma and min_y > 30.0:
        # L2: widen the luma floor (max -6 points, declared) and re-count
        sel2 = Selector(beats_list, dur, luma=luma, min_y=30.0, scene_of=scene_of,
                        max_per_scene=max_per_scene, scene_cuts=scene_cuts)
        n_cap2 = len(sel2.candidates)
        for m in (sc_margin, 1.05, 1.00):
            if n_cap2 / (band[0] * m) >= goal:
                relaxations.append({"kind": "luma_floor", "from": min_y, "to": 30.0,
                                    "reason": f"candidate capacity {n_cap}->{n_cap2}; "
                                              f"reach {goal:.1f}s"})
                if m != sc_margin:
                    relaxations.append({"kind": "cps_band_lower_edge", "from": sc_margin,
                                        "to": m, "reason": "combined with luma floor"})
                sel, n_cap, scarcity = sel2, n_cap2, True
                min_y, sc_margin = 30.0, m
                pred = n_cap2 / (band[0] * m)
                break
        else:
            if n_cap2 > n_cap:
                relaxations.append({"kind": "luma_floor", "from": min_y, "to": 30.0,
                                    "reason": f"candidate capacity {n_cap}->{n_cap2} "
                                              f"(still short)"})
                sel, n_cap, min_y = sel2, n_cap2, 30.0
            pred, scarcity = _predict_total(n_cap, sc_margin, base_out, target_len)
            if pred < goal:
                reasons.append(f"{n_cap} clean candidates cannot fill "
                               f"{float(requested):.0f}s at style density band {band} "
                               f"even after the declared relaxations")
    if scarcity:
        # Scarcity solver: n candidates is the hard capacity (G3 no-reuse), so
        # every candidate hosts one segment. Sizing contract:
        #   cps = n / (n*out - (n-1)*fade) >= band[0]*margin  (ladder-decided)
        #   src_span = typical candidate spacing + 0.28s deliberate overlap,
        #   hidden inside the crossfades (pick() enforces <=0.3s real)
        # out_dur is solved from the cps constraint; speed lands within +/-7%
        # of 1.0 (imperceptible retiming).
        n_target = min(n_target, n_cap)
        print(f"[plan] scarcity solver: {n_cap} candidates fill only ~{pred:.1f}s "
              f"of the {float(requested):.0f}s request at {1.0/base_out:.2f}cps "
              f"(margin {sc_margin}) -> full-capacity walk", flush=True)

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
            out_dur = round(min(max((n_cap / (band[0] * sc_margin)
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
        # dialogue-bearing segs must not land in the outro fadeblack zone:
        # burned captions under a deliberate fade are unreadable
        speech = (transcript or {}).get("segments") or []
        def has_speech(s):
            # any overlap between the segment's source span and a speech span
            return any(s["src_start"] < x["end"] and x["start"] < s["src_start"] + s["src_dur"]
                       for x in speech)
        tail = 2
        for i in range(len(order) - 1, len(order) - 1 - tail, -1):
            if i > 1 and has_speech(order[i]):
                for j in range(1, i):
                    if not has_speech(order[j]):
                        order[i], order[j] = order[j], order[i]
                        break
        segs[:] = order
        for j, s in enumerate(segs):
            s["i"] = j

    # ---- E1: per-segment active_crop from the ingest-time bar map ----------
    # A vertical editor that ships letterbox bars inside a full-bleed claim is
    # not top-notch: scope shots and full-frame shots each get their own crop.
    # (barmap was already loaded above for the E6 scene clusters)
    bar_census = {"map": bool(barmap), "attached": 0, "scenes": 0}
    if barmap:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import bar_map as _barmap
            bar_census["attached"] = _barmap.attach_segments(segs, barmap)
            bar_census["scenes"] = len(barmap.get("scenes") or [])
            bar_census["legacy"] = bool(barmap.get("legacy"))
            print(f"[plan] bar map: {bar_census['scenes']} scenes, "
                  f"{bar_census['attached']}/{len(segs)} segments carry their own "
                  f"active_crop", flush=True)
        except Exception as e:
            print(f"[plan] WARN bar map attach failed ({type(e).__name__}: {e}) - "
                  f"falling back to meta-level crop only", flush=True)
            bar_census["error"] = str(e)[:120]

    soft = style_cfg.get("transitions") == "soft_fades"
    per_section = max(6, len(segs) // 3)
    # spec 2.4 + E6: hard pseudo-cut default (0.05 = 1-2 frames), fade <= 0.18,
    # fadewhite ONLY at section boundaries <= 2 frames (0.067 @30fps),
    # fadeblack ONLY as the final transition <= 0.4s.
    # E6: the scarcity path uses the SAME mix builder - the v2.0 all-0.18-fade
    # scarcity special case (22/22 identical transitions) is gone. Its 0.28s
    # source overlap stays inside the G3 <=0.3s rule and the 0.05s xfade simply
    # skips the remainder - visually a hard cut.
    flash_dur = round(2.0 / 30.0, 3)
    est_total = sum(x["out_dur"] for x in segs)
    fb_dur = round(min(0.4, max(0.12, est_total * 0.018)), 3)
    decisions_tr = []
    for k in range(len(segs) - 1):
        if soft:
            t = ("fade", 0.5)
        elif k == 0:
            t = ("fade", 0.18)              # opening
        elif (k + 1) == len(segs) - 1:
            t = ("fadeblack", fb_dur)       # outro (G1 budget-scaled)
        elif (k + 1) % per_section == 0:
            t = ("fadewhite", flash_dur)    # section bound, <= 2 frames
        else:
            t = ("fade", 0.05)              # pseudo-cut workhorse
        decisions_tr.append([k, t])

    # E6 band enforcement: the optional typographic transitions (opening fade,
    # section fadewhites) demote to pseudo-cuts until the style's pseudo-cut
    # minimum holds. fadeblack is never demoted. "fadewhite only at section
    # bounds" stays true - demotion removes events, it never relocates them.
    tm_band_cfg = style_cfg.get("transition_mix") or {}
    pmin = float(tm_band_cfg.get("pseudo_cut_min") or 0.0)
    if decisions_tr and pmin > 0:
        n_tr_ = len(decisions_tr)
        need = int(-(-pmin * n_tr_ // 1))   # ceil(pmin * n)
        pseudo_now = sum(1 for _, (t_, d_) in decisions_tr if t_ == "fade" and d_ <= 0.06)
        demotable = [idx for idx, (k_, (t_, d_)) in enumerate(decisions_tr)
                     if t_ in ("fade", "fadewhite") and k_ != 0
                     or (t_ == "fade" and k_ == 0)]
        # demote the opening fade first, then extra fadewhites
        order_dm = ([i for i in demotable if decisions_tr[i][0] == 0]
                    + [i for i in demotable if decisions_tr[i][1][0] == "fadewhite"])
        for idx in order_dm:
            if pseudo_now >= need:
                break
            if decisions_tr[idx][1][0] in ("fade", "fadewhite"):
                decisions_tr[idx][1] = ("fade", 0.05)
                pseudo_now += 1

    mix_census = {"pseudo_cut": 0, "fade": 0, "fadewhite": 0, "fadeblack": 0}
    section_times = []
    cum = 0.0
    for k, (t_, d_) in decisions_tr:
        cum += segs[k]["out_dur"]
        segs[k]["transition_after"] = {"type": t_, "dur": d_}
        if t_ == "fade" and d_ <= 0.06:
            mix_census["pseudo_cut"] += 1
        elif t_ == "fadewhite":
            mix_census["fadewhite"] += 1
            section_times.append(round(cum, 2))
        elif t_ == "fadeblack":
            mix_census["fadeblack"] += 1
        else:
            mix_census["fade"] += 1
    if segs:
        segs[-1]["transition_after"] = {"type": "none", "dur": 0.0}
    transition_mix = mix_census

    # G7 metric: median |cut - nearest beat| in ms (cuts sit on the beat grid)
    import statistics
    grid = sorted(set(round(b, 3) for b in beats_list))
    devs = [min((abs(s["src_start"] - b) for b in grid), default=0.5) for s in segs]
    beat_align_ms = round(1000 * statistics.median(devs), 1) if devs else 0.0
    audit["beat_alignment_ms"] = beat_align_ms
    audit["section_flash_times"] = section_times
    audit["cut_density_target_cps"] = round(cps_target, 2)
    audit["bar_map"] = bar_census
    audit["relaxations"] = relaxations
    audit["transition_mix"] = transition_mix

    # E4: honest impossibility contract - measured delivered vs requested
    delivered_total = sum(s["out_dur"] for s in segs) - sum(
        s["transition_after"]["dur"] for s in segs[:-1])
    if requested_len and delivered_total < 0.80 * float(requested_len):
        audit["target_impossible"] = {
            "requested": round(float(requested_len), 2),
            "delivered": round(delivered_total, 2),
            "max_achievable": round(delivered_total, 2),
            "style": style,
            "cuts_band": band,
            "n_candidates": audit.get("n_candidates"),
            "relaxations": relaxations,
            "reasons": reasons or [
                f"clean-candidate capacity {audit.get('n_candidates')} cannot reach "
                f"{0.8 * float(requested_len):.1f}s at style density band {band}"],
            "note": (f"requested {float(requested_len):.0f}s: max achievable "
                     f"~{delivered_total:.1f}s at {style} density (band {band}) "
                     f"with {audit.get('n_candidates')} clean candidates and the "
                     f"declared relaxations applied"),
        }
        print(f"[plan] TARGET IMPOSSIBILITY: {audit['target_impossible']['note']}",
              flush=True)
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
    requested_len = a.target_len or max(lo, min(hi, dur * 0.55))   # the user ask, before clamps
    target = requested_len
    target = min(target, max(10, dur - 2))

    source_meta = dict(meta, path=os.environ.get("CF_SOURCE_PATH") or meta.get("path"))
    segments, audit = build_timeline(source_meta, beats, style_cfg, a.style, target,
                                     luma_cache=os.path.join(a.reports, "luma.json"),
                                     transcript=transcript, reports_dir=a.reports,
                                     requested_len=requested_len)
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

    hook_cands = hook_candidates(transcript, beats, style_cfg, a.title)
    # E5: width-fit selects among COMPLETE candidates - never a truncation
    hook_text = choose_hook(hook_cands, width_chars=30) if hook_cands else None
    # resilience: an empty transcript must never ship a hookless open
    # (creative loop draft 37886393173: silent transcribe fail -> hook=no -> no typography)
    if not hook_text:
        hook_text = a.title or "MONTAGE"
        hook_cands = hook_cands or [{"text": hook_text, "rule": "title", "src": None}]
    chosen_meta = next((c for c in hook_cands
                        if (c["text"] if isinstance(c, dict) else str(c)) == hook_text), None)
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
            "chosen": hook_text,
            "candidates": hook_cands,
            "rule": (chosen_meta or {}).get("rule") if isinstance(chosen_meta, dict) else None,
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
    # E3: real-music attribution flows plan-ward (captions.py burns the credit
    # as a 1-line outro event when the source is CC-BY); via feeds gate G6
    music_meta = (jload(os.path.join(a.reports, "media_manifest.json"), {}) or {}).get("music") or {}
    plan["music_via"] = music_meta.get("via")
    if music_meta.get("attribution_required") and music_meta.get("credit"):
        plan["music_credit"] = music_meta["credit"]
    # E4: target-fidelity contract fields (gate G11 reads these)
    plan["requested_duration"] = round(float(requested_len), 2)
    plan["duration_chain"] = {
        "requested": round(float(requested_len), 2),
        "style_range": [lo, hi],
        "after_source_cap": round(target, 2),
        "delivered": round(total, 2),
    }
    # always declare the relaxation record - empty means "tried, none needed",
    # the impossibility note carries the reasons when none could help
    plan["relaxations"] = audit.get("relaxations") or []
    plan["transition_mix"] = audit.get("transition_mix") or {}
    plan["scene_diversity"] = {"max_per_scene": audit.get("max_per_scene"),
                               "cluster_histogram": audit.get("cluster_histogram") or {}}
    if audit.get("target_impossible"):
        plan["target_impossible_note"] = audit["target_impossible"]
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
