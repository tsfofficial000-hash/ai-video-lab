#!/usr/bin/env python3
"""Shared segment-selection core (defect D3).

Guarantees enforced here (G3):
  - forward-only walk: no wrap-around, opening never replayed
  - no source-range overlap > 0.3s between selected segments
  - luma gate: a candidate is usable only if its window's min-Y >= min_y
  - end-card / dark-zone exclusion via the source luma profile
Callers (edit_plan.py, montage/build_timeline.py) keep rhythm/hero/transition logic.
"""
import json
import os
import subprocess


def luma_profile_ffmpeg(src, fps=2, cache=None):
    """2fps YAVG profile of a source video -> [{"t", "y"}]. Cached to `cache` path."""
    if cache and os.path.isfile(cache):
        try:
            return json.load(open(cache))
        except Exception:
            pass
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-vf",
                        f"fps={fps},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout:
        print(f"[luma] PROFILE FAILED rc={p.returncode} src={src!r} "
              f"stderr_tail={(p.stderr or '')[-200:]!r}", flush=True)
    times, ys = [], []
    for ln in (p.stdout or "").splitlines():
        mt, my = "pts_time:" in ln, "YAVG=" in ln
        if mt:
            try:
                times.append(float(ln.split("pts_time:")[1].split()[0].rstrip(",")))
            except Exception:
                times.append(len(times) / float(fps))
        if my:
            try:
                ys.append(float(ln.split("YAVG=")[1].split()[0].rstrip(",")))
            except Exception:
                ys.append(255.0)
    prof = [{"t": t, "y": y} for t, y in zip(times, ys)]
    if cache and prof:
        os.makedirs(os.path.dirname(os.path.abspath(cache)), exist_ok=True)
        json.dump(prof, open(cache, "w"))
    return prof


def window_min_y(luma, start, dur, pad=0.25):
    """Min YAVG over [start, start+dur]; unknown regions treated as bright (255)."""
    ys = [p["y"] for p in luma if start - pad <= p["t"] <= start + dur + pad]
    return min(ys) if ys else 255.0


def dark_ranges(luma, thr=30, step=0.5, min_len=0.6):
    """Contiguous dark regions [(start, end)] where YAVG < thr."""
    dark_ts = [p["t"] for p in luma if p["y"] < thr]
    if not dark_ts:
        return []
    dark_ts.sort()
    ranges, s0, prev = [], dark_ts[0], dark_ts[0]
    for t in dark_ts[1:]:
        if t - prev <= step * 1.5:
            prev = t
        else:
            ranges.append((s0, prev + step))
            s0, prev = t, t
    ranges.append((s0, prev + step))
    return [(a, b) for a, b in ranges if b - a >= min_len]


class Selector:
    """Forward-only, overlap-free, luma-gated candidate walk over a beat grid.
    E6: optional per-scene-cluster diversity cap (max N segments per
    PySceneDetect scene) so near-identical shots cannot clump mid-montage."""

    def __init__(self, beats, dur, luma=None, min_y=30.0, head_guard=1.5,
                 tail_guard=None, max_overlap=0.3, scene_of=None,
                 max_per_scene=None, scene_cuts=None):
        self.dur = dur
        self.min_y = min_y
        self.max_overlap = max_overlap
        self.luma = luma or []
        self.tail_guard = tail_guard if tail_guard is not None else max(1.5, 0.05 * dur)
        self.head_guard = head_guard
        self.scene_of = scene_of
        self.max_per_scene = max_per_scene
        self.scene_cuts = sorted(scene_cuts or [])
        self.dark = dark_ranges(self.luma) if self.luma else []
        self.used = []  # (start, end) reserved source spans
        self.scene_usage = {}
        self.stats = {"dropped_luma": 0, "dropped_overlap": 0,
                      "dropped_exhausted": 0, "dropped_scene_cap": 0}
        hi = dur - self.tail_guard
        self.candidates = []
        for b in sorted({round(b, 3) for b in beats}):
            if b < head_guard or b > hi:
                continue
            if self.luma and window_min_y(self.luma, b, 1.0) < min_y:
                self.stats["dropped_luma"] += 1
                continue
            if any(a - 0.05 <= b <= z + 0.05 for a, z in self.dark):
                self.stats["dropped_luma"] += 1
                continue
            self.candidates.append(b)
        self.pos = 0

    def _overlaps(self, start, span):
        e = start + span
        worst = 0.0
        for a, z in self.used:
            ov = min(z, e) - max(a, start)
            if ov > worst:
                worst = ov
        return worst

    def pick(self, cursor, src_span):
        """Nearest candidate >= cursor whose span is free AND fully bright;
        None if exhausted. Never wraps back to the opening (D3).
        G3: the WHOLE span must hold min-Y >= min_y (long spans otherwise
        sneak past the 1.0s candidate-window check and ship dark frames)."""
        n = len(self.candidates)
        i = self.pos
        while i < n:
            c = self.candidates[i]
            if c < cursor - 1e-6:
                i += 1
                continue
            if c + src_span > self.dur - 0.25:
                i += 1
                self.stats["dropped_overlap"] += 0
                continue
            if self.luma and window_min_y(self.luma, c, src_span) < self.min_y:
                i += 1
                self.stats["dropped_luma"] += 1
                continue
            if self._overlaps(c, src_span) > self.max_overlap:
                i += 1
                self.stats["dropped_overlap"] += 1
                continue
            if self.scene_of is not None and self.max_per_scene is not None:
                sid = self.scene_of(c + 0.5 * src_span)
                if self.scene_usage.get(sid, 0) >= self.max_per_scene:
                    i += 1
                    self.stats["dropped_scene_cap"] += 1
                    continue
            self.used.append((c, c + src_span))
            if self.scene_of is not None and self.max_per_scene is not None:
                sid = self.scene_of(c + 0.5 * src_span)
                self.scene_usage[sid] = self.scene_usage.get(sid, 0) + 1
            self.pos = i + 1
            return c
        self.stats["dropped_exhausted"] += 1
        return None

    def audit(self, n_selected):
        spans = sorted(self.used)
        overlaps = []
        for (a1, z1), (a2, z2) in zip(spans, spans[1:]):
            ov = z1 - a2
            if ov > self.max_overlap:
                overlaps.append(round(ov, 3))
        hist = {}
        if self.scene_of is not None:
            for (a1, z1) in spans:
                sid = self.scene_of(a1 + 0.5 * (z1 - a1))
                hist[str(sid)] = hist.get(str(sid), 0) + 1
        return {
            "wraparound": False,
            "luma_gate_min_y": self.min_y,
            "head_guard_s": self.head_guard,
            "tail_guard_s": round(self.tail_guard, 2),
            "excluded_dark_ranges": [[round(a, 2), round(b, 2)] for a, b in self.dark],
            "n_candidates": len(self.candidates),
            "n_selected": n_selected,
            "n_dropped_luma": self.stats["dropped_luma"],
            "n_dropped_overlap": self.stats["dropped_overlap"],
            "n_dropped_exhausted": self.stats["dropped_exhausted"],
            "n_dropped_scene_cap": self.stats["dropped_scene_cap"],
            "max_per_scene": self.max_per_scene,
            "scene_cuts": [round(c, 2) for c in self.scene_cuts],
            "cluster_histogram": hist,
            "overlaps_gt_030s": overlaps,
            "selected_span": [round(spans[0][0], 3), round(spans[-1][1], 3)] if spans else None,
        }
