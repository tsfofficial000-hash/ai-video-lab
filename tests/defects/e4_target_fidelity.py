#!/usr/bin/env python3
"""E4: requested duration silently halved (30 s requested -> 17.8 s delivered).

Audit: the scarcity solver is honest in logs but nothing surfaces it; the plan
records only the shrunken target and QC compares against it.

Fix contract:
  - plan records requested_duration (the user ask) beside target_duration (delivered)
  - declared relaxations (cps band lower edge, luma floor -6 with logged reason)
    are attempted and recorded in plan.relaxations
  - if still short: plan.target_impossible_note with max achievable per style density
  - gate G11 target-fidelity: delivered >= 0.80 x requested, silent shrink = RED

Probe runs edit_plan.py end-to-end on a synthetic scarcity source (few clean
candidates, requested 30 s). On HEAD the plan has no requested_duration and no
impossibility contract -> FAILS.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def synth_source(path, dur=40.0):
    vf = "gradients=s=320x180:d=%.1f:c0=0x204060:c1=0xF0D080,format=yuv420p" % dur
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=%.1f" % dur,
                    "-map", "0:v", "-map", "1:a", "-t", str(dur), "-r", "30",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", path], check=True)
    return path


def main():
    with tempfile.TemporaryDirectory() as td:
        src = synth_source(os.path.join(td, "src.mp4"))
        reports = os.path.join(td, "reports")
        out = os.path.join(td, "out")
        os.makedirs(reports)
        os.makedirs(out)

        json.dump({"duration": 40.0, "width": 320, "height": 180, "fps": 30.0,
                   "has_audio": True, "size_mb": 1.0},
                  open(os.path.join(reports, "source_metadata.json"), "w"))
        # 2fps luma profile: only ~1 clean 1s-window per 2s bright band -> hard scarcity
        luma = []
        bright_bands = [(2.0, 4.0), (6.0, 8.0), (10.0, 12.0), (14.0, 16.0),
                        (18.0, 20.0), (22.0, 24.0), (26.0, 28.0), (30.0, 32.0),
                        (34.0, 36.0)]
        for i in range(80):  # t = 0..39.5 step 0.5
            t = i * 0.5
            y = 110.0 if any(a <= t <= b for a, b in bright_bands) else 18.0
            luma.append({"t": t, "y": y})
        json.dump(luma, open(os.path.join(reports, "luma.json"), "w"))
        beats = [round(0.55 * k, 3) for k in range(1, 72)]
        json.dump({"tempo": 109.0, "beats": beats, "energy_peak_starts": [],
                   "onsets": beats[:10]},
                  open(os.path.join(reports, "beats.json"), "w"))
        json.dump({"transcript_empty": True, "segments": []},
                  open(os.path.join(reports, "transcript.json"), "w"))
        json.dump({"silence_ratio": 0.0},
                  open(os.path.join(reports, "audio_analysis.json"), "w"))

        env = dict(os.environ, CF_SOURCE_PATH=src)
        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "cineforge",
                                                          "edit_plan.py"),
                            "--reports", reports, "--out", out,
                            "--style", "beat_montage", "--target-len", "30",
                            "--mood", "cinematic"],
                           capture_output=True, text=True, env=env,
                           cwd=os.path.join(REPO, "scripts", "cineforge"))
        plan_p = os.path.join(reports, "edit_plan.json")
        if not os.path.isfile(plan_p):
            fail(f"edit_plan.py produced no plan: {(r.stderr or r.stdout)[-500:]}")
        plan = json.load(open(plan_p))
        delivered = plan.get("target_duration")

        if "requested_duration" not in plan:
            fail(f"E4 present: plan silently shrinks the request - no "
                 f"requested_duration recorded (target_duration={delivered}, "
                 f"user asked 30s). Scarcity log said: "
                 f"{[ln for ln in (r.stdout or '').splitlines() if 'scarcity' in ln][:1]}")
        if abs(plan["requested_duration"] - 30.0) > 0.01:
            fail(f"requested_duration={plan['requested_duration']} != 30")
        ok(f"plan records requested_duration=30 beside delivered={delivered}")

        if delivered >= 0.8 * 30.0:
            ok(f"target fidelity reached outright: {delivered}s >= 24s")
        else:
            note = plan.get("target_impossible_note")
            if not note:
                fail(f"E4 present: delivered {delivered}s < 0.8*30s with NO "
                     f"target_impossible_note - silent shrink")
            if "max_achievable" not in json.dumps(plan.get("target_impossible_note", "")) \
               and not isinstance(note, dict):
                fail(f"target_impossible_note must state the max achievable "
                     f"(got {note!r})")
            ok(f"honest impossibility declared: {str(note)[:140]}")

        # relaxations must be declared when used, never silent
        delivered_short = delivered < 0.8 * 30.0
        rel = plan.get("relaxations")
        if rel is None:
            fail("plan.relaxations missing - relaxation use must be declared, never silent")
        if not delivered_short and not rel:
            ok("no relaxations needed and none declared")
        print(f"  relaxations: {json.dumps(rel)[:220]}")

    print("E4 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
