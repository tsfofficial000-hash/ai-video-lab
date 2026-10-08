# ITERATIONS.md — CineForge v2 gate-run loop log

Each entry: hypothesis / change / gate deltas / runtime delta.

## Iteration log (99-full-pipeline dispatches, Phase 2)

| # | Run | Hypothesis → change | Gate delta | Runtime |
|---|-----|---------------------|------------|---------|
| 1 | 37768321060 | Baseline v2 after D1-D7 fixes → dispatch | stage7 RED: mix crash (`Invalid stream specifier: voice`) | — |
| 2 | 37769509104 | Suspect mid-run push cancel → re-dispatch clean | stage6 CANCELLED in setup (12-min silent pip stall) | — |
| 3 | 37771945975 | Suspicion: capture_output hid ffmpeg stderr → visible errors + amix normalize→explicit gain | stage7 RED: `Invalid stream specifier: voice` (REAL — runner ffmpeg 6.1.1) | — |
| — | 97 probe 1 | Matrix A-E on runner ffmpeg 6.1.1 | **A FAIL / B PASS** — the `[voice]` label itself is rejected on 6.1.1; direct `[0:a]`-as-key passes | 2 min |
| 4 | (fix) | Rename labels voice/mmain → bed/duck (python patch; Edit tool strips `[m` sequences) | probes 7/7 green | — |
| 5 | 37775227883 | Labels fixed → dispatch | stage7 hang 12.5 min in pip (silent), job timeout | — |
| — | (fix) | setup-cf: pip/apt timeout+retry, unquiet | — | — |
| 6 | 37780436434 | Retry logic in → dispatch | stage5 RED: apt archive flake (2×150s timeouts) → apt made conditional (ffmpeg preinstalled) | — |
| 7 | 37783420025 | apt conditional → dispatch | stages 0-9 GREEN; stage10 RED: mux `-shortest` truncated 21.9s→1.6s (ffmpeg6 copy+shortest) + QC int-format crash + captions makedirs | — |
| 8 | (fix) | mux `-t` explicit + truncation guard | — | — |
| 9 | 37792749234 | → dispatch | stage7 RED: music.mp3 headerless (unseeded anoisesrc → misprobed container) → `[1:a]` no match | — |
| 10 | (fix) | Music container self-heal (forced mp3 demuxer) at fetch_music + audio_mix validation | — | — |
| 11 | 37794723399 | → dispatch | stages 0-9 GREEN; stage10: **G1 GREEN (0 black!)**, G2 RED median=44 (floor 45) — gate ACTIVE: 50/87 candidates dropped | — |
| 12 | (fix) | luma min_y 30→36 | — | — |
| 13 | 37797520826 | → dispatch | stages 0-10 GREEN!; stage11 RED: `import os` missing in aesthetic heredoc | ~25 min |
| 14 | (fix) | os import | — | — |
| — | 97 probe 2 | Real 17-seg repro on runner: segs healthy (19 video pkts, 0.66s audio) but master17 = container 10.5s with **37 video packets (1.23s)** — xfade chain starved after 2 segs | root cause: `-shortest` in segment encode + AAC priming → video streams 0.633s vs container 0.66s; offsets used container duration | 5 min |
| 15 | 37808676481 | `-shortest` removed + assemble offsets from VIDEO stream duration | stages 0-9 GREEN; stage10: **G2 GREEN median=94**, G1 RED: outro fadeblack 0.4s + global fade-out stacked = 0.5s black = 5.1% > 2% budget | ~24 min |
| 16 | (fix) | fadeblack scaled to runtime (min(0.4, 2%·total)) + no second fade-out when outro is fadeblack | — | — |
| 17 | 37811634227 | → dispatch | pending | — |

## Defect classes discovered beyond D1-D7 (all fixed, all with runner evidence)

1. runner ffmpeg 6.1.1 rejects `[voice]` as a filtergraph label (parses as stream specifier)
2. GH-hosted runners: silent 12-min pip hangs (cache contention) — needs timeout+retry
3. apt archive flakes — apt is unnecessary (ffmpeg preinstalled)
4. `-shortest` + `-c:a aac` silently drops the last video frame(s) of short segments
5. xfade offsets must come from the VIDEO stream duration, not the container
6. anamorphic sources break `scale=-2:'min(480,ih)'` (853x480 odd width → 0-byte proxy)
7. unseeded `anoisesrc` + mp3 muxing can yield headerless containers — verify + self-heal
8. `loudnorm`/video streams with `color_range=unknown` break mjpeg extraction (`-strict unofficial`)
9. Edit-tool input path strips `[m` sequences (ANSI-reset lookalike) — patch via python/chr(91)
10. v4 artifacts are run-scoped — solo stage dispatches cannot download prior-run artifacts
