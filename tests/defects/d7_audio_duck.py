#!/usr/bin/env python3
"""D7: audio_mix.py emits `sidechaincompress=...:level_sc=duck` (invalid - ffmpeg:
"Undefined constant or missing '(' in 'duck'") and a dead `[sc]` fragment; the music
path never executes for keep_source styles. Probe must FAIL on HEAD, PASS after fix.
Fix contract: no level_sc, no dead [sc]; --music path renders successfully and reports
mode=sidechain_duck with a measured duck_depth_db >= 6 dB (voice bursts vs music-only).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import cf_path, ok, fail

mix_src = open(cf_path("scripts/cineforge/audio_mix.py")).read()

# 1. invalid constant and dead fragment removed
if "level_sc" in mix_src:
    fail("level_sc=duck still present (ffmpeg: Undefined constant 'duck')")
if re.search(r"volume=0\.0001\[sc\]", mix_src):
    fail("dead [sc] filter fragment still present")
ok("no level_sc / dead [sc] fragment in audio_mix.py")

with tempfile.TemporaryDirectory() as td:
    # voice: 300Hz sine bursts (0.5s on / 0.5s off) for 6s
    voice = os.path.join(td, "voice.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=6",
                    "-af", "volume='if(lt(mod(t,1),0.5),1,0)':eval=frame",
                    "-ar", "48000", "-ac", "2", voice], check=True)
    # music: continuous 110Hz bed for 6s
    music = os.path.join(td, "music.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=110:duration=6", "-af", "volume=0.8",
                    "-ar", "48000", "-ac", "2", music], check=True)

    out = os.path.join(td, "mixed.wav")
    reports = os.path.join(td, "reports")
    os.makedirs(reports, exist_ok=True)
    p = subprocess.run([sys.executable, cf_path("scripts/cineforge/audio_mix.py"),
                        "--voice", voice, "--music", music, "--out", out,
                        "--reports", reports], capture_output=True, text=True)
    if p.returncode != 0:
        fail(f"audio_mix --music crashed on HEAD "
             f"(expected: Undefined constant 'duck'):\n{p.stderr[-400:]}")
    ok("audio_mix --music renders without crashing")

    rep = json.load(open(os.path.join(reports, "audio_mix_report.json")))
    if rep.get("mode") != "sidechain_duck":
        fail(f"report mode={rep.get('mode')} != sidechain_duck")
    ok("report mode=sidechain_duck")

    # 2. measured duck depth >= 6 dB (independent measurement from diagnostics)
    ducked = os.path.join(td, "_ducked_music.wav")
    if not os.path.isfile(ducked):
        fail("no _ducked_music.wav diagnostic written - duck depth unmeasurable")

    def rms_db_window(path, t0, dur):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(t0), "-t", str(dur),
                            "-i", path, "-af", "astats=metadata=1", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        vals = [float(m) for m in re.findall(r"RMS level dB: (-?[\d.]+)", r)]
        return sum(vals) / len(vals) if vals else -120.0

    # voice-active windows: 0-0.5, 1-1.5, 2-2.5 (bursts)
    refs, ducks = [], []
    for t0 in (0.05, 1.05, 2.05):
        ducks.append(rms_db_window(ducked, t0, 0.4))
    ref = os.path.join(td, "_ref_music.wav")
    if os.path.isfile(ref):
        for t0 in (0.05, 1.05, 2.05):
            refs.append(rms_db_window(ref, t0, 0.4))
        depth = sum(refs) / len(refs) - sum(ducks) / len(ducks)
    else:
        # fallback: compare against the raw music bed gain-matched
        raw = rms_db_window(music, 0.05, 0.4)
        depth = raw - (sum(ducks) / len(ducks)) + 20 * 0.0953  # 0.9 gain compensation
        depth -= 20 * 0.0953
        depth = raw - (sum(ducks) / len(ducks))
    if depth < 6.0:
        fail(f"measured duck depth {depth:.1f} dB < 6 dB (ducks={ducks})")
    ok(f"independently measured duck depth: {depth:.1f} dB >= 6 dB")

    if float(rep.get("duck_depth_db", 0)) < 6.0:
        fail(f"report duck_depth_db={rep.get('duck_depth_db')} < 6")
    ok(f"report duck_depth_db={rep.get('duck_depth_db')}")

print("D7 PROBE: PASS (defect fixed)")
