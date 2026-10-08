# DECISIONS.md — engineering log

Each entry: what / why / effect / verdict.

1. **Existing repo reused (`ai-video-lab`), not new `cineforge-pro-lab`.**
   Why: prompt §5 says "If the repository already exists, use it"; repo is public (unlimited Actions minutes) and already hosts the validated montage engine + A-E experiment evidence.
   Effect: zero setup overhead; full history retained. Verdict: adopted.

2. **Reusable-workflow chaining for stages (00-11 called by 99).**
   Why: modular, per-stage debuggable, independently dispatchable; artifacts pass state; concurrency-safe.
   Effect: failed stage = re-dispatch that stage only (latency rule 6). Verdict: adopted.

3. **Montage engine as render core, wrapped by cineforge stages.**
   Why: beat-grid timeline -> segment render -> xfade/acrossfade master already dry-run-validated on 2-core sandbox and CI-proven (SAR fix, CFR fix).
   Effect: render stage inherits proven code; new code limited to captions/mix/QC. Verdict: adopted.

4. **sidechaincompress ducking instead of Demucs/Spleeter.**
   Why: Demucs CPU separation = 6-10 min per track on runner; sidechain = single-pass seconds.
   Effect: stage 7 ~10-20s vs ~10 min. Verdict: fallback promoted to default (documented in fallbacks.json).

5. **FreePD CC0 for mood music, HEAD-verified with synth-pad fallback.**
   Why: copyright safety (§7: no popular copyrighted music) + pipeline must never hard-fail on a dead link.
   Effect: every candidate verified at download; if all fail, generated pad (zero third-party rights). Verdict: adopted.

6. **faster-whisper small int8 + base fallback, VAD on.**
   Why: prior runs (whisper-asr.yml) measured small int8 at ~4.2x realtime on 2-core runners.
   Effect: transcript of 60s source ~15-25s. Verdict: adopted.

7. **Draft/final dual quality path.**
   Why: latency goal #3/#4; drafts use crf 23 + veryfast (~4x faster), final crf 19 + medium.
   Verdict: implemented in 08 inputs.

8. **Caption burn as separate stage 9 pass.**
   Why: burning forces video re-encode; separating it from the segment render lets plan/style iterate without re-rendering segments.
   Effect: iteration cost drops from ~full render to one fast burn pass. Verdict: adopted.

9. **Acquisition ladder self-heals via `source-v1` release cache.**
   Why: yt-dlp bot-walled on runner IPs (evidence: montage run 37721306346); tunnel jobs have variable latency; a successful acquisition uploads source.mp4 to a release so future runs never re-risk the ladder.
   Verdict: implemented in stage 01.

10. **QC auto-repair loop (renormalize loudness, recompress size).**
    Why: §10 repair examples; keeps stage 10 non-blocking for minor issues while gating hard failures.
    Verdict: adopted; exit code 2 only on unrepaired failures.
