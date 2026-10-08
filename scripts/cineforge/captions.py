#!/usr/bin/env python3
"""Stage 9a: captions -> media/captions.ass (libass styled, safe-zone aware)."""
import argparse
import re

from utils import jdump, jload, record_stage
import time

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cine,{font},{size},{primary},{primary},{outline},&H96000000,{bold},0,0,0,100,100,0,0,1,{outline_w},{shadow},{align},{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(t):
    h, m = int(t // 3600), int(t % 3600 // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def wrap(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="reports/transcript.json")
    ap.add_argument("--style", default="minimal_clean")
    ap.add_argument("--plan", default="reports/edit_plan.json")
    ap.add_argument("--out", default="media/captions.ass")
    ap.add_argument("--resolution", default="1080x1920")
    a = ap.parse_args()

    t0 = time.time()
    tr = jload(a.transcript, {})
    plan = jload(a.plan, {})
    styles = jload("configs/caption_styles.json", {})
    st = styles.get(a.style or "", styles["minimal_clean"])
    if not st:
        raise SystemExit("caption style disabled in plan")

    w, h = map(int, a.resolution.split("x"))
    fs = int(h * st["font_size_ratio"] * (w / 1080.0) ** 0)
    mv = int(h * st.get("margin_v_ratio", 0.18))
    align = 2  # bottom center
    if st["position"] in ("center", "center_lower"):
        align = 2 if st["position"] == "center_lower" else 5
    bold = 1 if st["outline_width"] > 2.5 else 0

    hdr = ASS_HEADER.format(w=w, h=h, font="DejaVu Sans", size=fs, primary=st["primary"],
                            outline=st["outline"], outline_w=st["outline_width"],
                            shadow=st["shadow"], bold=bold, align=align,
                            ml=int(w * 0.06), mr=int(w * 0.06), mv=mv)
    events = []
    for seg in tr.get("segments", []):
        text = seg["text"].strip()
        if not text:
            continue
        if st.get("uppercase"):
            text = text.upper()
        lines = wrap(text, st.get("max_chars", 40))
        body = r"\N".join(lines)
        fade = ""
        if st.get("fade_per_line"):
            fade = r"{\fad(" + f"{int(st['fade_per_line']*300)},{int(st['fade_per_line']*300)})" + "}"
        dur = seg["end"] - seg["start"]
        # split long segments into <=3.5s chunks
        n = max(1, int(dur // 3.5) + 1)
        chunk = dur / n
        for k in range(n):
            s0 = seg["start"] + k * chunk
            events.append(f"Dialogue: 0,{ts(s0)},{ts(min(seg['end'], s0 + chunk - 0.05))},Cine,,0,0,0,,{fade}{body}")

    open(a.out, "w").write(hdr + "\n".join(events))
    jdump({"style": a.style, "events": len(events), "out": a.out},
          "reports/captions_report.json")
    record_stage("reports", "09a-captions", "success", t0=t0)
    print(f"captions.ass events={len(events)} style={a.style}")


if __name__ == "__main__":
    main()
