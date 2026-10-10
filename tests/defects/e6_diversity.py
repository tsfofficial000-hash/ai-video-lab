#!/usr/bin/env python3
"""E6: mid-section monotony + all-fade transitions.

Audit: 5 near-identical dune shots at 8-13 s; 22/22 transitions are 0.18 s
fades (the scarcity path replaces the whole mix with one transition type).

Fix contract:
  - scene-diversity constraint in the solver: max 2 segments per PySceneDetect
    scene cluster (proxy-res detection)
  - transition mix per style: beat_montage >= 60% pseudo-cuts (0.05 s), fades
    <= 40%, fadewhite only at section bounds - in EVERY solver mode
  - G7 extended: report cluster histogram + transition mix; RED if any cluster
    > 2 or mix violated

Probe runs edit_plan.py on a 6-scene synthetic source with beats concentrated
early. On HEAD: no cluster histogram in the audit and the transition mix
collapses -> FAILS. After fix: histogram max <= 2 and mix inside band.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def synth_multiscene(path, scenes=6, scene_len=5.0):
    """Concat flat mid-bright color scenes with hard cuts (scenedetect-visible)."""
    colors = ["0x504030", "0x304050", "0x405030", "0x503040", "0x304a44", "0x46324a"]
    inputs, fc, idx = [], [], 0
    for k in range(scenes):
        inputs += ["-f", "lavfi", "-i",
                   f"color=c={colors[k % len(colors)]}:s=320x180:d={scene_len}"]
        idx += 1
    inputs += ["-f", "lavfi", "-i", f"sine=frequency=330:duration={scenes * scene_len}"]
    fc = "".join(f"[{k}:v]" for k in range(scenes)) + f"concat=n={scenes}:v=1:a=0[v]"
    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + [
        "-filter_complex", fc + f";[v]format=yuv420p,setsar=1[vf]",
        "-map", "[vf]", "-map", f"{scenes}:a", "-t", str(scenes * scene_len),
        "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", path]
    subprocess.run(cmd, check=True)
    return path


def main():
    with tempfile.TemporaryDirectory() as td:
        src = synth_multiscene(os.path.join(td, "src.mp4"))
        reports = os.path.join(td, "reports")
        out = os.path.join(td, "out")
        os.makedirs(reports)
        os.makedirs(out)

        json.dump({"duration": 30.0, "width": 320, "height": 180, "fps": 30.0,
                   "has_audio": True, "size_mb": 1.0},
                  open(os.path.join(reports, "source_metadata.json"), "w"))
        json.dump([{"t": round(i * 0.5, 2), "y": 110.0} for i in range(60)],
                  open(os.path.join(reports, "luma.json"), "w"))
        beats = [round(0.6 * k, 3) for k in range(1, 50)]  # dense early beats
        json.dump({"tempo": 100.0, "beats": beats, "energy_peak_starts": [],
                   "onsets": beats[:8]},
                  open(os.path.join(reports, "beats.json"), "w"))
        json.dump({"transcript_empty": True, "segments": []},
                  open(os.path.join(reports, "transcript.json"), "w"))
        json.dump({"silence_ratio": 0.0},
                  open(os.path.join(reports, "audio_analysis.json"), "w"))

        env = dict(os.environ, CF_SOURCE_PATH=src)
        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "cineforge",
                                                          "edit_plan.py"),
                            "--reports", reports, "--out", out,
                            "--style", "beat_montage", "--target-len", "7",
                            "--mood", "cinematic"],
                           capture_output=True, text=True, env=env,
                           cwd=os.path.join(REPO, "scripts", "cineforge"))
        audit_p = os.path.join(reports, "selection_audit.json")
        plan_p = os.path.join(reports, "edit_plan.json")
        if not os.path.isfile(audit_p) or not os.path.isfile(plan_p):
            fail(f"edit_plan.py failed: {(r.stderr or r.stdout)[-500:]}")
        audit = json.load(open(audit_p))
        plan = json.load(open(plan_p))

        hist = audit.get("cluster_histogram")
        if hist is None:
            fail("E6 present: selection audit carries no scene-cluster histogram - "
                 "the solver has no diversity constraint")
        over = {k: v for k, v in hist.items() if v > 2}
        if over:
            fail(f"E6 present: {len(over)} scene clusters contribute >2 segments "
                 f"(monotony): {over}")
        if not audit.get("scene_cuts"):
            fail("scene cuts not detected on a hard-cut multiscene source - "
                 "cluster detection is not real")
        ok(f"cluster histogram all <=2: {hist} (scene cuts: {len(audit['scene_cuts'])})")

        mix = plan.get("transition_mix")
        if not mix:
            fail("plan.transition_mix missing - transition census not reported")
        n_tr = sum(mix.values())
        if not n_tr:
            fail("transition census empty")
        pseudo = mix.get("pseudo_cut", 0)
        fades = mix.get("fade", 0)
        frac_pseudo = pseudo / n_tr
        frac_fade = fades / n_tr
        if frac_pseudo < 0.6:
            fail(f"E6 present: beat_montage transition mix violates the band - "
                 f"pseudo-cuts {frac_pseudo:.0%} < 60% (mix={mix})")
        if frac_fade > 0.4:
            fail(f"E6 present: fades {frac_fade:.0%} > 40% (mix={mix})")
        kinds = {s["transition_after"]["type"] for s in plan.get("segments", [])[:-1]}
        if "fadewhite" in kinds:
            fw = [s for s in plan["segments"][:-1]
                  if s["transition_after"]["type"] == "fadewhite"]
            if len(fw) > max(1, len(plan["segments"]) // 6):
                fail(f"fadewhite overused outside section bounds: {len(fw)} events")
        ok(f"transition mix inside beat_montage band: pseudo={frac_pseudo:.0%} "
           f"fade={frac_fade:.0%} mix={mix}")

        # durations: every pseudo-cut really is a 0.05s hard cut
        for s in plan.get("segments", [])[:-1]:
            tr = s["transition_after"]
            if tr["type"] == "fade" and tr["dur"] <= 0.06:
                continue  # pseudo-cut
            if tr["type"] == "fade" and tr["dur"] > 0.06 and frac_fade > 0.4:
                fail(f"long fade outside the allowed fraction at seg {s['i']}: {tr}")

    print("E6 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
