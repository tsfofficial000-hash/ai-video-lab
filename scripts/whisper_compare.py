#!/usr/bin/env python3
"""TEST D — Whisper ASR comparison: faster-whisper (small/base) vs openai-whisper (base.en).

Transcribes the SAME mixed audio, scores each engine against the known
reference narration text, writes SRTs, and burns the best SRT via FFmpeg.

Usage: whisper_compare.py <audio> <ref_text_file> <outdir>
"""
import difflib
import json
import os
import resource
import sys
import time


def fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def metric(k, v):
    line = f"[METRIC] {k}={v}"
    print(line, flush=True)
    open(os.path.join(OUTDIR, "metrics.txt"), "a").write(line + "\n")


def norm(t: str) -> str:
    return " ".join("".join(c.lower() for c in t if c.isalnum() or c == " ").split())


def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(cues, 1):
            f.write(f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{txt}\n\n")


AUDIO, REFFILE, OUTDIR = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUTDIR, exist_ok=True)
ref_text = open(REFFILE, encoding="utf-8").read()
results = {}

# ---------------- faster-whisper ----------------
t0 = time.time()
from faster_whisper import WhisperModel

fw_install = time.time() - t0
metric("fw_import_seconds", round(fw_install, 1))

for model_name in ("small", "base"):
    t1 = time.time()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    load_s = time.time() - t1
    t2 = time.time()
    segments, info = model.transcribe(AUDIO, language="en", vad_filter=True, beam_size=1)
    cues = [(s.start, s.end, s.text.strip()) for s in segments]
    trans_s = time.time() - t2
    hyp = norm(" ".join(c[2] for c in cues))
    score = difflib.SequenceMatcher(None, norm(ref_text), hyp).ratio()
    srt_path = os.path.join(OUTDIR, f"subs_fw_{model_name}.srt")
    write_srt(cues, srt_path)
    key = f"fw_{model_name}"
    results[key] = {
        "engine": "faster-whisper", "model": model_name,
        "model_load_s": round(load_s, 1), "transcribe_s": round(trans_s, 1),
        "audio_s": round(info.duration, 1),
        "rtf": round(info.duration / trans_s, 2) if trans_s > 0 else None,
        "cues": len(cues), "similarity": round(score, 3),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    metric(f"{key}_load_seconds", results[key]["model_load_s"])
    metric(f"{key}_transcribe_seconds", results[key]["transcribe_s"])
    metric(f"{key}_rtf_realtime_factor", results[key]["rtf"])
    metric(f"{key}_similarity", results[key]["similarity"])
    metric(f"{key}_peak_rss_mb", results[key]["peak_rss_mb"])
    del model

# ---------------- openai-whisper ----------------
try:
    t3 = time.time()
    import whisper

    ow_model = whisper.load_model("base.en")
    load_s = time.time() - t3
    t4 = time.time()
    res = ow_model.transcribe(AUDIO, language="en", verbose=False)
    trans_s = time.time() - t4
    cues = [(s["start"], s["end"], s["text"].strip()) for s in res["segments"]]
    hyp = norm(" ".join(c[2] for c in cues))
    score = difflib.SequenceMatcher(None, norm(ref_text), hyp).ratio()
    srt_path = os.path.join(OUTDIR, "subs_ow_base_en.srt")
    write_srt(cues, srt_path)
    results["ow_base_en"] = {
        "engine": "openai-whisper", "model": "base.en",
        "model_load_s": round(load_s, 1), "transcribe_s": round(trans_s, 1),
        "audio_s": round(res.get("duration", 0), 1),
        "rtf": round(res.get("duration", 0) / trans_s, 2) if trans_s > 0 else None,
        "cues": len(cues), "similarity": round(score, 3),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    metric("ow_base_en_load_seconds", results["ow_base_en"]["model_load_s"])
    metric("ow_base_en_transcribe_seconds", results["ow_base_en"]["transcribe_s"])
    metric("ow_base_en_rtf_realtime_factor", results["ow_base_en"]["rtf"])
    metric("ow_base_en_similarity", results["ow_base_en"]["similarity"])
    metric("ow_base_en_peak_rss_mb", results["ow_base_en"]["peak_rss_mb"])
except Exception as e:  # noqa: BLE001
    metric("ow_base_en_error", str(e)[:200].replace(" ", "_"))

# ---------------- also transcribe the CLEAN narration for an upper bound ----
fw_small_clean = None
try:
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe("narration.wav", language="en", vad_filter=True, beam_size=1)
    cues = [(s.start, s.end, s.text.strip()) for s in segments]
    hyp = norm(" ".join(c[2] for c in cues))
    fw_small_clean = difflib.SequenceMatcher(None, norm(ref_text), hyp).ratio()
    metric("fw_small_clean_narration_similarity", round(fw_small_clean, 3))
except Exception as e:  # noqa: BLE001
    metric("fw_small_clean_error", str(e)[:200].replace(" ", "_"))

results["fw_small_clean_narration_similarity"] = fw_small_clean
with open(os.path.join(OUTDIR, "whisper_comparison.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("[DONE-WHISPER-COMPARE]")
