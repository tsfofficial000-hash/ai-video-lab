#!/usr/bin/env python3
"""Synthesize SFX with pure ffmpeg (zero downloads, zero rights):
  impact  = sine drop 180->40Hz + noise burst, fast decay (hook hit, t=0)
  whoosh  = bandpass-swept noise, 0.45s (section flash transitions)
  riser   = noise sweep up 1.2s (pre-drop)
Usage: sfx.py --kind impact --out media/sfx/impact.wav
"""
import argparse
import os
import subprocess


def synth(kind, out, dur=None):
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if kind == "impact":
        d = dur or 0.8
        # pitch-dropping sine via vibrato+atempo illusion: layered sines + noise burst
        fc = ("sine=frequency=180:duration={d},aeval=val(0)*exp(-6*t)|ch=2,"
              "asplit[a][b];"
              "sine=frequency=42:duration={d},aeval=val(0)*exp(-4*t)|ch=2,adelay=30|30[c];"
              "anoisesrc=color=brown:duration=0.18:amplitude=0.7,"
              "aeval=val(0)*exp(-16*t)|ch=2[d];"
              "[a][c][d]amix=inputs=3:duration=longest:normalize=0,volume=0.9").replace(
                  "aeval=val(0)*exp(-6*t)|ch=2", "aformat=channel_layouts=stereo"
              ).replace("aeval=val(0)*exp(-4*t)|ch=2", "aformat=channel_layouts=stereo"
              ).replace("aeval=val(0)*exp(-16*t)|ch=2", "aformat=channel_layouts=stereo")
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "lavfi", "-i", f"sine=frequency=180:duration={d}",
               "-f", "lavfi", "-i", f"sine=frequency=42:duration={d}",
               "-f", "lavfi", "-i", "anoisesrc=color=brown:duration=0.18:amplitude=0.7",
               "-filter_complex",
               f"[0:a]aformat=channel_layouts=stereo,afade=t=out:st={d*0.25:.2f}:d={d*0.75:.2f},volume=0.8[s1];"
               f"[1:a]aformat=channel_layouts=stereo,volume=0.9,afade=t=out:st={d*0.3:.2f}:d={d*0.7:.2f}[s2];"
               f"[2:a]aformat=channel_layouts=stereo,afade=t=out:st=0.04:d=0.14,volume=0.85[s3];"
               f"[s1][s2][s3]amix=inputs=3:duration=longest:normalize=0,volume=0.95[out]",
               "-map", "[out]", "-ar", "48000", "-ac", "2", out]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    elif kind == "whoosh":
        d = dur or 0.45
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={d}:amplitude=0.8",
               "-af", (f"bandpass=f=900:width_type=o:w=1.2,"
                       "aformat=channel_layouts=stereo,volume=0.75,"
                       "afade=t=in:d=0.08,"
                       f"afade=t=out:st={d*0.5:.2f}:d={d*0.5:.2f}"),
               "-ar", "48000", "-ac", "2", out]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    elif kind == "riser":
        d = dur or 1.2
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "lavfi", "-i", f"anoisesrc=color=white:duration={d}:amplitude=0.5",
               "-af", (f"bandpass=f=500:width_type=o:w=2,"
                       "aformat=channel_layouts=stereo,"
                       f"volume='min(1,0.15+t/{d}*1.1)':eval=frame,"
                       f"afade=t=out:st={d-0.08:.2f}:d=0.08,volume=0.8"),
               "-ar", "48000", "-ac", "2", out]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    else:
        raise SystemExit(f"unknown sfx kind {kind}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["impact", "whoosh", "riser"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    synth(a.kind, a.out)
    print(f"sfx {a.kind} -> {a.out}")


if __name__ == "__main__":
    main()
