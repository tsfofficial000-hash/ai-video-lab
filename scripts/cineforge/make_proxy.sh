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

# fast proxy for analysis (square pixels - SAR-aware scaling produced odd widths
# like 853x480 that libx264 rejects, leaving a 0-byte proxy: the luma gate died)
ffmpeg -v error -y -i "$SRC" -vf "scale=480:270:force_original_aspect_ratio=decrease,setsar=1" \
  -c:v libx264 -preset veryfast -crf 26 -an "$WD/media/proxy.mp4"
[ -s "$WD/media/proxy.mp4" ] || { echo "FATAL: proxy.mp4 empty - luma gate would be dead"; exit 1; }
# active-picture detection (baked-in letterbox: e.g. 2.35:1 content inside 16:9)
CROP=$(ffmpeg -hide_banner -i "$SRC" -vf "cropdetect=limit=24:round=2:reset=0" -frames:v 90 -f null - 2>&1 | grep -ao "crop=[0-9:]*" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}' | cut -c6-)
if [ -n "$CROP" ]; then
  CW=$(echo "$CROP" | cut -d: -f1); CH=$(echo "$CROP" | cut -d: -f2)
  python3 - "$WD" "$CW" "$CH" <<'PY'
import json, sys
wd, cw, ch = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
p = f"{wd}/reports/source_metadata.json"
m = json.load(open(p))
iw, ih = m["width"], m["height"]
if cw <= iw * 0.97 and ch <= ih * 0.97:   # meaningful bars only
    m["active_crop"] = {"w": cw, "h": ch}
    json.dump(m, open(p, "w"), indent=1)
    print(f"active_crop: {cw}x{ch} (source {iw}x{ih})")
PY
fi
# per-scene bar map (E1): cropdetect per-frame on the proxy + scene segmentation
# -> reports/bar_map.json; edit_plan attaches a segment-level active_crop so
# scope AND full-frame shots render bar-free (meta-level crop stays for compat)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/bar_map.py" --proxy "$WD/media/proxy.mp4" \
  --out "$WD/reports/bar_map.json" --meta "$WD/reports/source_metadata.json" \
  || echo "WARN: bar map failed - segments fall back to meta-level active_crop"
# audio wav for analysis
ffmpeg -v error -y -i "$SRC" -vn -ac 1 -ar 22050 "$WD/media/audio.wav"
# contact sheet: 4x4 thumbnails
ffmpeg -v error -y -i "$SRC" -vf "fps=1/$(python3 -c "
import json;d=json.load(open('$WD/reports/source_metadata.json'));
print(max(1,int(d['duration']//16)))" 2>/dev/null || echo 5),scale=320:-2,tile=4x4" \
  -frames:v 1 "$WD/media/contact.jpg" || \
ffmpeg -v error -y -i "$SRC" -vf "select=eq(n\,0),scale=320:-2" -frames:v 1 "$WD/media/contact.jpg"
echo "ingest done: $(ls -la $WD/media/ | tail -3)"
