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
| 17 | 37811634227 | → dispatch | stage1 RED: setup-cf flake (apt class) → apt already conditional; superseded by #37 re-dispatch | — |
| 18 | 37814402550 (#37) | clean re-dispatch after 2287af3 | **12/12 stages SUCCESS**, wall 13m18s; but `gates_report.json` RED on G2/G3/G7/G10 — masked by `\|\| true`: gates.py scanned nonexistent `out/final.mp4` (artifact nests under `final/`), and selection_audit / audio_mix_report / media_manifest were never downloaded into stage-10 → plumbing, not video, defect | 13m18s |
| 19 | 37818948356 (98 #2) | single-shot iterate on HEAD 1dce20e after 98 #1 failed at stage-09 burn (dryrun gate consumed render) | SUCCESS 2m31s, 1080x1920 draft, 10.03s / 17 segs / 1.72 cps; QC 12/12; captions still n/a (style had `captions: null`) | 2m31s |
| 20 | (fix round) | gates.py v2 (glob report discovery incl. final/, real video path, own 2fps luma scan, G6 measured `output_i` via ebur128 in audio_mix.py, G9 latency-aware) + stage-10 strict gates + stage-11 G9 from jobs API + captions ON per style (bold_highlight) + mood plumbed to edit_plan + setup-cf venv cache (setup ≤45s target) | local fixture of #37 artifacts: **ALL GREEN exit 0**; probes 7/7 | — |

| 21 | 37875877209 | inline -filter_complex (static ffmpeg 7.0.2 misparses -filter_complex_script); fps_mode; scarcity solver (9.88s -> capacity-max plan, consistent spans, whole-span luma gate) | dispatched | — |

| 21 | 37875877209 | dryrun still "Filter not found" with inline graph -> probe v3 verdict: johnvansickle static 7.0.2 has NO drawtext (probe v2's all-0 rc was `$?` after a pipe - tail's exit code). Fix: capability-driven setup (apt 6.1.1 has drawtext; BtbN GPL static fallback) | stages 0-9 GREEN (apt ffmpeg 6.1.1); stage10 RED: captions_burned + duration 9.83s vs plan 17.02s | ~14 min |
| 22 | (fix) | renderer law out = src/speed vs plan out = src*speed mismatch: scarcity segs overstated out_dur. Contract fixed: explicit src_dur=0.73, speed=src/out=0.772 (subtle slow-mo), src/speed == out_dur exactly. captions.py burned SOURCE times as OUTPUT times (cues 11.9-20.3s in a 9.83s video): transcript now projected through plan segments into output time, out-of-coverage pieces dropped | local: plan 23 segs / 17.80s / cps 1.29 / overlap 0.266; probes 7/7 | - |
| 23 | 37879732737 | consistency dispatch on 24fcd05 | dispatched | - |

| 23 | 37879732737 | G6 search gap at delivery (stage-11 lacked mix artifact) + honest setup pattern | G9 wall=663s PASS but maxSetup=68s RED (honest measurement caught the real cost) | ~13 min |
| 24 | (perf) | ffmpeg pinned as release asset (xz 50MB, BtbN master w/ drawtext+libass), whisper cache to stage-04/98 only, venv cache | green 37885213747: **12/12 stages, ALL GATES G1-G10 GREEN**, wall 383s, setup 23s | 6.4 min |
| 25 | 37886393173 (98 draft) | creative r1 review: hook clipped both edges, desert-tail sag, caption double-render -> hook width-fit + motion interleave + piece merge; ALSO found 98 stage-09 `../` path bug (drafts burned nothing, ever) | draft 37888578923 first burnt draft, all axes >=8 | 2m48s |
| 26 | 37889110062 / 37890113995 | caption pixel samples: fadeblack-window clamp + hook-band padding for sparse speech; dialogue tail bias (span overlap) | dialogue at out 0.8s; samples 3-point measurable | - |
| 27 | 37891039600 + 37891911705 | **Phase 3 complete: two consecutive ALL-GREEN full runs with all creative fixes** | wall 469/451s, setup 21/32s | 7.8/7.5 min |
| 28 | 37891926280 / 37891928188 / 37891930331 | Phase 4 style sweep (sad/cinematic/motivational drafts): 3 grades, 3 bands, 3 caption styles, SATAVG 11.2/22.7/21.8 - zero config bleed | all 3 drafts green | ~3 min each |

## Defect classesscovered beyond D1-D7 (all fixed, all with runner evidence)

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
11. gates.py scanned `out/final.mp4` while artifacts nest under `final/` — same family as D2 (report paths assumed, never resolved); fixed by glob discovery + strict assert
12. masked red: `|| true` on the gates step certified a not-green run as success — gates now `set -e`-strict at stage-10 and assert at stage-11

| 29 | 38042389349 | v2.1 first full run (99-chain, source-v1, beat_montage/cinematic/30): E-fixes proven on real footage - G4 bar_fraction=0.000 (v2 audit: 20/23 barred windows), G6 via=archive_cc (real CC0 music, duck 13.1dB), G5 hookInCands+wordComplete, 13/13 segs carry active_crop | stage-10 RED: G7 cps=1.14 < band floor 1.2; G11 11.2s/30s (honest note fired) | 9.5 min |
| 30 | (fix, rehearsed offline on run-1 artifacts) | root causes: (1) scarcity capacity equation assumed (n-1)*0.18 all-fade transitions but the E6 mix subtracts ~0.05s pseudo-cuts -> solved out_dur overshot; (2) equation used raw n_cap=35 while the scene-diversity cap allows only 7 clusters x 2 = 14 (source is long-take: [32.1s-end] is one 19.4s take holding 18 candidates, capped to 2 - the 30s request is GENUINELY impossible under G3 no-reuse + G7 diversity + G2 luma). Fix: n_eff (scene-cap-effective capacity) + mix-aware transition sum T in the equation; impossibility note carries the cluster math | local rehearsal on run-1 beats/luma/cuts: cps 1.28 (in band), clusters<=2, 13/13 segs cropped, note states max ~10.1s with capacity math | - |
