#!/usr/bin/env python3
"""Stage 4: faster-whisper transcript -> transcript.txt/json + subtitles.srt
Fallback ladder: small int8 -> base int8 -> transcript_empty.
N4: CF_WHISPER_TIER=tiny gives constrained runners a tiny->base ladder; the
tier and the model actually used are logged to reports/environment.json."""
import argparse
import json
import os
import time

from utils import jdump, record_stage

MODEL = "small"
FALLBACK_MODEL = "base"
LADDERS = {"tiny": ["tiny", "base"], "base": ["base"], "small": ["small", "base"]}


def model_ladder():
    """N4: the transcription ladder for this run (CF_WHISPER_TIER rung)."""
    tier = os.environ.get("CF_WHISPER_TIER") or "small"
    return list(LADDERS.get(tier, LADDERS["small"]))


def log_environment(reports_dir, used_model, extra=None):
    """N4: record the whisper tier + model in reports/environment.json."""
    p = os.path.join(reports_dir, "environment.json")
    env = {}
    if os.path.isfile(p):
        try:
            env = json.load(open(p))
        except Exception:
            env = {}
    env.update({"whisper_model": used_model,
                "whisper_tier": os.environ.get("CF_WHISPER_TIER") or "small",
                "whisper_ladder": model_ladder()})
    env.update(extra or {})
    os.makedirs(reports_dir, exist_ok=True)
    json.dump(env, open(p, "w"), indent=1)
    return env


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
    ladder = model_ladder()
    if a.model and a.model != MODEL:          # explicit --model rung wins first
        ladder = [a.model] + [x for x in ladder if x != a.model]
    used = None
    segs = info = None
    for i, cand in enumerate(ladder):
        try:
            segs, info = transcribe(a.audio, cand)
            if len(segs) == 0:
                raise RuntimeError("empty transcript")
            used = cand
            break
        except Exception as e:
            print(f"[transcribe] {cand} failed ({type(e).__name__})", flush=True)
            if i + 1 < len(ladder):
                print(f"[transcribe] falling back to {ladder[i + 1]}", flush=True)
    if used is None:
        used = ladder[-1]   # keep the report honest even on total failure
    log_environment(a.reports, used)

    if a.max_seconds:
        segs = [s for s in (segs or []) if s["start"] <= a.max_seconds]

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
