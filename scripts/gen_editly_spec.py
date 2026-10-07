#!/usr/bin/env python3
"""Generate an Editly JSON spec implementing the shared edit intent.

Demonstrates the "AI-agent integration" claim: the whole edit is one JSON
document an LLM can emit directly. Parses the Whisper SRT and maps cues onto
Editly's per-clip subtitle layers.

Usage: gen_editly_spec.py <subs.srt>  (reads work/narration.wav metadata) > spec.json
"""
import json
import re
import sys

W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
CLIP1_DUR = 6.0        # clip 1 covers master time [0, 6)
CLIP2_START = 5.0      # clip 2 starts at master t=5 (1s crossfade overlap)
CLIP2_DUR = 6.0        # master total = 6 + 6 - 1 = 11s
NARR_END = 10.7


def fmt_t(s: str) -> float:
    s = s.strip().replace(",", ".")
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def parse_srt(path):
    cues = []
    blocks = re.split(r"\n\s*\n", open(path, encoding="utf-8").read().strip())
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            a, b = lines[1].split("-->")
            cues.append((fmt_t(a), fmt_t(b), " ".join(x.strip() for x in lines[2:])))
    return cues


subs_path = sys.argv[1] if len(sys.argv) > 1 else "subs.srt"
try:
    cues = parse_srt(subs_path)
except FileNotFoundError:
    cues = []

clip1_subs, clip2_subs = [], []
for (a, b, tx) in cues:
    # Cue portion falling inside clip 1 (master [0, 6)) -> clip-relative time
    if a < CLIP1_DUR - 0.05:
        clip1_subs.append({
            "type": "subtitle", "text": tx, "fontPath": FONT,
            "textColor": "#ffffff",
            "start": round(max(a, 0), 2),
            "stop": round(min(b, CLIP1_DUR), 2),
        })
    # Cue portion falling inside clip 2 (master [5, 11)) -> clip-relative time
    a2, b2 = a - CLIP2_START, b - CLIP2_START
    if b2 > 0.05 and a2 < CLIP2_DUR:
        clip2_subs.append({
            "type": "subtitle", "text": tx, "fontPath": FONT,
            "textColor": "#ffffff",
            "start": round(max(a2, 0), 2),
            "stop": round(min(b2, CLIP2_DUR), 2),
        })

spec = {
    "outPath": "final_editly.mp4",
    "width": W,
    "height": H,
    "fps": 30,
    "clips": [
        {
            "duration": CLIP1_DUR,
            "layers": [
                {"type": "video", "path": "footage_src", "cutFrom": 3, "cutTo": 9,
                 "resizeMode": "contain-blur"},
                {"type": "title", "text": "AI VIDEO LAB", "fontPath": FONT,
                 "textColor": "#ffffff", "position": "top",
                 "start": 0.3, "stop": 3.5},
                *clip1_subs,
                {"type": "detached-audio", "path": "narration.wav",
                 "cutFrom": 0, "cutTo": NARR_END, "mixVolume": 1.4, "start": 0.3},
            ],
        },
        {
            "duration": CLIP2_DUR,
            "transition": {"type": "fade", "duration": 1},
            "layers": [
                {"type": "video", "path": "footage_src", "cutFrom": 12, "cutTo": 18,
                 "resizeMode": "contain-blur"},
                {"type": "title", "text": "EDITLY JSON EDIT", "fontPath": FONT,
                 "textColor": "#ffffff", "position": "top",
                 "start": 0, "stop": 3},
                *clip2_subs,
            ],
        },
    ],
}
print(json.dumps(spec, indent=2))
print(f"[SPEC] {len(cues)} SRT cues mapped onto {len(clip1_subs) + len(clip2_subs)} subtitle layers", file=sys.stderr)
