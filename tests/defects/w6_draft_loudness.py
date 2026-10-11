#!/usr/bin/env python3
"""W6: loudness self-heal on the DRAFT path.

Audit W4 evidence: the E-sweep motivational draft (38108787972) shipped
outI=-14.8 (G6 draft variance) while production self-heals - because those
drafts ran BEFORE commit 3a892a6 added the verify-and-correct loop to
audio_mix.py. The loop is shared code: 98's stage-07 invokes the SAME
audio_mix.py as 07-audio-mix, so drafts now measure their own output and
apply corrective loudnorm passes (max 2, each logged).

Fix contract:
  - the draft path provably runs the self-heal (shared entrypoint) and its
    measured output lands in the production band [-17,-15];
  - the corrective-pass primitive (measure -> loudnorm -> re-measure, the
    exact commands the loop uses) demonstrably pulls a hot mix into band;
  - the iterate gate print LABELS the draft G6 band explicitly (declared
    wider [-18,-14], non-fatal in the draft loop) - variance is never
    silently ignored; the production band stays enforced at 99/stage-10.

Probe exit 0 = contract holds; exit 1 = defect present.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, cf_path


def measure_out_i(path):
    """Same measurement the loop uses (ebur128 integrated I)."""
    eb = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                         "-af", "ebur128=peak=true", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    matches = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", eb)
    return float(matches[-1]) if matches else None


def synth_voice(path, dur=12.0):
    vf = "gradients=s=320x180:d=%.1f:c0=0x303050:c1=0xE0E0FF,format=yuv420p" % dur
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
                    "-f", "lavfi", "-i",
                    "sine=frequency=330:duration=%.1f:sample_rate=48000" % dur,
                    "-map", "0:v", "-map", "1:a", "-t", str(dur),
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", path], check=True)
    return path


def main():
    # ---- 1) WIRING: the draft mix path runs the self-healing module ----
    wf98 = open(cf_path(".github/workflows/98-iterate.yml")).read()
    if not re.search(r"python3\s+audio_mix\.py", wf98):
        fail("W6 present: 98's stage-07 does not invoke audio_mix.py - the "
             "draft path would miss the verify-and-correct loop entirely")
    mix_src = open(cf_path("scripts/cineforge/audio_mix.py")).read()
    if "loudness correction #" not in mix_src or "loudness_corrections" not in mix_src:
        fail("audio_mix.py lost the verify-and-correct loop (3a892a6 "
             "regression) - drafts would ship uncorrected outI again")
    if "draft G6" not in wf98 or "loudness_corrections" not in wf98:
        fail("W6 present: the iterate gate print does not LABEL the draft G6 "
             "band - variance was silently swallowed in the draft loop")
    ok("98 stage-07 runs the self-healing audio_mix.py; the gate print "
       "labels the draft G6 band explicitly")

    with tempfile.TemporaryDirectory() as td:
        # ---- 2) END-TO-END on the draft invocation: measured + in band ----
        voice = synth_voice(os.path.join(td, "source.mp4"))
        music = os.path.join(td, "music.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=220:duration=12:sample_rate=48000",
                        "-c:a", "pcm_s16le", music], check=True)
        reports = os.path.join(td, "reports")
        os.makedirs(reports, exist_ok=True)
        plan = {"audio_ducking_plan": {"mode": "sidechain_duck", "duck_to_db": -14},
                "segments": [], "target_duration": 12.0}
        json.dump(plan, open(os.path.join(reports, "edit_plan.json"), "w"))
        r = subprocess.run(
            [sys.executable, cf_path("scripts/cineforge/audio_mix.py"),
             "--voice", voice, "--music", music,
             "--plan", os.path.join(reports, "edit_plan.json"),
             "--out", os.path.join(td, "mixed_audio.wav"),
             "--reports", reports],
            capture_output=True, text=True, cwd=td)
        rep_p = os.path.join(reports, "audio_mix_report.json")
        if not os.path.isfile(rep_p):
            fail(f"audio_mix.py produced no report: "
                 f"{(r.stderr or r.stdout)[-300:]}")
        rep = json.load(open(rep_p))
        out_i = rep.get("output_i")
        if out_i is None:
            fail("draft-path mix did not MEASURE its output (output_i null) - "
                 "the self-heal's verify leg is dead on the draft path")
        if not (-17.0 <= out_i <= -15.0):
            fail(f"W6 present: draft-path mix landed at outI={out_i} outside "
                 f"the production band [-17,-15] (corrections: "
                 f"{rep.get('loudness_corrections')})")
        if "loudness_corrections" not in rep:
            fail("report must always carry the loudness_corrections array "
                 "(each corrective pass is evidence)")
        ok(f"draft-path invocation self-verifies: outI={out_i} in [-17,-15], "
           f"corrections logged={len(rep.get('loudness_corrections') or [])}")

        # ---- 3) HEAL PRIMITIVE: a hot mix is pulled into band ----
        hot = os.path.join(td, "hot.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=10:sample_rate=48000",
                        "-af", "volume=26dB", "-c:a", "pcm_s16le", hot],
                       check=True)
        hot_i = measure_out_i(hot)
        if hot_i is None or hot_i <= -15.0:
            fail(f"fixture must start OUT of band (hot outI={hot_i})")
        healed = os.path.join(td, "healed.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", hot, "-af",
                        "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000",
                        "-ac", "2", healed], check=True, capture_output=True)
        healed_i = measure_out_i(healed)
        if healed_i is None or not (-17.0 <= healed_i <= -15.0):
            fail(f"corrective loudnorm pass must land in band (got {healed_i})")
        ok(f"corrective-pass primitive: hot {hot_i:.1f} LUFS -> healed "
           f"{healed_i:.1f} LUFS (the loop's exact command)")

    print("W6 PROBE: PASS (draft path self-verifies + self-heals; draft G6 "
          "band labelled, production band enforced)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"W6 PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
