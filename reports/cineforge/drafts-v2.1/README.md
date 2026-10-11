# Phase E style sweep (v2.1) - three drafts on source-v1 (Sintel), 30 s ask

| run | style | grade | caption | cuts band | cps | music (via=archive_cc, mood-screened) | draft gates |
|---|---|---|---|---|---|---|---|
| 38108781479 | sad_emotional | sad_cold | emotional_soft | [0.15, 0.35] | 0.29 | "The Adventures of Sherlock Holmes" (sad) | G4/G5 draft-path RED, G11 honest impossibility (10.4 s) |
| 38108784839 | cinematic | cinematic_teal_orange | minimal_clean | [0.3, 0.7] | 0.49 | "The Odyssey" (cinematic) | G4/G5 draft-path RED, G11 honest impossibility (18.4 s) |
| 38108787972 | motivational | natural | viral_high_contrast | [0.3, 0.7] DOWNSHIFTED (declared) | 0.49 | "Jack Benny 143 Eps" (motivational, neutral-pass) | +G6 outI -14.8 (draft variance); R3 downshift LOGGED; impossibility note |

Differences asserted (E_sweep_assert.txt): 3 distinct grades, 3 distinct caption
styles, 3 distinct music sources, bands per style - ZERO config bleed (every
plan param equals its own styles.json entry; the only band deviation is the
logged style_density_downshift relaxation, R3 firing in production).

Known draft-path artifact (pre-existing, now VISIBLE because E2 made G4
measured): 98-iterate draft renders letterbox (measured on the pre-R Oct-9
draft final: top/bottom 8% bands Y=10) -> draft G4 RED is the gate working,
not a regression. The production 99 path is pixel-measured clean
(run 38043976013: bar_fraction=0.000). R2 auto-discovery proven in CI: draft
qc ran the hook-card differential re-burn via "ass default media/captions.ass".

Draft finals + full evidence live in run artifacts iterate-evidence-<run_id>
(Actions); JSONs + contact sheets committed here per the evidence law.
