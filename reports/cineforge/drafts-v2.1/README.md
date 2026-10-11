# Phase E style sweep (v2.1) - three drafts on source-v1 (Sintel), 30 s ask

## POST-VETO RE-RUNS (W4 closure) - authoritative table

| run | style | grade | caption | cuts band | cps | music (post-veto) | draft gates |
|---|---|---|---|---|---|---|---|
| 38127183904 (@7759bf4) | sad_emotional | sad_cold | emotional_soft | [0.15, 0.35] | 0.25 | incompetech_ccb "Healing" (curated CC-BY fallback; OTR collections vetoed) | ALL GREEN (G9 pending by design); W1 credit pixel-verified on-screen (window 5.5-7.7 s, rel 0.062) |
| 38125437999 (@741c2aa) | cinematic | cinematic_teal_orange | minimal_clean | [0.3, 0.7] | 0.49 | incompetech_ccb "Healing" (curated CC-BY fallback) | ALL GREEN; DECLARED letterbox bar_presence 1.000 (32/32, top-4% band); credit pixel-verified (rel 0.012) |
| 38126219366 (@ef1e820) | motivational | natural | viral_high_contrast | [0.3, 0.7] | 0.49 | incompetech_ccb "Healing" (curated CC-BY fallback) | ALL GREEN; loudness self-heal fired (1 correction, outI -16.0); credit pixel-verified (rel 0.058) |

Differences asserted (E_sweep_assert.txt): 3 distinct grades, 3 distinct caption
styles, bands per style - ZERO config bleed. Music conclusions: the spoken-word
veto works (zero OTR/audiobook picks across three post-veto runs); the archive
ladder returns no license-clean music for these moods once the OTR/librivox
flood is excluded, so the ladder degrades to the curated CC-BY fallback with
attribution burned on-screen and the fallback reason recorded in the manifest.

## W4 invalidation record (audit trail)

The ORIGINAL sweep rows below are INVALID for the music column (pre-veto
dispatches that shipped audiobooks/radio shows as "music"); they are kept for
the config-bleed history. Post-veto re-runs at 42703c0/0cba570 still picked
OTR collections ("Tales Of The Texas Rangers" / "Fibber McGee and Molly -
1942") - their search metadata carries no spoken-word marker, which produced
the veto hardening (52456fa: OTR/episode-collection shapes) and the search
layer fix (ef1e820: -collection:OldTimeRadio + collection-field screen).
A captions.py plan-total bug (double-counted last segment) pushed the credit
event off-screen on scarcity-shrunk plans - caught by the W1 QC pixel
verification exactly as designed, fixed in 7759bf4 (probe w7_credit_window).

## Original (pre-veto, music column INVALID) sweep

| run | style | grade | caption | cuts band | cps | music (INVALID - pre-veto) | draft gates |
|---|---|---|---|---|---|---|---|
| 38108781479 | sad_emotional | sad_cold | emotional_soft | [0.15, 0.35] | 0.29 | ~~"The Adventures of Sherlock Holmes"~~ (librivox audiobook) | G4/G5 draft-path RED (pre-bar-map), G11 honest impossibility (10.4 s) |
| 38108784839 | cinematic | cinematic_teal_orange | minimal_clean | [0.3, 0.7] | 0.49 | ~~"The Odyssey"~~ (librivox audiobook) | G4/G5 draft-path RED (pre-bar-map), G11 honest impossibility (18.4 s) |
| 38108787972 | motivational | natural | viral_high_contrast | [0.3, 0.7] DOWNSHIFTED (declared) | 0.49 | ~~"Jack Benny 143 Eps"~~ (OTR radio comedy) | +G6 outI -14.8 (draft variance, pre-self-heal); R3 downshift LOGGED; impossibility note |

The draft-path G4/G5 REDs and the G6 variance of the original round are
closed for good by W3 (bar map + required draft G4 green), W6 (self-heal +
labelled draft G6 band) and the declared-letterbox G4 contract.

Draft finals + full evidence live in run artifacts iterate-evidence-<run_id>
(Actions); JSONs + contact sheets committed here per the evidence law.
