# Aesthetic report (auto-stats)
- runtime: 18.367s, segments: 9, cut density: 0.49 cuts/s
- transitions: {'fade': 6, 'fadewhite': 1, 'fadeblack': 1}
- grade: cinematic_teal_orange, vertical: cover_crop
- qc status: pass

## Creative self-review
(appended by the agent during Phase 3 creative loop; see reports/cineforge/)

## Creative self-review pass 2 (v2.1 Phase D2 re-run, SHIP candidate, run 38109649950)

Dispatched after the pass-2 review of run 38043976013 scored music 5.5 (the
audit's geometry-dash-for-cinematic case) and triggered the fix -> re-run ->
review-again rule. This run carries the full R1-R5 code: R3's density
downshift (beat_montage [1.2,2.0] -> cinematic [0.3,0.7], logged in
relaxations + duration_chain.note), R4's mood screen (archive candidates
vetoed/ranked; this run landed on the incompetech CC-BY fallback "Healing" -
a mood-appropriate ambient score with the attribution line burned in the
outro), R2's ass auto-discovery, and the mix loudness verify-and-correct
loop (outI -15.2 in band). G1-G11 ALL GREEN, measured: bar_fraction 0.000
(0/36 edge samples), 0.49 cps in the declared band, clustersMax 2, wall 424 s.

Evidence: committed contact sheet + 11 full-res frames (t = 0.8, 2.0, 3.2,
5.0, 6.8, 8.4, 10.0, 12.2, 14.6, 16.2, 17.6 s) + top/bottom 8% band scans
(n=37, min 31/26, zero dark samples) + credit-band check at 17.6 s.

| # | axis | score | evidence |
|---|------|-------|----------|
| 1 | hook | 8.5 | "I'M SEARCHING / FOR SOMEONE" complete punch-rule phrase, Anton 2 lines width-fitted, entrance anim, gone by 2.5 s (t=0.8/2.0 frames); rides ~y12-16% vs y~30% spec center (cosmetic, complaint 2) |
| 2 | pacing | 8.5 | 0.49 cps inside the DECLARED downshifted band [0.3, 0.7]; 9 segments over 18.4 s at cinematic density; pseudo-cut mix 62%; no cluster doubling (7 clusters, cap 2); beat alignment 0 ms |
| 3 | typography | 9 | bold_highlight ~99px outline5 shadow3, yellow keyword pop on "searching" (t=2.0/3.2 frames), <=2 lines <=18 chars, G5 pixel test green via R2 auto-discovered differential |
| 4 | layout | 9.5 | full-bleed MEASURED bar_fraction=0.000 across 36 edge samples; end card + sub-line pinned to the bottom safe band (t=16.2/17.6); CC-BY credit line rendered at y~96% in the outro |
| 5 | grade | 8.5 | cinematic_teal_orange consistent across all 9 segments; warm desert palette coherent; no crush (G2 medianY=89, blown=0) |
| 6 | audio | 9 | sidechain duck 13.07 dB, output -15.2 LUFS IN BAND after the verify-and-correct loop, impact/whoosh SFX bed, no tail silence |
| 7 | music | 8.5 | "Healing" - Kevin MacLeod (incompetech), CC BY 4.0: tonally right for cinematic fantasy (ambient score under aerial footage), attribution burned on-screen + manifest; from the curated CC-BY fallback rather than a keyword-matched archive hit (complaint 3) |

Worst complaints (with timestamps):
1. Sky-wash holds at t=5.0 s and t=12.2 s - subject-less cloud frames; the
   7-cluster x cap-2 budget still spends 2 of 9 segments on vacant skies
   (future fix: in-cluster motion-variance preference at selection time).
2. Hook block sits at ~y12-16% (t=0-2.5 s) above the y~30% safe-zone center
   intent - the two-line anchor positions the block bottom, not its visual
   center. Cosmetic.
3. Music came from the curated CC-BY fallback list, not a keyword-matched
   archive hit - the mood_fit rationale honestly logs 'no per-item fit
   metadata'; improving the archive screen's keyword recall is future work.

Verdict: ALL 7 AXES >= 8 -> PASS. Ship-ready as the v2.1 deliverable.
Residual honesty: 18.4 s delivered vs 30 s requested (61%) under the declared
impossibility note - the R3 ladder downshifted the density band and filled
the full scene-capped capacity (9 segments = the entire effective capacity);
pushing to 24 s would require reusing footage (G3 violation).

