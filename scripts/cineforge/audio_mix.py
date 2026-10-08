#!/usr/bin/env python3
"""Stage 7: audio mix -> media/mixed_audio.wav
Speech-preserving duck (sidechaincompress, D7-fixed), noise reduce optional,
loudnorm -16 LUFS. Writes duck-depth diagnostics so G6 is measurable:
  media/_ref_music.wav    = music bed at mix gain, unducked
  media/_ducked_music.wav = same bed after sidechain compression
  duck_depth_db           = mean RMS drop in voice-active windows (ref - ducked)

D7 note: only numeric options are passed to sidechaincompress (the old text
constant was an invalid ffmpeg argument that crashed the music path).
"""
import argparse
import os
import re
import subprocess

from utils import jdump, record_stage
import time


def voice_windows(voice, min_sil=0.25):
    """Voice-active windows from silencedetect (inverse of silence)."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", voice, "-af",
                          f"silencedetect=noise=-38dB:d={min_sil}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    sil = [(float(a), float(b)) for a, b in
           re.findall(r"silence_start:\s*([\d.]+)[\s\S]*?silence_end:\s*([\d.]+)", err)]
    return sil  # silence regions; active = complement


def rms_db(path, t0, dur):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(t0), "-t", str(dur),
                          "-i", path, "-af", "astats=metadata=1", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    vals = [float(m) for m in re.findall(r"RMS level dB: (-?[\d.]+)", err)]
    return sum(vals) / len(vals) if vals else -120.0


def measure_duck_depth(voice, ducked_wav, ref_wav, dur):
    """Mean (ref RMS - ducked RMS) over voice-active windows."""
    sil = voice_windows(voice)
    dur_a = 0.0
    prev = 0.0
    active = []
    for s, e in sil:
        if s - prev > 0.3:
            active.append((prev, min(s, dur)))
        prev = e
    if dur - prev > 0.3:
        active.append((prev, dur))
    depths = []
    for a0, a1 in active:
        mid = (a0 + a1) / 2.0
        win = min(0.4, (a1 - a0) / 2.0)
        r = rms_db(ref_wav, mid, win)
        d = rms_db(ducked_wav, mid, win)
        depths.append(r - d)
    return round(sum(depths) / len(depths), 2) if depths else 0.0, len(depths)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, help="source video/wav carrying speech")
    ap.add_argument("--music", default=None, help="music track (mp3/wav)")
    ap.add_argument("--out", default="media/mixed_audio.wav")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--denoise", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    den = "afftdn=nr=12:nf=-32," if a.denoise else ""

    if a.music:
        # voice = sidechain key; music = main input. Numeric options only
        # (the invalid text constant that crashed ffmpeg is gone - see D7).
        fc = (
            "[0:a]{}anull[voice];"
            "[1:a]volume=0.9[mmain];"
            "[mmain][voice]sidechaincompress=threshold=0.02:ratio=8:attack=20:"
            "release=300:makeup=1.0[ducked];"
            "[ducked][voice]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "afade=t=in:d=0.6,volume=1.0[out]"
        ).format(den)
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.voice, "-i", a.music,
               "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "2", a.out]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        # diagnostics for measurable ducking (G6)
        out_dir = os.path.dirname(os.path.abspath(a.out))
        os.makedirs(out_dir, exist_ok=True)
        ref_wav = os.path.join(out_dir, "_ref_music.wav")
        ducked_wav = os.path.join(out_dir, "_ducked_music.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.music,
                        "-af", "volume=0.9", "-t", "30", ref_wav],
                       check=True, capture_output=True, text=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.voice, "-i", a.music,
                        "-filter_complex",
                        "[0:a]{}anull[voice];[1:a]volume=0.9[m];"
                        "[m][voice]sidechaincompress=threshold=0.02:ratio=8:attack=20:"
                        "release=300:makeup=1.0[d]".format(den),
                        "-map", "[d]", "-t", "30", ducked_wav],
                       check=True, capture_output=True, text=True)
        vdur = 30.0
        try:
            vdur = min(30.0, float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", a.voice], capture_output=True, text=True).stdout.strip()))
        except Exception:
            pass
        depth, n_win = measure_duck_depth(a.voice, ducked_wav, ref_wav, vdur)
        mode = "sidechain_duck"
    else:
        fc = "[0:a]{}loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.3[out]".format(den)
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.voice,
               "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "2", a.out]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        depth, n_win = 0.0, 0
        mode = "voice_only"

    jdump({"mode": mode, "music": a.music, "target": "I=-16 TP=-1.5 LRA=11",
           "denoise": a.denoise, "duck_depth_db": depth, "duck_windows": n_win,
           "out": a.out}, f"{a.reports}/audio_mix_report.json")
    record_stage(a.reports, "07-audio-mix", "success", t0=t0,
                 bottleneck="none (single-pass ffmpeg)",
                 optimization_applied="sidechaincompress diagnostics pass",
                 optimization_result=f"duck_depth={depth}dB over {n_win} windows")
    print(f"mixed ok mode={mode} duck_depth={depth}dB windows={n_win}")


if __name__ == "__main__":
    main()
