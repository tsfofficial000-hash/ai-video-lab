# ai-video-lab

**Experimental benchmarking lab: can a 100% free, fully autonomous AI video-editing pipeline run inside GitHub Actions?**

Five isolated experiments run on GitHub-hosted runners. No cloud video APIs, no watermarks, no credits — pure open source.

| # | Workflow | Tool | Runner | What it proves |
|---|----------|------|--------|----------------|
| A | `ffmpeg-baseline.yml` | Raw FFmpeg (complex filtergraphs) | `ubuntu-latest` | trim → 9:16 blur-pad composite → xfade → drawtext → TTS mix → loudnorm → Whisper SRT burn-in + hwaccel fallback probe |
| B | `moviepy-test.yml` | MoviePy 2.x (Python) | `ubuntu-latest` | programmatic timeline generation, memory ceiling, render speed vs FFmpeg |
| C | `editly-test.yml` | Editly (Node.js/JSON) | `ubuntu-latest` | JSON-based templating, layer composition, ease of AI-agent integration |
| D | `whisper-asr.yml` | faster-whisper vs openai-whisper | `ubuntu-latest` | CPU speech-to-text on runner: speed, RAM, accuracy, SRT hand-off to FFmpeg |
| E | `palmier-pro-autopsy.yml` | [palmier-io/palmier-pro](https://github.com/palmier-io/palmier-pro) (Swift/macOS) | `macos-26` | headless CI feasibility autopsy of an AI-native macOS video editor |

## Shared test fixture

- **Footage**: Blender Open Movie trailer (Sintel, 1920x1080, CC-BY) downloaded at runtime onto the runner — with automatic fallback URLs.
- **Speech**: `espeak-ng` synthesizes a deterministic narration track so ASR accuracy is measurable (known reference text).
- **Edit spec** (identical intent across all tools): trim 2 segments → 9:16 vertical (1080x1920) → crossfade → dynamic title → mix narration + source audio → EBU R128 loudness normalization → auto-subtitle burn-in.

Every run emits `[METRIC] key=value` lines (greppable in CI logs), peak-RSS memory samples, and uploads the rendered MP4s + SRTs as artifacts.

## Usage

Workflows A–D auto-trigger on pushes touching their scripts. Workflow E (macOS, 10x minute multiplier) is `workflow_dispatch`-only:

```bash
gh workflow run "palmier-pro-autopsy.yml"
```

Verdicts live in **[FINAL_LAB_REPORT.md](./FINAL_LAB_REPORT.md)**.
