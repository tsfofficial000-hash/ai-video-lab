#!/usr/bin/env bash
# =============================================================================
# TEST D — Whisper ASR pipeline: engine comparison + FFmpeg burn-in hand-off.
#   1. shared master fixture (provides refmix.m4a audio for ASR)
#   2. faster-whisper (small, base) vs openai-whisper (base.en) on same audio
#   3. similarity scored against known reference narration text
#   4. burn each engine's SRT into a separate final video via FFmpeg
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
mkdir -p "$WORK"; cd "$WORK" || exit 1

metric(){ echo "[METRIC] $1=$2" | tee -a metrics.txt; }
fail(){ echo "[FAIL-D] $*" | tee -a metrics.txt; exit 1; }
T_ALL=$(date +%s)

# ---------- 1. Fixture + master (video target for burn-in) ----------
bash "$ROOT/scripts/build_master.sh" || fail "master build failed"

# ---------- 2. Engine comparison on the SAME mixed audio ----------
pip install -q faster-whisper "av==14.2.0" openai-whisper 2>/dev/null \
  || pip install -q --break-system-packages faster-whisper "av==14.2.0" openai-whisper \
  || fail "whisper installs failed"
python3 "$ROOT/scripts/whisper_compare.py" refmix.m4a ref_text.txt . || fail "whisper compare failed"

# ---------- 3. Burn-in hand-off: each engine's SRT -> final video ----------
STYLE="FontName=DejaVu Sans,FontSize=11,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=18"
for srt in subs_fw_small.srt subs_fw_base.srt subs_ow_base_en.srt; do
  [ -s "$srt" ] || { metric "burn_${srt}" skipped_missing_srt; continue; }
  T0=$(date +%s)
  ffmpeg -y -v error -i master.mp4 \
    -vf "subtitles=${srt}:force_style='${STYLE}'" \
    -c:v libx264 -preset medium -crf 20 -c:a copy "final_whisper_${srt%.srt}.mp4" 2>> burn_errors.log \
    || { metric "burn_${srt}" failed; tail -5 burn_errors.log; continue; }
  metric "burn_${srt}_seconds" "$(( $(date +%s) - T0 ))"
done

# ---------- 4. Validation ----------
for f in final_whisper_*.mp4; do
  [ -s "$f" ] || continue
  D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
  metric "output_${f}_duration" "$D"
done
metric whisper_total_wall_seconds "$(( $(date +%s) - T_ALL ))"
echo "[DONE-D]"
