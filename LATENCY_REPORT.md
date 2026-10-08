# LATENCY_REPORT.md

Measured on the successful end-to-end run (run id 37746375946, rerun-failed-jobs continuation, ubuntu-latest 4-core runners, 2026-10-08). Source: Blender Sintel trailer (1080p, 52.2s) → 26.2s beat_montage final.

## Stage table

| Stage | Status | Duration | Output | Bottleneck | Optimization |
|---|---|---:|---|---|---|
| 00 environment | pass | 68.0s | reports/environment.json | apt install | shared setup-cf action, pip cache |
| 01 assets | pass | 67.0s | source.mp4 + music + manifest | none (direct CC asset) | sample chain, source-v1 self-heal |
| 02 ingest/proxy | pass | 60.0s | metadata, proxy, wav, contact sheet | ffmpeg proxy encode | 480p veryfast proxy |
| 03 audio analysis | pass | 61.0s | audio_analysis.json | ffmpeg scans | single-pass volumedetect/silencedetect/loudnorm |
| 04 transcript | pass | 91.0s | transcript + srt | whisper model load | small int8, VAD, base fallback |
| 05 beat analysis | pass | 86.0s | beats.json | librosa full-file decode | 22.05kHz mono decode |
| 06 edit decision | pass | 77.0s | edit_plan.json + timeline | none | pure python |
| 07 audio mix | pass | 55.0s | mixed_audio.wav (-16 LUFS) | none | sidechaincompress (Demucs rejected: 6-10min) |
| 08 video render | pass | 177.0s | master.mp4 26.2s + poster | 49 segment encodes + xfade graph | parallel 2-job renders, real-duration offsets |
| 09 captions | pass | 60.0s | final.mp4 (copy; style=n/a for montage) | n/a | skip-branch for null caption styles |
| 10 QC | pass | 66.0s | qc_report.json (12/12 pass) | loudnorm scan | fail-fast exit 2 |
| 11 delivery | pass | 80.0s | bundle artifact + release | release upload | conditional asset upload |
| **TOTAL** | **12/12 pass** | **~15.8 runner-min** | | | |

## Goals vs achieved

- Environment check < 2 min: **68s ✓**
- Dependency install < 5 min: **~35s per stage (pip-cached) ✓**
- 30s draft render < 10 min: **full 1080p final render = 3 min ✓ (draft path unused)**
- 60s final render < 20 min: **projected ~8-10 min render stage ✓**
- Heavy AI isolated: **transcript (91s) parallel with audio+beats; not on critical path ✓**

## Retries & runs

- Total workflow runs this session (montage + cineforge): 25
- Dispatch-run iterations to first fully-green 99 chain: 9 (bug classes: YAML schema ×2, artifact path layout, CWD-relative config, numpy2 scalar, kwarg mismatch, argparse requirements, workspace over-step, xfade drift)
- Spurious job cancels: 1 (recovered via rerun-failed-jobs API, artifacts preserved)

## Key optimization wins

1. **Artifact-layout immunity**: glob resolvers + pre-cd absolute paths killed an entire bug class.
2. **Real-duration xfade offsets**: master duration now derives from actual encoded segment files, not planned values (drift eliminated).
3. **sidechaincompress over Demucs**: stage 7 = 55s vs ~10 min.
4. **Reusable-workflow chaining**: any failed stage re-dispatches alone; rerun-failed-jobs preserves upstream artifacts.
