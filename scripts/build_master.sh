#!/usr/bin/env bash
# =============================================================================
# Shared FFmpeg "master" render: the complex edit WITHOUT subtitles.
#   trim 2 segments -> 9:16 vertical blurred-bg composite -> xfade crossfade
#   -> dynamic drawtext titles -> narration + source audio mix -> loudnorm
# Also produces refmix.m4a (audio-only reference used by Whisper in A/C/D).
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/fetch_footage.sh" || exit 1
cd "$ROOT/work" || exit 1

# shellcheck source=scripts/time_shim.sh
source "$ROOT/scripts/time_shim.sh"; WORK="$ROOT/work"; ensure_time

metric(){ echo "[METRIC] $1=$2" | tee -a metrics.txt; }

# ---------- 1. Audio-only reference mix (input to Whisper) ----------
if [ ! -s refmix.m4a ]; then
  ffmpeg -y -v error -i src_audio.m4a -i narration.wav -filter_complex "\
[0:a]asplit=2[sa0][sa1];\
[sa0]atrim=3:9,asetpts=PTS-STARTPTS[oa0];\
[sa1]atrim=12:18,asetpts=PTS-STARTPTS[oa1];\
[oa0][oa1]acrossfade=d=1[srcx];\
[1:a]adelay=300|300,apad,atrim=0:11,volume=1.4[nar];\
[srcx][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[mix]" \
  -map "[mix]" -c:a aac -b:a 192k refmix.m4a || { echo "[FAIL-MASTER] refmix render failed"; exit 1; }
  metric refmix_rendered yes
fi

# ---------- 2. Master video render (complex filtergraph) ----------
cat > filter_master.txt <<'FEOF'
[0:v]split=2[sA][sB];
[sA]trim=3:9,setpts=PTS-STARTPTS,fps=30[t0];
[sB]trim=12:18,setpts=PTS-STARTPTS,fps=30[t1];
[t0]split=2[p0a][p0b];
[t1]split=2[p1a][p1b];
[p0a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,boxblur=luma_radius=24:luma_power=2[bg0];
[p1a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,boxblur=luma_radius=24:luma_power=2[bg1];
[p0b]scale=1080:1920:force_original_aspect_ratio=decrease[fg0];
[p1b]scale=1080:1920:force_original_aspect_ratio=decrease[fg1];
[bg0][fg0]overlay=(W-w)/2:(H-h)/2,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='AI VIDEO LAB':fontsize=72:fontcolor=white:borderw=3:bordercolor=black@0.8:x=(w-text_w)/2:y=h*0.10:enable='between(t,0.3,3.5)'[v0];
[bg1][fg1]overlay=(W-w)/2:(H-h)/2,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='FFMPEG BASELINE':fontsize=52:fontcolor=white:borderw=3:bordercolor=black@0.8:x=(w-text_w)/2:y=h*0.10:enable='between(t,0,3)'[v1];
[v0][v1]xfade=transition=fade:duration=1:offset=5[vpre];
[2:a]asplit=2[sa0][sa1];
[sa0]atrim=3:9,asetpts=PTS-STARTPTS[oa0];
[sa1]atrim=12:18,asetpts=PTS-STARTPTS[oa1];
[oa0][oa1]acrossfade=d=1[srcx];
[1:a]adelay=300|300,apad,atrim=0:11,volume=1.4[nar];
[srcx][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]
FEOF
FILTER=$(tr -d '\n' < filter_master.txt)

if [ ! -s master.mp4 ]; then
  T0=$(date +%s)
  "$TIME_BIN" -v ffmpeg -y -v error \
    -i footage_src -i narration.wav -i src_audio.m4a \
    -filter_complex "$FILTER" -map "[vpre]" -map "[aout]" \
    -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
    -c:a aac -b:a 192k -movflags +faststart master.mp4 2> time_master.txt
  RC=$?
  [ $RC -eq 0 ] || { echo "--- ffmpeg stderr (tail) ---"; tail -15 time_master.txt; echo "[FAIL-MASTER] master render rc=$RC"; exit 1; }
  T1=$(date +%s)
  metric master_render_seconds "$((T1-T0))"
  awk -F': ' '/Maximum resident/{print "[METRIC] master_peak_rss_kb="$2; print "[METRIC] master_peak_rss_mb="int($2/1024)}' time_master.txt | tee -a metrics.txt
  awk -F': ' '/Elapsed \(wall/{gsub(/[ \t]/,"",$2); print "[METRIC] master_wall_clock="$2}' time_master.txt | tee -a metrics.txt
fi

ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of json master.mp4 > master_probe.json
MD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 master.mp4)
metric master_duration "$MD"
echo "[MASTER-READY]"
