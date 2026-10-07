#!/usr/bin/env python3
"""Transcribe an audio/video file to SRT using faster-whisper (CPU, int8).

Usage: make_srt.py <input media> <output .srt>
Emits [METRIC] lines for CI log parsing.
"""
import os
import resource
import sys
import time


def fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    model_name = os.environ.get("WHISPER_MODEL", "small")
    t0 = time.time()
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    load_s = time.time() - t0

    t1 = time.time()
    segments, info = model.transcribe(
        src, language="en", vad_filter=True, beam_size=1
    )
    cues = [(seg.start, seg.end, seg.text.strip()) for seg in segments]
    trans_s = time.time() - t1

    with open(dst, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(cues, 1):
            f.write(f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{txt}\n\n")

    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"[METRIC] whisper_model={model_name}")
    print(f"[METRIC] whisper_model_load_seconds={load_s:.1f}")
    print(f"[METRIC] whisper_transcribe_seconds={trans_s:.1f}")
    print(f"[METRIC] whisper_audio_seconds={info.duration:.1f}")
    print(f"[METRIC] whisper_speedup_realtime={info.duration / trans_s if trans_s > 0 else 0:.2f}x")
    print(f"[METRIC] whisper_cues={len(cues)}")
    print(f"[METRIC] whisper_peak_rss_mb={rss_mb:.0f}")
    print(f"[SRT-WRITTEN] {dst} ({len(cues)} cues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
