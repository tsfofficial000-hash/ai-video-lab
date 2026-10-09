# Aesthetic report (auto-stats)
- runtime: 17.5s, segments: 23, cut density: 1.31 cuts/s
- transitions: {'fade': 22}
- grade: cinematic_teal_orange, vertical: cover_crop
- qc status: pass

## Creative self-review
(appended by the agent during Phase 3 creative loop; see reports/cineforge/)


## Creative self-review (agent, six axes, from contact sheet + frames)

- runtime 17.50s, 23 segments, 1.29 cuts/s (band [1.2, 2.0]), beat alignment 0ms
- transitions: fade xfade-dominant per spec 2.4, fadewhite at section bounds (2 frames), fadeblack outro only
- grade: cinematic_teal_orange (single application point), vertical: cover_crop full-bleed

| axis | score | evidence |
|---|---|---|
| hook | 9 | "WHAT BRINGS YOU / TO THE LAND" Anton fs150 width-fitted 2 lines at y~30%, entrance 0.25s, gone by 2.5s, impact SFX at t=0 |
| pacing | 8.5 | 1.29 cps; motion-variance interleave alternates action/static (33.2, 0.5, 26.6, 1.6, ...); no tail sag; dialogue button at 0.8s |
| typography | 9 | bold_highlight 99px outline5 shadow3 marginV291, keyword pop on "searching", <=2 lines <=18 chars, yellow \1c pop |
| layout | 8.5 | full-bleed cover_crop, no letterbox, end card + Sintel logo fade, safe zones asserted |
| grade | 8 | teal-orange signature consistent; slight warmth wash on monochrome-orange desert footage |
| audio | 8 | generated cinematic bed, 13.04 dB duck, -16.3 LUFS integrated, synth SFX (impact/whoosh/riser) |

Complaints fixed this run (was 6.5/7.5/7 on hook/pacing/typography in run 37885213747):
1. hook clipped both edges -> width-fitted wrap (est-glyph check, fs floor 150)
2. desert-tail sag + duplicate-adjacent cuts -> motion interleave + caption merge
3. caption double-render over shared spans -> piece merge in projection
