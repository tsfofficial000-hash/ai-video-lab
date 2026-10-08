#!/usr/bin/env python3
"""Mood-based royalty-free music acquisition (FreePD CC0) with verified fallbacks.
Usage: fetch_music.py --mood cinematic [--url URL] --out media/music.mp3 --manifest reports/media_manifest.json
"""
import argparse
import json
import os
import subprocess
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/132.0"}
FREEPD = "https://freepd.com/music/"


def dl(url, dest, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(dest)


def probe_ok(path):
    try:
        d = json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", path]).decode())
        return float(d["format"]["duration"]) > 20
    except Exception:
        return False


def _has_audio(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "stream=codec_type", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout
        return "audio" in out
    except Exception:
        return False


def _heal_container(path):
    """Re-mux/re-encode via forced mp3 demuxer when the container confuses probes."""
    fixed = path + ".fixed.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "mp3", "-i", path,
                        "-c:a", "libmp3lame", "-b:a", "128k", fixed],
                       capture_output=True, text=True)
    if r.returncode == 0 and _has_audio(fixed):
        os.replace(fixed, path)
        return True
    if os.path.isfile(fixed):
        os.remove(fixed)
    return False


def synth_pad(dest, seconds=180):
    """Fallback: CC0-equivalent generated ambient pad (no third-party rights)."""
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", "sine=frequency=110:duration=%d" % seconds,
           "-f", "lavfi", "-i", "sine=frequency=165.2:duration=%d" % seconds,
           "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.04:duration=%d" % seconds,
           "-filter_complex",
           "[0:a]volume=0.35[a0];[1:a]volume=0.22[a1];[2:a]lowpass=f=400,volume=0.18[a2];"
           "[a0][a1][a2]amix=inputs=3:duration=longest,tremolo=f=0.15:d=0.4,"
           "afade=t=in:d=4,afade=t=out:st=%d:d=6,aformat=channel_layouts=stereo" % (seconds - 8),
           "-c:a", "libmp3lame", "-b:a", "128k", dest]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mood", default="cinematic")
    ap.add_argument("--url", default=None, help="user-provided music URL overrides mood")
    ap.add_argument("--out", default="media/music.mp3")
    ap.add_argument("--manifest", default="reports/media_manifest.json")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    entry = {"license": None, "mood": a.mood, "title": None, "url": None,
             "attribution_required": False, "safe_for_shorts": True}

    if a.url:
        try:
            sz = dl(a.url, a.out)
            ok = probe_ok(a.out)
            entry.update({"license": "user-provided (verify rights before publishing)",
                          "title": os.path.basename(a.url), "url": a.url,
                          "safe_for_shorts": ok, "bytes": sz})
            if ok:
                print(json.dumps({"status": "ok", "via": "user_url", **entry}))
                _write(a.manifest, "music", entry)
                return
        except Exception as e:
            print(f"user url failed: {e}", flush=True)

    cfg = json.load(open("configs/music_moods.json"))
    for name in cfg["moods"].get(a.mood, cfg["moods"]["cinematic"]):
        url = FREEPD + name.replace(" ", "%20")
        try:
            sz = dl(url, a.out)
            if probe_ok(a.out):
                entry.update({"license": "CC0 (FreePD.com, Kevin MacLeod et al.)",
                              "title": name, "url": url, "bytes": sz})
                print(json.dumps({"status": "ok", "via": "freepd", **entry}))
                _write(a.manifest, "music", entry)
                return
        except Exception as e:
            print(f"candidate failed: {name}: {type(e).__name__}", flush=True)

    synth_pad(a.out)
    if not _has_audio(a.out):
        # unseeded noise sources can yield containers some probes misparse - self-heal
        if not _heal_container(a.out):
            raise SystemExit("synth pad produced no decodable audio")
    entry.update({"license": "generated in-pipeline (no third-party rights)",
                  "title": "generated_ambient_pad.mp3", "url": None, "bytes": os.path.getsize(a.out)})
    print(json.dumps({"status": "ok", "via": "synth_fallback", **entry}))
    _write(a.manifest, "music", entry)


def _write(manifest, key, val):
    data = {}
    if os.path.isfile(manifest):
        try:
            data = json.load(open(manifest))
        except Exception:
            pass
    data[key] = val
    os.makedirs(os.path.dirname(manifest) or ".", exist_ok=True)
    json.dump(data, open(manifest, "w"), indent=1)


if __name__ == "__main__":
    main()
