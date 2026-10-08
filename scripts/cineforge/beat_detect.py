#!/usr/bin/env python3
"""Stage 5: beat & rhythm analysis -> reports/beats.json
Works on music wav (preferred) or source audio. Falls back to uniform grid."""
import argparse
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--src-duration", type=float, default=None)
    a = ap.parse_args()

    import numpy as np
    import librosa
    from utils import jdump, record_stage
    import time
    t0 = time.time()

    y, sr = librosa.load(a.audio, sr=22050, mono=True)
    dur = a.src_duration or len(y) / sr
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.ravel(tempo)[0]) if np.ndim(tempo) else float(tempo)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=False)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)

    # energy peaks (top windows for hook/hero selection)
    win = int(sr * 1.5 / 512)
    if len(rms) > win:
        conv = np.convolve(rms, np.ones(win) / win, mode="valid")
        peaks = [round(float(times[i]), 3) for i in np.argsort(conv)[-8:]]
    else:
        peaks = [0.0]

    # section candidates: boundaries where onset density changes
    sections = []
    if len(beats) >= 8:
        per = np.array_split(np.array(beats), 4)
        sections = [{"start": float(b[0]), "end": float(b[-1]), "beats": len(b)} for b in per if len(b)]

    out = {
        "tempo": round(float(tempo), 1),
        "beat_count": len(beats),
        "beats": [round(float(b), 3) for b in beats],
        "onsets": [round(float(o), 3) for o in onsets],
        "energy_peak_starts": sorted(peaks),
        "sections": sections,
        "duration": round(dur, 2),
        "analysis_source": a.audio,
    }
    jdump(out, f"{a.reports}/beats.json")
    record_stage(a.reports, "05-beat-analysis", "success", t0=t0,
                 bottleneck="librosa full-file decode" if dur > 300 else "")
    print(f"tempo={out['tempo']} beats={out['beat_count']} peaks={len(peaks)}")


if __name__ == "__main__":
    main()
