# PIPELINE.md — CineForge Pro architecture

Repository: `ai-video-lab` (public — unlimited Actions minutes).
Stack: GitHub Actions render farm + FFmpeg + faster-whisper + librosa + Python. Zero paid APIs, zero GUI, zero SaaS render.

## Stage graph

```
00 env check ─┐
              ▼
01 assets (source ladder + CC0 music)
              ▼
02 ingest/proxy (ffprobe, 480p proxy, wav, contact sheet)
              ▼
   ┌──────────┼────────────┐
03 audio   04 transcript  05 beats     (parallel)
   └──────────┼────────────┘
              ▼
06 edit decision (style-aware EDL + engine timeline)
              ▼
07 audio mix (sidechain duck + loudnorm -16)
              ▼
08 video render (dry-run gate -> segments -> xfade master -> mix mux)
              ▼
09 captions & grade (libass burn, letterbox)
              ▼
10 QC (12 checks + auto-repair)
              ▼
11 delivery (bundle artifact + Release cineforge-v1 + logs commit)
```

Orchestrator: `99-full-pipeline.yml` (reusable-workflow calls, needs-chained).
Each stage is independently dispatchable; artifacts chain stage outputs (unique names `stage-XX-*`, 3-7 day retention).

## Media flow (never committed to git)

media files live only in artifacts: source.mp4, proxy, wav, music, mixed_audio, master, final, captions.ass.

## Latency engineering

- `scripts/cineforge/utils.py:record_stage` writes `reports/latency.json` (per-stage: duration, cores, RAM, retries, bottleneck, optimization).
- pip cache via setup-python (cache: pip).
- dry-run gate in 08 (2-segment micro render) before full render.
- draft path: crf 23/veryfast (~4x faster), final: crf 19/medium.
- transcript fallback small int8 -> base int8; beats fallback uniform grid; music fallback synthesized pad; acquisition ladder per `configs/fallbacks.json`.

## Engine lineage

The montage render core (beat-grid timeline -> segment render with blurred-bg 9:16 composite -> xfade/acrossfade master graph) is the battle-tested path from the montage.yml experiments (see logs/montage/). CineForge wraps it with the full stage chain, captions, mixing, QC and delivery.
