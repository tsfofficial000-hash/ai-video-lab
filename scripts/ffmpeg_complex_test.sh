#!/usr/bin/env bash
# =============================================================================
# TEST A — Raw FFmpeg baseline: full complex edit end-to-end.
#   build_master.sh (trim/xfade/9:16/drawtext/loudnorm)
#   + gen_subs.sh (faster-whisper SRT on the mixed audio)
#   + libass subtitle burn-in
#   + hardware-acceleration fallback probes
#   + final validation
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
mkdir -p "$WORK"; cd "$WORK" || exit 1

metric(){ echo "[METRIC] $1=$2" | tee -a metrics.txt; }
fail(){ echo "[FAIL-A] $*" | tee -a metrics.txt; exit 1; }
# shellcheck source=scripts/time_shim.sh
source "$ROOT/scripts/time_shim.sh"; WORK="$WORK"; ensure_time
T_ALL=$(date +%s)

# ---------- 1. Master render (shared, timed) ----------
bash "$ROOT/scripts/build_master.sh" || fail "master render failed"

# ---------- 2. Whisper ASR on the mixed audio ----------
bash "$ROOT/scripts/gen_subs.sh" || fail "whisper SRT generation failed"
[ -s subs.srt ] || fail "subs.srt empty"
metric srt_cues "$(grep -c ' --> ' subs.srt)"

# ---------- 3. Subtitle burn-in (libass) ----------
T2=$(date +%s)
"$TIME_BIN" -v ffmpeg -y -v error -i master.mp4 \
  -vf "subtitles=subs.srt:force_style='FontName=DejaVu Sans,FontSize=11,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=18'" \
  -c:v libx264 -preset medium -crf 20 -c:a copy final_ffmpeg.mp4 2> time_burn.txt
RC=$?
[ $RC -eq 0 ] || { echo "--- burn stderr ---"; tail -15 time_burn.txt; fail "subtitle burn rc=$RC"; }
T3=$(date +%s)
metric burn_render_seconds "$((T3-T2))"
awk -F': ' '/Maximum resident/{print "[METRIC] burn_peak_rss_mb="int($2/1024)}' time_burn.txt | tee -a metrics.txt

# ---------- 4. Hardware acceleration fallback probes ----------
ffmpeg -hide_banner -hwaccels > hwaccels.txt 2>&1
echo "[LAB-A] available hwaccels:"; cat hwaccels.txt
probe_hw(){
  local name=$1; shift
  if ffmpeg -y -v error "$@" -f null - 2> "hw_${name}.err"; then
    metric "hwaccel_${name}" available
  else
    metric "hwaccel_${name}" unavailable
    echo "--- hw_${name}.err (tail) ---"; tail -3 "hw_${name}.err"
  fi
}
probe_hw vaapi        -init_hw_device vaapi=va:/dev/dri/renderD128 -f lavfi -i testsrc2=size=640x360:rate=30 -t 1 -c:v h264_vaapi
probe_hw nvenc        -f lavfi -i testsrc2=size=640x360:rate=30 -t 1 -c:v h264_nvenc
probe_hw qsv          -f lavfi -i testsrc2=size=640x360:rate=30 -t 1 -c:v h264_qsv
probe_hw videotoolbox -f lavfi -i testsrc2=size=640x360:rate=30 -t 1 -c:v h264_videotoolbox
metric hwaccel_fallback_libx264 available

# ---------- 5. Final validation ----------
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,width,height -of json final_ffmpeg.mp4 > final_probe.json
FD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 final_ffmpeg.mp4)
FS=$(stat -c%s final_ffmpeg.mp4)
FW=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 final_ffmpeg.mp4)
FH=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 final_ffmpeg.mp4)
FA=$(ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 final_ffmpeg.mp4)
metric final_resolution "${FW}x${FH}"
metric final_duration "$FD"
metric final_size_mb "$(awk -v s="$FS" 'BEGIN{printf "%.1f", s/1048576}')"
metric final_audio_codec "$FA"
ffmpeg -y -v error -ss 5 -i final_ffmpeg.mp4 -frames:v 1 thumbnail_ffmpeg.jpg
metric ffmpeg_total_wall_seconds "$(( $(date +%s) - T_ALL ))"
echo "[DONE-A]"
