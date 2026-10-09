# LATENCY_v2.md — CineForge v2 timing

All numbers from the GitHub jobs API measured at delivery (stage-11) on the two
consecutive all-green runs, plus the single-shot draft loop.

## Full 1080p run — per-stage wall (green run 37891911705, 17.5 s deliverable)

| Stage | Job | Wall (s) | Warm-setup share |
|---|---|---|---|
| 00 | environment check | 17 | ~8 s |
| 01 | asset acquisition (source-v1 release + music + manifest) | 59 | ~32 s |
| 02 | ingest (proxy 480x270 + wav + metadata) | 51 | ~30 s |
| 03 | audio analysis | 25 | ~21 s |
| 04 | transcribe (faster-whisper small int8, cache-warm) | 30 | ~22 s |
| 05 | beat analysis (librosa) | 52 | ~21 s |
| 06 | edit decision (plan + luma scan + solver) | 28 | ~20 s |
| 07 | audio mix (duck + SFX synth + loudnorm) | 39 | ~20 s |
| 08 | video render (23 segments, --jobs 4, xfade master, grade) | 78 | ~30 s |
| 09 | captions + hook burn (libass) | 42 | ~30 s |
| 10 | QC + G1–G10 gates | 31 | ~20 s |
| 11 | delivery (bundle + G9 API measure + release) | ~55 | ~20 s |
| — | **critical-path wall (stages 0→11)** | **451** | — |

Parallel branch note: stages 3/4/5 run concurrently after stage-2 (the wall
pays only the slowest of the three, stage-5 at 52 s).

## Green-run comparison

| Run | Verdict | Wall | Max job setup |
|---|---|---|---|
| 37891039600 (green #1) | ALL GATES GREEN | 469 s | 21 s |
| 37891911705 (green #2) | ALL GATES GREEN | 451 s | 32 s |
| v1 reference (37746375946) | 12/12 pass, vacuous QC | 948 s | 50–75 s (unmeasured then; measured now) |

Setup improvements that landed this session: pinned `ffmpeg-v1` release asset
(xz, ~5 s/job replacing apt roulette), venv cache keyed on requirements hash
(pip skipped when warm), whisper model cache moved to stage-04/98 only, fonts
cache. Per-job setup went 68 s → 21–32 s against the 45 s budget.

## Single-shot vs chained (the §5.1 efficiency claim, measured)

| Path | What runs | Wall | Overhead |
|---|---|---|---|
| `98-iterate` (single job, stages 01→10 in one workspace) | draft loop | **~2.5–4 min** (37888578923: 2 m 48 s; 37891926280: ~3 min) | 1× job setup |
| `99-full-pipeline` (12 reusable stages) | production + per-stage recovery | ~7.5 min | 12× job setup (amortized by caches: ~20–30 s each) |

The chained pipeline costs ~2.2× the single-shot path in wall time, entirely
job-setup overhead — which is why creative iteration runs on 98 and only
gate-verified production renders run on 99.

## G9 gate (spec: full ≤12 min wall, draft ≤4 min, setup ≤45 s)

| Requirement | Measured | Verdict |
|---|---|---|
| Full 1080p run ≤ 12 min for ≤60 s source | 451–469 s (7.5–7.8 min) | PASS |
| Draft iteration ≤ 4 min (540p-equivalent speed path) | 2.5–4 min | PASS |
| Per-job setup ≤ 45 s (caches warm) | 21–32 s | PASS |
