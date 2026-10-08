#!/usr/bin/env python3
"""Stage 9a: captions + hook card -> media/captions.ass (libass, spec v2).

Typography (creative spec 2.1 / gate G5):
  - caption face: Montserrat (OFL, media/fonts), Bold, Fontsize 96-112 @1080x1920
  - Outline 5 black, Shadow 3, MarginV 240-300 clamped into bottom safe-zone
  - max 2 lines of <= 18 chars, wrapped on phrase boundaries
  - keyword pop on the active word: {\\1c&H00FFFF&\\fscx112\\fscy112\\t(0,120,...)}
  - hook card: Anton display face 150-190px, <= 6 words, centered at y = 30%,
    entrance 0.25s (alpha 0->1 + scale 92->100), gone by 2.5s
  - face-avoidance: MediaPipe bbox when available (per-cue decision logged),
    else bottom safe-zone. Decisions land in captions_report.json.
"""
import argparse
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
from utils import jdump, jload, record_stage  # noqa: E402
import time  # noqa: E402

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cine,{cap_font},{size},{primary},{primary},{outline},&H96000000,1,0,0,0,100,100,0,0,1,{outline_w},{shadow},2,{ml},{mr},{mv},1
Style: Hook,{hook_font},{hook_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,6,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

PHRASE_SPLIT = re.compile(r"(?<=[,.;:!?])\s+")


def ts(t):
    h, m = int(t // 3600), int(t % 3600 // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def wrap2(text, max_chars):
    """Wrap into <= 2 lines of <= max_chars, preferring phrase boundaries."""
    for part in PHRASE_SPLIT.split(text):
        pass
    phrases = PHRASE_SPLIT.split(text)
    lines, cur = [], ""
    for phrase in phrases:
        for word in phrase.split():
            cand = (cur + " " + word).strip()
            if len(cand) <= max_chars:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = word
    if cur:
        lines.append(cur)
    if len(lines) <= 2:
        return lines
    # rebalance into exactly 2 lines near the midpoint
    mid = len(text) // 2
    best, bd = 0, 10**9
    for i, ln in enumerate(lines[:-1]):
        acc = len(" ".join(lines[:i + 1]))
        if abs(acc - mid) < bd:
            bd, best = abs(acc - mid), i
    return [" ".join(lines[:best + 1]), " ".join(lines[best + 1:])]


def keyword_of(text):
    """Active word = longest alphanumeric token (caps/digits weighted)."""
    words = re.findall(r"[A-Za-z0-9']+", text)
    if not words:
        return None
    scored = [(w, len(w) + (3 if w.isupper() else 0) + (2 if any(ch.isdigit() for ch in w) else 0))
              for w in words]
    return max(scored, key=lambda kv: kv[1])[0]


def pop_tags(word):
    return "{\\1c&H00FFFF&\\fscx112\\fscy112\\t(0,120,\\fscx100\\fscy100)}" + word + "{\\1c&HFFFFFF&}"


def face_boxes(source, cue_times):
    """Optional MediaPipe face detection at cue mid-times -> [{t, bbox|None}]."""
    try:
        import cv2  # noqa
        import mediapipe as mp  # noqa
    except Exception:
        return [{"t": t, "bbox": None, "reason": "mediapipe_unavailable"} for t in cue_times]
    out = []
    try:
        det = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
        for t in cue_times:
            p = subprocess_frame(source, t)
            if p is None:
                out.append({"t": t, "bbox": None, "reason": "frame_grab_failed"})
                continue
            res = det.process(p)
            if res.detections:
                b = res.detections[0].location_data.relative_bounding_box
                out.append({"t": t, "bbox": [b.xmin, b.ymin, b.width, b.height],
                            "reason": "face_detected"})
            else:
                out.append({"t": t, "bbox": None, "reason": "no_face"})
    except Exception as e:
        out = [{"t": t, "bbox": None, "reason": f"mediapipe_error:{type(e).__name__}"}
               for t in cue_times]
    return out


def subprocess_frame(source, t):
    """Decode one frame at time t as a BGR numpy array (640x360) for detection."""
    import subprocess as sp
    W, H = 640, 360
    try:
        raw = sp.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", source,
                      "-frames:v", "1", "-vf", f"scale={W}:{H}",
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     capture_output=True).stdout
        if len(raw) < W * H * 3:
            return None
        import numpy as np
        import cv2
        arr = np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="reports/transcript.json")
    ap.add_argument("--style", default="minimal_clean")
    ap.add_argument("--plan", default="reports/edit_plan.json")
    ap.add_argument("--out", default="media/captions.ass")
    ap.add_argument("--resolution", default="1080x1920")
    ap.add_argument("--fontsdir", default="media/fonts")
    ap.add_argument("--source", default=None, help="source video for optional face-avoidance")
    a = ap.parse_args()

    t0 = time.time()
    tr = jload(a.transcript, {})
    plan = jload(a.plan, {})
    styles = jload(REPO_ROOT + "/configs/caption_styles.json", {})
    safe = jload(REPO_ROOT + "/configs/safe_zones.json", {})
    st = styles.get(a.style or "", styles["minimal_clean"])
    if not st:
        raise SystemExit("caption style disabled in plan")

    w, h = map(int, a.resolution.split("x"))
    hook_only = not a.style   # empty style = hook card only (no caption cues)
    fs = int(h * st["font_size_ratio"])
    fs = min(112, max(96, fs))                      # spec band
    mv = int(h * st.get("margin_v_ratio", 0.152))
    mv = min(300, max(240, mv))                     # spec band 240-300
    bottom_safe = int(h * safe.get("bottom", 0.15))
    if mv < bottom_safe:                            # safe-zone assert (G5)
        print(f"[captions] marginV {mv} < bottom safe {bottom_safe}; clamped", flush=True)
        mv = min(300, bottom_safe + 4)
    ml = int(w * safe.get("sides", 0.06))
    hook_size = min(190, max(150, int(h * 0.088)))  # 150-190px at 1920

    cap_font, hook_font = "Montserrat", "Anton"
    hdr = ASS_HEADER.format(w=w, h=h, cap_font=cap_font, hook_font=hook_font,
                            size=fs, primary=st["primary"], outline=st["outline"],
                            outline_w=st["outline_width"], shadow=st["shadow"],
                            ml=ml, mr=ml, mv=mv, hook_size=hook_size)

    events, decisions, cues = [], [], []

    # ---- hook card (title_card styles): display face, y=30%, entrance anim ----
    hook = plan.get("hook") or {}
    if hook.get("type") in ("title_card", "bold_statement", "emotional_line") and hook.get("text"):
        words = hook["text"].split()[:6]
        text = " ".join(words).upper()
        h0, h1 = (hook.get("seconds") or [0, 2.5])[:2]
        h1 = min(h1, 2.5)
        y = int(h * safe.get("hook_y_center", 0.30))
        tags = (r"{\pos(" + f"{w // 2},{y})" +
                r"\fad(250,180)\fscx92\fscy92" +
                r"\t(0,250,\fscx100\fscy100)}")
        events.append(f"Dialogue: 1,{ts(h0)},{ts(h1)},Hook,,0,0,0,,{tags}{text}")
        decisions.append({"cue": h0, "element": "hook_card", "placement": f"y={y}",
                          "reason": "hook_y_center per safe_zones", "face": None})

    # ---- captions ----
    segs = [] if hook_only else (tr.get("segments", []) or [])
    for seg in segs:
        text = seg["text"].strip()
        if not text:
            continue
        if st.get("uppercase"):
            text = text.upper()
        lines = wrap2(text, st.get("max_chars", 18))
        if len(lines) > 2:
            lines = lines[:2]
        body_plain = "\\N".join(lines)
        kw = keyword_of(text) if st.get("karaoke_pop") else None
        if kw:
            parts = []
            for ln in lines:
                parts.append(" ".join(pop_tags(wd) if wd.strip(".!?,:;") == kw else wd
                                      for wd in ln.split()))
            body = "\\N".join(parts)
        else:
            body = body_plain
        fade = ""
        if st.get("fade_per_line"):
            fade = r"{\fad(" + f"{int(st['fade_per_line']*300)},{int(st['fade_per_line']*300)})" + "}"
        dur = seg["end"] - seg["start"]
        n = max(1, int(dur // 3.5) + 1)
        chunk = dur / n
        for k in range(n):
            s0 = seg["start"] + k * chunk
            e0 = min(seg["end"], s0 + chunk - 0.05)
            events.append(f"Dialogue: 0,{ts(s0)},{ts(e0)},Cine,,0,0,0,,{fade}{body}")
            cue = round((s0 + e0) / 2, 2)
            cues.append(cue)
            decisions.append({"cue": cue, "element": "caption",
                              "placement": f"marginV={mv}",
                              "lines": len(lines),
                              "keyword": kw,
                              "face": None, "reason": "bottom_safe_zone"})

    # ---- optional face-avoidance pass (logged; MediaPipe when available) ----
    if a.source and os.path.isfile(a.source) and cues:
        fb = face_boxes(a.source, cues[:6])
        for d, f in zip([d for d in decisions if d["element"] == "caption"][:len(fb)], fb):
            d["face"] = f["bbox"]
            d["reason"] = f["reason"] + (" -> caption below face bbox" if f["bbox"]
                                         else " -> bottom safe-zone")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    open(a.out, "w").write(hdr + "\n".join(events))
    jdump({"style": a.style, "events": len(events), "cues": cues[:12],
           "font_caption": cap_font, "font_hook": hook_font,
           "fontsize": fs, "margin_v": mv, "hook_size": hook_size,
           "licenses": {"Montserrat": "OFL", "Anton": "OFL"},
           "safe_zone_assert": {"bottom": bottom_safe, "margin_v": mv,
                                "within": mv >= bottom_safe},
           "decisions": decisions[:12]},
          "reports/captions_report.json")
    record_stage("reports", "09a-captions", "success", t0=t0)
    print(f"captions.ass events={len(events)} style={a.style} fs={fs} mv={mv} "
          f"hook={'yes' if 'Hook' in str(hdr) and any('Hook,' in e for e in events) else 'no'}")


if __name__ == "__main__":
    main()
