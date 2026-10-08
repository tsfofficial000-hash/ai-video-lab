#!/usr/bin/env python3
"""Stage 7: audio mix -> media/mixed_audio.wav
Speech-preserving duck (sidechaincompress), noise reduce optional, loudnorm -16 LUFS."""
import argparse
import subprocess

from utils import jdump, record_stage
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, help="source video/wav carrying speech")
    ap.add_argument("--music", default=None, help="music track (mp3/wav)")
    ap.add_argument("--out", default="media/mixed_audio.wav")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--denoise", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    filters = []
    if a.denoise:
        filters.append("afftdn=nr=12:nf=-32")

    if a.music:
        duck = ("[1:a]volume=0.95[m];[m][0:a]asplit=2[m1][m2];"
                "[0:a]volume=1.0,volume=0.0001[sc];"  # silent key? no - use voice directly
                )
        # proper: voice as sidechain key over music bed
        fc = (
            "[0:a]{}[voice];"
            "[1:a]volume=0.9[mus];"
            "[mus][voice]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=420:"
            "makeup=1.0:level_sc=duck[ducked];"
            "[ducked][voice]amix=inputs=2:duration=first:weights=1 1,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "afade=t=in:d=0.6,volume=1.0[out]"
        ).format(",".join(filters) or "anull")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.voice, "-i", a.music,
               "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "2", a.out]
        mode = "sidechain_duck"
    else:
        fc = ("[0:a]{}," "loudnorm=I=-16:TP=-1.5:LRA=11,"
              "afade=t=in:d=0.3[out]").format(",".join(filters) or "anull")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.voice,
               "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "2", a.out]
        mode = "voice_only"

    subprocess.run(cmd, check=True)
    jdump({"mode": mode, "music": a.music, "target": "I=-16 TP=-1.5 LRA=11",
           "denoise": a.denoise, "out": a.out}, f"{a.reports}/audio_mix_report.json")
    record_stage(a.reports, "07-audio-mix", "success", t0=t0,
                 bottleneck="none (single-pass ffmpeg)")
    print(f"mixed ok mode={mode}")


if __name__ == "__main__":
    main()
