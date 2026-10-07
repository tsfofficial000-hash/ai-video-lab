#!/usr/bin/env bash
# =============================================================================
# Shared fixture prep: downloads public 1080p test footage + synthesizes a
# deterministic TTS narration track + guards a source-audio file.
# Produces (in work/): footage_src, footage.json, narration.wav, ref_text.txt,
#                      src_audio.m4a
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
mkdir -p "$WORK"
cd "$WORK" || exit 1

log(){ echo "[FETCH] $*"; }
metric(){ echo "[METRIC] $1=$2" | tee -a metrics.txt; }

command -v ffmpeg >/dev/null 2>&1 || { sudo apt-get update -qq; sudo apt-get install -y -qq ffmpeg; }
command -v espeak-ng >/dev/null 2>&1 || { sudo apt-get install -y -qq espeak-ng; }

# ---------- 1. Test footage (1080p, 30-60s, freely licensed) ----------
URLS=(
  "https://download.blender.org/durian/trailer/sintel_trailer-1080p.mp4"
  "https://download.blender.org/peach/trailer/trailer_1080p.mov"
  "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/1080/Big_Buck_Bunny_1080_10s_30MB.mp4"
  "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
)
LICENSES=("CC-BY Blender Foundation (Sintel)" "CC-BY Blender Foundation (Peach)" "CC-BY Blender Foundation (BBB sample)" "CC-BY Blender Foundation (BBB GTV mirror)")

if [ -s footage_src ] && ffprobe -v error footage_src >/dev/null 2>&1; then
  log "footage already present, reusing"
else
  SRC_OK=""
  for i in "${!URLS[@]}"; do
    u="${URLS[$i]}"
    log "trying source $i: $u"
    if curl -fL --retry 2 --connect-timeout 20 --max-time 300 -o footage_src "$u"; then
      W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 footage_src 2>/dev/null)
      H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 footage_src 2>/dev/null)
      D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 footage_src 2>/dev/null)
      log "got ${W}x${H} / ${D}s"
      # Accept if horizontal res >= 1080 and duration >= 20s
      OK=$(awk -v w="$W" -v d="$D" 'BEGIN{print (w>=1080 && d>=20) ? 1 : 0}')
      if [ "$OK" = "1" ]; then SRC_OK="yes"; echo "$u" > footage_source_url.txt; echo "${LICENSES[$i]}" > footage_license.txt; break; fi
    fi
    rm -f footage_src
  done
  [ -n "$SRC_OK" ] || { echo "[FAIL-FETCH] no usable footage"; exit 1; }
fi

ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate -of json footage_src > footage.json
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 footage_src)
WID=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 footage_src)
HEI=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 footage_src)
metric footage_source "$(cat footage_source_url.txt)"
metric footage_license "$(cat footage_license.txt)"
metric footage_resolution "${WID}x${HEI}"
metric footage_duration "$DUR"

# ---------- 2. Deterministic TTS narration (for measurable ASR) ----------
REF_TEXT="Welcome to the A I Video Lab. This narration was synthesized on a GitHub Actions runner. Whisper will transcribe it, and F Fmpeg will burn the subtitles back into the final vertical video."
printf '%s' "$REF_TEXT" > ref_text.txt
espeak-ng -v en-us -s 150 -p 40 -w narration_raw.wav "$REF_TEXT" || { echo "[FAIL-FETCH] espeak-ng failed"; exit 1; }
ffmpeg -y -v error -i narration_raw.wav -ar 48000 -ac 2 narration.wav
ND=$(ffprobe -v error -show_entries format=duration -of csv=p=0 narration.wav)
metric narration_duration "$ND"

# ---------- 3. Source-audio guard (may be silent or missing) ----------
if ffmpeg -y -v error -i footage_src -vn -ac 2 -ar 48000 src_audio.m4a 2>/dev/null && [ -s src_audio.m4a ]; then
  log "source audio track extracted"
  metric source_audio present
else
  log "source has NO usable audio - generating silence bed"
  ffmpeg -y -v error -f lavfi -i anullsrc=r=48000:cl=stereo -t 60 -c:a aac src_audio.m4a
  metric source_audio silence_generated
fi

echo "[FETCH-READY]"
