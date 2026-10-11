# CineForge v2.1 — CONTINUATION MANDATE: FINAL REPORT

Shipped at HEAD `3a892a6` (evidence commit `b7e9390`), release
[`cineforge-v2.1`](https://github.com/tsfofficial000-hash/ai-video-lab/releases/tag/cineforge-v2.1),
ship run **38109649950** — **G1–G11 ALL GREEN with measured numbers**, wall
424 s, max job setup 23 s, 18.37 s 1080×1920 deliverable from the `source-v1`
(Sintel) cache. The resume mandate (Phases D2/E/F + audit findings R1–R5) is
closed: the last visual-bug class is dead at the pixel level, real licensed
music ships, target fidelity is an enforced gate with a declared relaxation
ladder, and every gate a report claims is now reproducible from committed
artifacts alone.

> **CORRECTION (v2.2 audit, finding W1).** The claim that v2.1 ships
> "on-screen attribution" was FALSE for the artifact: stage-06 never
> downloaded the stage-01 media manifest, so `plan.music_credit` was `None`
> and **no credit was burned** into the released `cineforge-v2.1` MP4
> (verified on run 38109649950's committed `edit_plan.json`). Repo-side
> license text does not satisfy attribution-with-the-work for a published
> Short. The fix (manifest wiring + `music_credit_on_screen` QC pixel
> verification + G10 attribution clause) ships with release
> **`cineforge-v2.1.1`, the first release that carries the burned credit**.
> The affected lines in this report are annotated inline.

## 1. Gate table — before / after (all values measured, artifact-backed)

| Gate | v2.0 ship (37891911705) | v2.1 pre-crash run 3 (38043976013) | **v2.1 SHIP (38109649950)** |
|---|---|---|---|
| G1 black | 0.00 s / 17.5 s | 0.00 s / 10.0 s | **0.00 s / 18.4 s** |
| G2 luma | medianY=91, nearBlack 0%, first1sY=52 | medianY=93, first1sY=54 | **medianY=89, first1sY=58 (n=37)** |
| G3 selection | wrap=False, overlaps 0, 23 selected | wrap=False, 13 selected | **wrap=False, 9 selected (full effective capacity)** |
| G4 layout | by-construction (`fg=full-bleed` — never looked at pixels) | **MEASURED bar_fraction=0.000** (0/19 samples) | **bar_fraction=0.000 (0/36 samples, top8/bottom8% Y≥25)** |
| G5 typography | pixelTest=True (differential via explicit `--ass`) | pixelTest=True + hookInCands + wordComplete | **pixelTest=True via R2 auto-discovered differential (max rel 0.026) + hook word-complete** |
| G6 audio | duck 13.04 dB, outI −16.3, music=**synth** | duck 13.1 dB, outI −15.3, via=archive_cc (**mood-blind**) | **duck 13.07 dB, outI −15.2 (verify-and-correct loop), via=incompetech_ccb "Healing" CC-BY** *(credit NOT burned in v2.1 — W1; burned from v2.1.1)* |
| G7 pacing | 1.29 cps, band [1.2,2.0], align 0 ms | 1.28 cps, clustersMax 2, pseudo 75% | **0.49 cps in the DECLARED downshifted band [0.3,0.7], clustersMax 2, pseudo 62%** |
| G8 evidence | 3/3 reports | 3/3 | **3/3 + 10-file committed evidence set (R5)** |
| G9 latency | wall 451 s, setup 32 s | wall 392 s, setup 26 s | **wall 424 s, setup 23 s** |
| G10 free | music = in-pipeline synth | music = CC0 archive (unchecked mood) | **music = CC BY 4.0 (incompetech) + CC-BY 4.0 source; zero paid calls** *(v2.1 attribution was manifest-only, not on-screen — W1; G10 attribution clause added in v2.1.1)* |
| G11 fidelity | (gate did not exist; 17.5 s vs 30 s silent) | 10.0 s vs 30 s = 33%, honest impossibility, **no downshift attempted** | **18.4 s vs 30 s = 61%, honest impossibility AFTER the logged style-density downshift (L1→L2→L3 ladder full)** |

### Music-source census (the E3/R4 arc)

| run | via | track | mood verdict |
|---|---|---|---|
| v2.0 (37891911705) | synth_fallback | generated pad | real-music mandate unmet |
| 38043976013 | archive_cc | **geometry_dash_1.9** (game OST, CC0) | license-safe, mood-blind — audit's R4 case |
| E-sweep drafts | archive_cc | Sherlock Holmes (sad) / The Odyssey (cinematic, **librivox audiobook — caught post-hoc**) / Jack Benny (motivational) | screened with 1-line rationales; audiobook hole found |
| **38109649950 (ship)** | incompetech_ccb | **"Healing" — Kevin MacLeod, CC BY 4.0** | mood-appropriate ambient score; manifest + MEDIA_LICENSES correct, but the on-screen credit was **NOT** burned in v2.1 (W1: stage-06 manifest wiring gap, `plan.music_credit=None`) — burned on-screen from **v2.1.1** onward |

### G11 target-fidelity outcomes

| run | requested | delivered | fidelity | ladder behaviour |
|---|---|---|---|---|
| 38043976013 | 30 s | 10.0 s | 33% | impossibility declared with **no** downshift (the R3 defect) |
| **38109649950** | 30 s | 18.4 s | 61% | L1 margin → L2 luma floor → **L3 style-density downshift [1.2,2.0]→[0.3,0.7] (logged, predicted fill 28.9 s)** → honest impossibility at full scene-capped capacity |

The residual gap is structural: 7 candidate-bearing clusters × cap 2 = the
entire usable footage; delivering 24 s+ would require replaying source (G3
violation). The user-facing `duration_chain` states delivered vs requested
and why, in the plan itself.

## 2. Audit findings R1–R5 — closed with probe/log proof (one commit each)

| finding | fix | proof |
|---|---|---|
| R1 probe hermeticity | d6 synthesizes its own production-shaped ass (captions.ASS_HEADER, bottom safe-zone, cue-spanning events), burns it, and asserts the DIFFERENTIAL path is the one used; fonts via CF_FONTS_DIR only | `reports/audits/v2.1-resume/R1_d6_probe.txt`, suite snapshot `SUITE_14plus_nits.txt` (a036d4b) |
| R2 false-RED in prod | captions.py records `ass_path` (absolute) in captions_report.json; qc auto-discovers (recorded → repo-root → media/ → reports → repo glob) and says how; absolute fallback 0.3%→**0.15%** labelled `FALLBACK`; latent bug found while proving: `_band_edge_density` needed `-copyts` or the re-burn evaluated at seek-shifted t=0 (hidden tautology — brn==nob to 3 decimals) | `R2_solo_qc_without_ass.txt` — solo CLI, no --ass: differential max rel 0.014 auto-discovered; ass removed: labelled FALLBACK passes (c73867a) |
| R3 G11 style-locked impossibility | L3 `style_density_downshift`: one style step at a time toward sparser cuts bands, every step logged, `_fidelity_out` fills toward the request with transition-aware band bounds; effective band surfaced to `plan.cuts_band` so G7 measures what was declared; impossibility remains last resort | `R3_probe.txt` — ladder logs [1.2,2.0]→[0.3,0.7] (fill ≥ goal) BEFORE impossibility; delivered cps inside the declared band (f6d7735) |
| R4 mood relevance | `mood_fit()` veto+rank heuristic per mood family; `apply_mood_fit()` screens/ranks candidates before any download; 1-line `mood_fit` rationale in every manifest music entry; ship-run hardening: SPOKEN_WORD_VETO (librivox/audiobook/…) scanned incl. the archive identifier + `-collection:librivoxaudio` in the query | `R4_probe.txt` — geometry-dash vetoed, true hit ranks first, manifest carries rationale, librivox id vetoed (17c5a1a, 7896a2c) |
| R5 evidence law | 11-final-delivery.yml copies captions_report.json + fonts_report.json into the delivery bundle and the git evidence commit; both audited runs backfilled from artifacts | run dirs `run-38043323428` / `run-38043976013` / `run-38109649950` each carry the full 10-file set (fa8c41d, 06176e8) |

## 3. Failures → fixes (continued)

| failure | root cause | fix | verified by |
|---|---|---|---|
| d6 probe verdict was font-metric-dependent (independent rerun false-RED) | probe ran QC without an ass → legacy absolute path | R1+R2 (above); probe now asserts the path used | d6 + r2 proofs |
| e6 probe failed locally while CI green | scenedetect installed for a different interpreter (PEP 668) | env fix only (`python3 -m pip`); no code change | e6 PASS locally post-install |
| Draft G4 letterbox RED in the E sweep | pre-existing draft-path behavior, invisible while G4 was by-construction (old Oct-9 draft measured: top/bottom bands Y=10) | documented in drafts README; production path measured 0.000 — gate now tells the truth on both paths | `drafts-v2.1/README.md` |
| Ship run 1 (38109018157) RED at stage-10: G6 outI −14.6 | dynamic speech bed under-corrects single-pass loudnorm | mix verify-and-correct loop (measure ebur128 → corrective loudnorm, max 2, each logged in `loudness_corrections[]`) | ship run 2: outI −15.2 in band (3a892a6) |
| Ship run 1 music: "The Odyssey" = librivox audiobook passed as 'neutral' | spoken-word forms unvetoed; identifier not scanned | R4 hardening (SPOKEN_WORD_VETO + identifier scan + query-level exclusion) | r4 probe case 7 (7896a2c) |

## 4. Phase D2 — creative self-review, 7 axes

Run 38043976013 (mandated review target): hook 8.5 / pacing 8 / typography 9 /
layout 9 / grade 8.5 / audio 8.5 / **music 5.5** — the audit's exact
mood-blind case; 3 timestamped complaints recorded (music mood mismatch,
empty-sky holds at 3.4 s/5.2 s, hook anchor high). Axis < 8 triggered the
fix → re-run → review-again rule → ship run 38109649950:
**hook 8.5 / pacing 8.5 / typography 9 / layout 9.5 / grade 8.5 / audio 9 /
music 8.5 — all axes ≥ 8, PASS** (worst residual complaints: sky-wash holds
at 5.0 s/12.2 s, hook anchor, fallback-list provenance of the music track).
Both reviews are committed in their run directories with frame-level
evidence.

## 5. Phase E — style sweep

Three 98-iterate drafts on source-v1 (30 s ask): sad_emotional (sad_cold /
emotional_soft / [0.15,0.35] / "Sherlock Holmes"), cinematic (teal-orange /
minimal_clean / [0.3,0.7] / "The Odyssey"), motivational (natural /
viral_high_contrast / [0.3,0.7] **via the logged downshift** / "Jack Benny").
`e_sweep_assert.py`: 3 distinct grades, 3 distinct caption styles, 3 distinct
music sources, every plan param equals its own styles.json entry — **zero
config bleed** (the only band deviation is the declared relaxation). R3 fired
and was logged in production CI; R2 auto-discovery exercised in CI ("ass
default media/captions.ass").

## 6. Confidence scores (self-assessed, with basis)

| area | confidence | basis |
|---|---|---|
| Bar-death (E1/E2) stays dead | 0.97 | measured bar_fraction 0.000 on 36 edge samples, ship run; 0.000 on run 3's 19 samples; old draft letterbox now VISIBLE to the same gate |
| Caption claims (R1/R2) | 0.95 | differential path asserted by the hermetic probe + solo-CLI proof; the seek-shift tautology (would have masked any regression) is fixed and pinned |
| Music rights cleanliness (G10) | 0.97 → 0.72 for v2.1 as shipped | CC0/CC-BY only, manifest + MEDIA_LICENSES; synth fallback gated behind logged egress failure. Downgraded: the v2.1 artifact lacked the on-screen credit (W1) — restored to 0.97 by the v2.1.1 re-ship with the burned credit + G10 attribution clause |
| Music mood fit | 0.85 | "Healing" tonally reviewed at 8.5; screen is keyword/tag-based, not audio analysis — fallback provenance honestly logged |
| G11 honesty | 0.9 | ladder fully attempted + logged; delivered = entire effective capacity; the 18.4-vs-30 s gap is structural (7 clusters × cap 2), not silent |
| Gate reproducibility from git alone | 0.9 | 10-file evidence set committed per run (R5); every gate value carries an artifact path |
| Pipeline robustness | 0.88 | two ship runs exercised the R-code end-to-end; loudness self-heal + mood veto closed the two stage-10 failures |

## 7. Deliverables

- Release: https://github.com/tsfofficial000-hash/ai-video-lab/releases/tag/cineforge-v2.1 —
  final video, contact sheet, full G8 bundle (all ten reports + both
  aesthetic reviews + gates snapshot), poster
- Committed evidence: `reports/cineforge/run-38109649950/` (10 files),
  `run-38043976013/` (10 files, incl. D2 pass-2 review),
  `run-38043323428/` (10 files), `reports/cineforge/drafts-v2.1/` (E sweep),
  `reports/audits/v2.1-resume/` (R1–R5 proofs)
- Suite state at ship: **14/14 mandated probes + nits 4/4 green**
  (CF_FONTS_DIR only), plus R3/R4 probes green
- MEDIA_LICENSES.md updated with the incompetech CC-BY credit string and the
  archive.org ladder rules

## 9. Addendum — CineForge v2.2 audit findings W1–W6 (all closed with probe + fix + one commit)

The v2.2 audit found six gaps on top of the shipped v2.1. Every item follows
the evidence law: a failing probe reproduces the defect first, the fix lands
in exactly one commit, and the proof is measured, never asserted. Suite at
closure: **14/14 mandated probes + nits 4/4 + seven W probes (W1–W7) green**.

| # | Finding | Root cause (measured) | Fix (commit) | Proof |
|---|---|---|---|---|
| W1 | Shipped v2.1 final had **no on-screen CC-BY credit** while this report claimed "attribution burned on-screen" | stage-06 downloaded only stage-02…05, so `media_manifest.json` never reached `edit_plan.py` → `plan.music_credit=None` (verified on run 38109649950's committed plan) | stage-01 uploads a tiny `stage-01-manifest` artifact; stage-06 downloads it; QC gained `music_credit_on_screen` (structural + outro-band differential, unmeasurable = RED); G10 attribution clause (manifest → plan → pixels) | `e4f26c2` + probe `w1_credit_burn.py`; ship run 38129852247: credit differentially verified at 15.2 s + frame-extracted credit visible in the released MP4 |
| W1-CI | The burned credit **clipped both ends** ("Music: " and "BY 4.0" off-frame) | 74 chars at fs 34 ≈ 1150 px > 1080 px frame (frame evidence on run 38128752534) | width-fit: one line at `fs = min(style, 0.92·w/(0.55·len))` floor 22 (lands at 24 → 977 px), two balanced lines only when the floor cannot fit; QC normalizes `\N` in the window finder | `5a7831d` + w1 probe width legs (1080: fs 24 fits; 540: 2-line wrap, every word kept) + rendered-frame visual |
| W2 | Differential **passed an uncaptioned video** when fonts were unresolvable (deltas 0.000, "tautology confirmed") | a zero delta means "burned" OR "nothing rendered" — no control | `fonts_resolvable()` self-test: a known-text control re-burn (the ass's own families) must inject luma (measured 34.6 YAVG) before any delta is trusted; failure reason propagates RED; void-band guard (both frames reading 0 = unmeasurable) | `0ca4ed2` + probe `w2_font_guard.py` (fontconfig-neutered clean checkout reproduced; unmeasurable REDs with the exact contract reason) |
| W3 | Draft path **bar-blind**: 98 never ran `bar_map.py` → every draft rendered letterboxed, draft G4 RED, loop reviewed frames production would never show | wiring gap (only make_proxy.sh in the 99 chain built the map) | 98 stage-01+02 runs `bar_map.py` before `edit_plan.py`; evidence bundle copies the map; iterate gate print **requires draft G4 green** (executable heredoc, after the one-liner SyntaxError lesson `42703c0`); G4 verifies the DECLARED layout (cinematic letterbox = 5.5 % bars → presence ≥95 % in a top-4 % band, `741c2aa`/`0cba570`) | `03c91da` + probe `w3_draft_barmap.py` (letterboxed RED 1.000 vs bar-free GREEN 0.000; gate script executed against 3 synthetic gate reports) |
| W4 | E-sweep music evidence pre-dated the spoken-word veto; **post-veto re-runs still picked OTR radio shows** ("Tales Of The Texas Rangers", "Fibber McGee and Molly - 1942" — metadata carries no spoken-word marker) | text-level veto structurally blind to collection-typed items; `captions.py` also double-counted the last segment (plan total 11.3 s vs delivered 7.9 s) pushing the credit off-screen — caught by W1's own pixel check | veto learned OTR/episode-collection shapes (`52456fa`); archive search excludes `-collection:OldTimeRadio` + collection-field screen (`ef1e820`); credit window anchored to the DELIVERED duration (`7759bf4`, model verified: cum 18.44 == plan delivered on the ship run) | probes `w4_music_evidence.py` + `w7_credit_window.py`; three ALL-GREEN post-veto drafts committed (`3e63344`): zero spoken-word picks, credit pixel-verified in all three finals |
| W5 | Ship review's declared residuals: static sky-holds occupied cluster slots; 2-line hooks rode ~y12–16 % vs the y=30 % spec center | Selector took the earliest qualifying candidate regardless of motion; `\an5` anchor + a half-line subtraction double-compensated | in-cluster motion-variance selection (most dynamic candidate within a same-scene horizon; all hard guards unchanged, capacity semantics preserved); hook block center anchored directly on the spec line | `6be2c34` + probe `w5_creative_residuals.py` (dynamic 8.0 s candidate beats the 4.0 s sky-hold; 2-line hook anchors at y=576) |
| W6 | Draft G6 variance (`outI=-14.8`) while production self-heals | the sweep ran before `3a892a6`; nothing proved the loop covers the draft path or labelled draft tolerance | proof: 98's stage-07 invokes the same self-healing `audio_mix.py`; iterate gate print LABELS draft G6 (declared wider [-18,-14], non-fatal; production band enforced at 99) | `bb8caa2` + probe `w6_draft_loudness.py` (draft invocation self-verifies outI=-16.1; corrective primitive -1.4 → -16.0 LUFS) |

**Ship (v2.1.1, final)**: run **38129852247** on `5a7831d` — the release
[`cineforge-v2.1.1`](https://github.com/tsfofficial000-hash/ai-video-lab/releases/tag/cineforge-v2.1.1)
assets are replaced in place (same tag, `--clobber`); this run's MP4 is the
one with the complete, width-fitted credit burned on-screen. Run
38128752534 (same tag, earlier commit) is superseded: its gates were
ALL_GREEN but its credit line clipped. Gate snapshot for the final ship run
lives in `reports/cineforge/run-38129852247/` alongside the superseded
run's evidence.
