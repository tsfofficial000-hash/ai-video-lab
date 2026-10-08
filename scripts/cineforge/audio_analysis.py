#!/usr/bin/env python3
"""Stage 3: audio analysis -> reports/audio_analysis.json (loudness, silences, noise floor)."""
import argparse
import json
import re
import subprocess

from utils import jdump, record_stage, jload


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="wav or source video")
    ap.add_argument("--reports", default="reports")
    a = ap.parse_args()

    t0 = __import__("time").time()
    import utils
    utils.record_stage._t0_iso = utils.now_iso()

    volumedetect = run(["ffmpeg", "-hide_banner", "-i", a.audio, "-af", "volumedetect", "-f", "null", "-"])
    silencedetect = run(["ffmpeg", "-hide_banner", "-i", a.audio, "-af",
                         "silencedetect=noise=-35dB:d=0.6", "-f", "null", "-"])
    loudnorm_scan = run(["ffmpeg", "-hide_banner", "-i", a.audio, "-af",
                         "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])

    def grab(pat, text, cast=float):
        m = re.search(pat, text)
        return cast(m.group(1)) if m else None

    silences = re.findall(
        r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", silencedetect)
    jn = re.search(r"\{[\s\S]*?\}", loudnorm_scan)
    loudnorm = json.loads(jn.group(0)) if jn else {}

    out = {
        "mean_volume_db": grab(r"mean_volume: ([-\d.]+) dB", volumedetect),
        "max_volume_db": grab(r"max_volume: ([-\d.]+) dB", volumedetect),
        "noise_floor_db": grab(r"histogram_[\d+a-z]*db: (\d+)", volumedetect, int) is not None and None or
                          grab(r"min_volume: ([-\d.]+) dB", volumedetect),
        "silence_regions": [{"start": float(s), "end": float(e), "dur": float(d)} for s, e, d in silences],
        "silence_ratio": round(sum(float(d) for _, _, d in silences) / max(
            grab(r"Duration: ([\d.]+)", volumedetect, float) or 1e9, 1e-9), 3) if silences else 0.0,
        "loudnorm_measured": loudnorm,
        "speech_heavy": len(silences) > 3,
        "music_heavy": len(silences) <= 2 and (grab(r"mean_volume: ([-\d.]+) dB", volumedetect) or -99) > -32,
    }
    jdump(out, f"{a.reports}/audio_analysis.json")
    record_stage(a.reports, "03-audio-analysis", "success", t0=t0)
    print(json.dumps({k: out[k] for k in ("mean_volume_db", "max_volume_db", "speech_heavy", "music_heavy")}))


if __name__ == "__main__":
    main()
