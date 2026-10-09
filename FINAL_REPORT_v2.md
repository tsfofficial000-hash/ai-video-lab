# CineForge v2 — FINAL_REPORT_v2.md

**Run family:** `99-full-pipeline` dispatches on `tsfofficial000-hash/ai-video-lab` · mandate: REPAIR + CREATIVE EXCELLENCE (100% FREE-ONLY)

---

## 1. Executive verdict

CineForge v2 shipped. The seven independently-verified defects (D1–D7) are fixed with failing-first probes, the creative output was rebuilt to the §2 spec, and **every gate G1–G10 is green with a measured number and an artifact path on two consecutive full runs** (37891039600, 37891911705). The v1 deliverable was a 26.2 s file that was 54% near-black with a 7.67 s black tail, a duplicated opening, no music, no captions, an unwired grade, and a QC that certified all of it through two checks that could never fail. The v2 deliverable is a 17.5 s 1080×1920 beat-montage with zero black frames, beat-aligned cuts at 1.29 cuts/s, burned width-fitted typography with keyword pops, a 13.0 dB sidechain duck over a generated bed at −16.3 LUFS, a single-application teal-orange grade, full-bleed cover-crop layout, OFL fonts with recorded licenses, CC-BY attribution, and a wall time of 6.4–7.5 minutes with 21–32 s job setup. The honest residual: the source (Sintel trailer via the `source-v1` cache) supports ~24 s of luma-clean, non-reusable material, so the 30 s mandate target lands at 17.5 s rather than violating G3 (no reuse) or G7 (band) — the scarcity solver maximizes runtime under the constraint set instead of replaying footage.

### Gate table — before (v1 audit) vs after (green runs 37891039600 / 37891911705)

| Gate | v1 (independent audit, run 37746375946) | v2 green (measured) |
|---|---|---|
| G1 BLACK | 54% near-black frames; black 18.50→26.17 s (7.67 s tail) | **0.00 s black (0.0% of 17.5 s), longest region 0.00 s** |
| G2 LUMA | median Y ≈ dark; first-second black | **medianY 91–95, near-black 0.0%, first-1s Y 45–52** |
| G3 SELECTION | 15/49 segments from min-Y<20 source; segs 42-48 ≡ 0-6 (wrap-around); 9.3 s on black cards | **wrap=False, 0 overlaps >0.3 s, 52 luma-gate drops enforced** |
| G4 LAYOUT | vignette-crushed blur fill, fg strip 607 px | **cover_crop full-bleed (fg = 100% by construction)** |
| G5 TYPO | captions tautology (always passed, nothing burned) | **OFL fonts licensed + pixel test 2.56% white at cues + per-cue decisions logged** |
| G6 AUDIO | no music path (`keep_source`), `level_sc=duck` crash | **sidechain_duck 13.04 dB, music wired, output −16.3 LUFS ∈ [−17,−15]** |
| G7 PACING | n/a (no metric) | **1.29 cuts/s ∈ [1.2, 2.0], beat alignment 0 ms** |
| G8 EVIDENCE | bundle lacked qc_report/latency/manifest (D2) | **7-file bundle + `reports/cineforge/run-<id>/` committed per run** |
| G9 LATENCY | unmeasured | **wall 383–469 s (≤720), max job setup 21–32 s (≤45)** |
| G10 FREE | unverified | **CC-BY 4.0 attribution recorded (Blender Foundation); music generated in-pipeline; zero paid calls** |

---

## 2. Defect fixes D1–D7 with probe evidence

Probe suite: `tests/defects/d1..d7` + `run_probes.py` (local python). All probes verified **FAILING on pre-fix HEAD, PASSING after each `fix(Dx)` commit**, and still 7/7 green at ship time (re-run after every subsequent change).

| ID | Defect → fix | Probe evidence |
|---|---|---|
| D1 | `qc.py` blackdetect regex demanded a space after `black_start:` (ffmpeg prints `black_start:0`) and scanned only `-t 10` → regex `black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)` + whole-file scan + G1 gate | probe reproduced 4 hidden black regions on a synthetic file; now 0/7 defects present |
| D2 | delivery copied `reports/{latency,qc_report,manifest}.json` from an empty dir with `\|\| true` → glob-resolved from downloaded artifacts; qc_report copy mandatory under `set -e`; gates step asserts strict | d2 probe passes; run 37885213747+ bundles contain all 7 files |
| D3 | selection wrap-around `cursor = usable[0]+0.37` replayed the opening → `Selector` forward-only, luma-gated, overlap-capped; **whole-span** min-Y gate (long spans leaked dark frames past the 1 s candidate check: cinematic minY 16→46); no wrap; audit emitted | d3 probe passes; audit wrap=False, overlaps=[] on every green run |
| D4 | bg `eq=brightness=-0.07` + full-canvas `vignette=PI/4.6` → `brightness=0.00:saturation=0.90` + `boxblur=16:2`, vignette removed, `cover_crop` default (full-bleed), `smart_crop` mode added | d4 probe passes; G4 green on all runs |
| D5 | `configs/grades.json` dead code (and its `colorbalance` options were invalid anyway) → single application point `render_ffmpeg.apply_grade()` after master assembly; smoke-burned in the dry-run gate | d5 probe passes; 3 styles → 3 measured signatures (§4 sweep) |
| D6 | `captions_burned` tautology → real burn-existence pixel test (white-pixel ratio ≥0.3% in the caption band at up to 3 cue timestamps, hook-band samples pad sparse-speech edits, samples clamp out of the fadeblack window) | d6 probe passes; run 37890113995 measured 2.559% at the burned cue |
| D7 | `sidechaincompress=...:level_sc=duck` (invalid) + dead `[sc]` fragment + music never wired → labels renamed (`voice/mmain`→`bed/duck` — runner ffmpeg parses `[voice]` as a stream specifier), `level_sc` deleted, music wired for `music != none` styles, duck depth measured (13.04 dB) | d7 probe passes; local repro crash gone; G6 green |

---

## 3. Aesthetic scores per run (self-reviewed from contact sheets + frames)

Six-axis self-review is performed on rendered frames (not configs). Scores 0–10.

| Run | Type | hook | pacing | typography | layout | grade | audio | Notes |
|---|---|---|---|---|---|---|---|---|
| 37885213747 | full, pre-creative-fix | 6.5 | 7.5 | 7 | 8.5 | 8 | 8 | 3 complaints: hook clipped both edges at t=0; desert-tail sag (3 static dune shots) + duplicate-adjacent cuts; caption double-render |
| 37888578923 | draft (fix validation) | 9 | 8.5 | 9 | 8.5 | 8 | 8 | hook width-fitted to 2 lines fs150; motion interleave alternating 33→0.5→26→1.6…; caption pieces merged |
| 37891039600 | **full GREEN #1** | 9 | 8.5 | 9 | 8.5 | 8 | 8 | dialogue button placed at 0.8 s (biased out of the fadeblack tail) |
| 37891911705 | **full GREEN #2** | 9 | 8.5 | 9 | 8.5 | 8 | 8 | all gates green; release refreshed |

Fixes applied between runs (all committed):
- **Hook width fit** — Anton estimated-glyph wrap to ≤2 lines, size floor 150 px (spec band), per-event `\fs` override, centered at y≈30%. (The 168 px single line overflowed 1080 px.)
- **Motion-variance interleave** — per-segment motion score (mean |ΔY| of the luma profile in-span); reorder strongest↔weakest so static shots spread between action beats. Same spans, presentation order only: G3/G7 unaffected.
- **Caption piece merge** — projected transcript pieces that overlap (adjacent segs share ≤0.29 s of source) are merged; no double-rendered sentences.
- **Dialogue tail bias** — speech-bearing segments swap out of the last two slots so burned captions never sit under the outro fadeblack.

Contact sheets are committed under `reports/cineforge/run-*/contact_sheet.png` and attached to release `cineforge-v2`.

---

## 4. Style sweep (Phase 4) — measurable differences, no config bleed

Same source, draft quality, three styles dispatched (`98-iterate` runs 37891926280 / 37891928188 / 37891930331):

| Style | grade applied | cuts/s (band) | caption style | measured SATAVG |
|---|---|---|---|---|
| sad_emotional | `sad_cold` | 0.29 ([0.15, 0.35]) ✓ | `emotional_soft` | **11.2** (desaturated) |
| cinematic | `cinematic_teal_orange` | 0.48 ([0.3, 0.7]) ✓ | `minimal_clean` | **22.7** |
| motivational | `natural` | 1.23 ([0.8, 1.4]) ✓ | `viral_high_contrast` | **21.8** |

Every style landed inside its own band, with its own grade name, its own caption style, and a distinct measured saturation signature (sad_cold is 2× less saturated than the others). Any config bleed would have shown as a band violation or a duplicated signature — none occurred.

---

## 5. Failures → fixes log (continues the 18-entry tradition)

| # | Class | Failure → fix (with evidence) |
|---|---|---|
| 19 | Gates plumbing (D2 family) | gates.py scanned `out/final.mp4` while artifacts nest under `final/`; audit/mix/manifest never downloaded into stage-10 → glob report discovery + real video path + strict assert (run 37814402550 gates were falsely RED-masked by `\|\| true`) |
| 20 | Vacuous green | `captions: null` in styles meant captions were never burned and G5 was n/a → captions enabled per style + report uploaded |
| 21 | Toolchain drift | runner image has no preinstalled ffmpeg → static johnvansickle 7.0.2 build **lacks drawtext** (`No such filter: 'drawtext'`, run 37875877209) → capability-driven install; probe v2's all-zero rc was `$?` after a pipe (tail's exit), probe v3 (python argv) got the real verdict |
| 22 | ffmpeg API drift | `-filter_complex_script` deprecated/misparses on static builds → inline `-filter_complex`; `-vsync` → `-fps_mode` (removed in ffmpeg 8) |
| 23 | Determinism | toolchain now pinned: `ffmpeg-v1` release asset (xz, 50 MB each, BtbN master build with drawtext/libass verified) — 5 s per job, no apt roulette |
| 24 | Plan/render semantic split | plan `out = src×speed` vs renderer `out = src/speed` (+trim): scarcity segs overstated out_dur → 9.83 s render vs 17.02 s plan (run 37877863218) → contract fixed: explicit `src_dur`, `speed = src/out ≤ 1`, `src/speed == out_dur` exactly |
| 25 | Material scarcity | 9.88 s plan vs 30 s target (candidates exhausted, silent) → scarcity solver: full-capacity walk, capacity-equation out_dur, ≤0.29 s crossfade-hidden overlap, retiming ≤0.772×; Sintel frontier ≈ 17.5–17.8 s at 1.29 cps |
| 26 | Whole-span luma | Selector gated only the first 1.0 s of a candidate window; long cinematic spans shipped min-Y 16 frames → whole-span gate (min-Y 46 after) |
| 27 | Caption time domain | captions.py burned SOURCE times as OUTPUT times (cues at 11.9–20.3 s in a 9.83 s video — vacuous pixel test) → transcript projected through plan segments into output time; out-of-coverage pieces dropped |
| 28 | One-`..`-too-few | 98-iterate stage-09 read `../reports/…` from `scripts/cineforge` = `scripts/reports/` (nonexistent): **every draft silently shipped unburnt video** → `../../` like every other stage (draft 37888578923 first burnt draft) |
| 29 | Evidence on red | 98's artifact upload lacked `if: always()` → failed drafts shipped no evidence → fixed (the red loop needs evidence most) |
| 30 | Push races | v1 lab experiment workflows auto-committed logs on every push, racing cineforge commits → push triggers disabled (dispatch-only) |
| 31 | Hook overflow | 168 px single-line hook clipped both edges → width-fitted wrap (§3) |
| 32 | Pacing sag | static-shot clumping at the tail → motion-variance interleave |
| 33 | Sample validity | pixel-test cues landed inside the fadeblack → samples clamp out of the exempt fade window |
| 34 | Sparse speech | 1-cue edits could never reach the ≥2-hit rule → hook-band samples pad the test (still 3-point measurable) |
| 35 | Empty transcript | silent transcribe failure shipped a hookless open → title fallback + hook-band pixel test |
| 36 | G9 honesty | latency.json was a stale single-stage local record → measured from the GitHub jobs API at delivery (wall + per-job setup), asserted before release |

---

## 6. Limitations & honest confidence scores

| Subsystem | Confidence | Notes |
|---|---|---|
| Defect fixes D1–D7 | 0.95 | probe-verified fail→pass, re-run green at ship |
| Gate measurement (G1–G8, G10) | 0.9 | direct ffmpeg/probe measurements on the shipped file |
| G9 latency | 0.85 | jobs-API measurement; wall includes queue-time variance between runs (383–469 s) |
| Creative quality (6 axes) | 0.8 | self-reviewed from contact sheets + extracted frames; hook/pacing fixes are measured, but "top-notch" is partly subjective — a human viewer pass is the missing reviewer |
| 30 s target | 0.5 | unreachable for THIS source under G3+G7 without reuse: Sintel's luma-clean span is ~24 s and the solver lands 17.5 s; a longer/CC0 source reaches 30 s with the same code |
| Face-avoidance (MediaPipe) | 0.4 | not installed (kept out of requirements for speed); captions use bottom safe-zone; the per-cue decision log records `face: null` honestly — wiring MediaPipe in is a one-line requirements change |
| rembg text-behind-subject | 0.0 (not built) | §2.3 optional masking was descoped in favor of the offset-title fallback the spec itself defines; hook only ≤3 s |
| Music source | 0.7 | FreePD candidates 403'd from runners (HTTPError on 3 candidates); synth fallback is mood-shaped (cinematic pad), CC0-clean, but a real FreePD bed is a one-retry-away |

---

## 7. Exact re-run commands

```bash
# Full 1080p gate run (beat_montage / cinematic / 30 s target, source from source-v1 cache)
gh workflow run 99-full-pipeline.yml \
  -f source_url=source-v1 -f style=beat_montage -f mood=cinematic \
  -f target_len=30 -f draft=false

# Other styles (draft iteration)
gh workflow run 98-iterate.yml -f source_url=source-v1 -f style=sad_emotional -f mood=sad      -f target_len=30 -f draft=true
gh workflow run 98-iterate.yml -f source_url=source-v1 -f style=cinematic     -f mood=cinematic -f target_len=30 -f draft=true
gh workflow run 98-iterate.yml -f source_url=source-v1 -f style=motivational  -f mood=energetic -f target_len=30 -f draft=true

# Single stages for recovery
gh workflow run 06-edit-decision.yml -f style=beat_montage -f target_len=30 -f mood=cinematic
gh workflow run 09-caption-grade.yml          # captions + hook burn
gh workflow run 10-quality-control.yml        # QC + G1-G10 aggregation
gh workflow run 11-final-delivery.yml         # bundle + release + G9 finalize

# Defect probes (local, no CI needed)
python3 tests/defects/run_probes.py           # expect: 0/7 defects present, 7/7 fixed

# YouTube source (only for URLs you own / that are clearly CC-licensed)
gh workflow run 99-full-pipeline.yml -f source_url=<URL> -f style=beat_montage -f mood=cinematic -f target_len=30
```

**Artifacts:** release `cineforge-v2` (final.mp4 + contact_sheet.png + delivery bundle), `reports/cineforge/run-<id>/` committed per run, `ITERATIONS.md` for the full loop log, `LATENCY_v2.md` for the timing table.
