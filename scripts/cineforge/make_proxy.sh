#!/usr/bin/env bash
# Stage 2: ingest + proxy. Usage: make_proxy.sh <source> <workdir>
# -> reports/source_metadata.json, media/proxy.mp4, media/audio.wav, media/contact.jpg
set -euo pipefail
SRC="$1"; WD="$2"
mkdir -p "$WD/reports" "$WD/media"

ffprobe -v error -print_format json -show_format -show_streams "$SRC" > "$WD/reports/_probe.json"
python3 - "$WD" <<'PY'
import json, sys, os
wd = sys.argv[1]
d = json.load(open(f"{wd}/reports/_probe.json"))
v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
meta = {
    "duration": float(d["format"]["duration"]),
    "resolution": f"{v['width']}x{v['height']}" if v else None,
    "width": v["width"] if v else None,
    "height": v["height"] if v else None,
    "fps": eval(v["r_frame_rate"]) if v else None,
    "video_codec": v["codec_name"] if v else None,
    "bitrate": int(d["format"].get("bitrate", 0)),
    "audio_channels": a["channels"] if a else 0,
    "audio_codec": a["codec_name"] if a else None,
    "has_audio": a is not None,
    "size_mb": round(int(d["format"]["size"]) / 1e6, 1),
}
json.dump(meta, open(f"{wd}/reports/source_metadata.json", "w"), indent=1)
print(json.dumps(meta))
PY

# fast proxy for analysis (keep aspect, cap height 480)
ffmpeg -v error -y -i "$SRC" -vf "scale=-2:'min(480,ih)':force_original_aspect_ratio=decrease" \
  -c:v libx264 -preset veryfast -crf 26 -an "$WD/media/proxy.mp4" || true
# audio wav for analysis
ffmpeg -v error -y -i "$SRC" -vn -ac 1 -ar 22050 "$WD/media/audio.wav"
# contact sheet: 4x4 thumbnails
ffmpeg -v error -y -i "$SRC" -vf "fps=1/$(python3 -c "
import json;d=json.load(open('$WD/reports/source_metadata.json'));
print(max(1,int(d['duration']//16)))" 2>/dev/null || echo 5),scale=320:-2,tile=4x4" \
  -frames:v 1 "$WD/media/contact.jpg" || \
ffmpeg -v error -y -i "$SRC" -vf "select=eq(n\,0),scale=320:-2" -frames:v 1 "$WD/media/contact.jpg"
echo "ingest done: $(ls -la $WD/media/ | tail -3)"
