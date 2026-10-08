#!/usr/bin/env python3
"""Stage 4: faster-whisper transcript -> transcript.txt/json + subtitles.srt
Fallback ladder: small int8 -> base int8 -> transcript_empty."""
import argparse
import json
import time

from utils import jdump, record_stage

MODEL = "small"
FALLBACK_MODEL = "base"


def to_srt(segs):
    def ts(t):
        h, m = int(t // 3600), int(t % 3600 // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return "\n".join(
        f"{i+1}\n{ts(s['start'])} --> {ts(s['end'])}\n{s['text'].strip()}\n" for i, s in enumerate(segs))


def transcribe(path, model_size):
    from faster_whisper import WhisperModel
    m = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=4)
    segs, info = m.transcribe(path, vad_filter=True, word_timestamps=False)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 3), "end": round(s.end, 3),
                    "text": s.text.strip(), "confidence": round(float(s.avg_logprob), 3)})
    return out, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="source video/audio")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-seconds", type=float, default=None, help="analyze only first N seconds")
    a = ap.parse_args()

    t0 = time.time()
    used = a.model
    try:
        segs, info = transcribe(a.audio, a.model)
        if len(segs) == 0:
            raise RuntimeError("empty transcript")
    except Exception as e:
        print(f"[transcribe] {a.model} failed ({type(e).__name__}), fallback to {FALLBACK_MODEL}", flush=True)
        used = FALLBACK_MODEL
        segs, info = transcribe(a.audio, FALLBACK_MODEL)

    if a.max_seconds:
        segs = [s for s in segs if s["start"] <= a.max_seconds]

    empty = not segs
    texts = [s["text"] for s in segs if s["text"].strip()]
    jdump({"model": used, "language": info.language if hasattr(info, "language") else None,
           "transcript_empty": empty, "segments": segs,
           "duration_analyzed": segs[-1]["end"] if segs else 0},
          f"{a.reports}/transcript.json")
    open(f"{a.reports}/transcript.txt", "w").write(" ".join(texts))
    open(f"{a.reports}/subtitles.srt", "w").write(to_srt(segs))
    record_stage(a.reports, "04-transcript", "success", t0=t0,
                 optimization_applied=f"model={used} int8",
                 optimization_result=f"{len(segs)} segments")
    print(f"model={used} segments={len(segs)} empty={empty}")


if __name__ == "__main__":
    main()
