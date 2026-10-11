#!/usr/bin/env python3
"""R3: G11 style-locked impossibility - the relaxation ladder never tried a
style-density DOWNSHIFT.

Audit: 30 s requested -> 10 s delivered because the ladder only relaxed the
cps margin and the luma floor. cinematic 0.3-0.7 cps fits ~13 segs x ~2.3 s
= 30 s within the same cluster cap.

Fix contract:
  - ladder step "style_density_downshift" (one style step toward a sparser
    cuts band, every step logged) is attempted BEFORE declaring impossibility;
  - impossibility remains the LAST resort (note only after the ladder);
  - plan.cuts_band carries the effective (downshifted) band so gate G7
    measures against what was declared;
  - duration_chain states delivered vs requested and why (user-facing).

Probe reuses the E4 scarcity fixture (hard capacity, beat_montage, 30 s ask).
On pre-R3 HEAD the plan either delivers ~10-14 s with no downshift entry or
declares impossibility without trying the sparser bands -> FAILS.
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
        # hard scarcity: 9 bright 2s bands, luma floor 36 -> ~2 clean
        # 1s-windows per band, requesting 30s (the audit's shape)
        luma = []
        bright_bands = [(2.0, 4.0), (6.0, 8.0), (10.0, 12.0), (14.0, 16.0),
                        (18.0, 20.0), (22.0, 24.0), (26.0, 28.0), (30.0, 32.0),
                        (34.0, 36.0)]
        for i in range(80):
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
        requested = plan.get("requested_duration")
        relax = plan.get("relaxations") or []
        kinds = [x.get("kind") for x in relax]

        print(f"  delivered={delivered}s requested={requested}s")
        print(f"  relaxations: {json.dumps(relax)[:300]}")
        print(f"  cuts_band={plan.get('cuts_band')} (style band [1.2, 2.0])")

        if requested != 30.0:
            fail(f"fixture broke: requested_duration={requested} != 30")

        downshifts = [x for x in relax if x.get("kind") == "style_density_downshift"]
        if delivered >= 0.8 * 30.0:
            if not downshifts:
                ok(f"fidelity reached outright ({delivered}s) without a downshift "
                   f"- acceptable, ladder entry optional here")
            else:
                ok(f"downshift logged AND fidelity reached: {delivered}s >= 24s")
                if not any(x.get("to_band") for x in downshifts):
                    fail("downshift entries must carry from_band/to_band")
        else:
            # short delivery is only honest if the ladder TRIED the downshift
            # first (logged) and the impossibility note is present
            if not downshifts:
                fail(f"R3 present: delivered {delivered}s < 24s and the ladder "
                     f"never logged a style_density_downshift attempt (kinds: {kinds})")
            note = plan.get("target_impossible_note")
            if not note:
                fail(f"delivered {delivered}s < 24s with downshifts logged but NO "
                     f"target_impossible_note")
            ok(f"downshift attempted before impossibility: "
               f"{[x.get('to_band') for x in downshifts]} then honest note")

        # the declared band must be the effective one (G7 measures it)
        eff = plan.get("cuts_band")
        style_band = [1.2, 2.0]
        if downshifts and eff == style_band:
            fail("downshift logged but plan.cuts_band still the style band - "
                 "G7 would measure the downshifted density against [1.2, 2.0]")
        # delivered cps must sit inside the effective band (G7 consistency)
        if delivered and plan.get("cut_density_cps") is not None and eff:
            cps = float(plan["cut_density_cps"])
            if not (eff[0] <= cps <= eff[1]):
                fail(f"delivered cps {cps} outside the declared band {eff} - "
                     f"the downshift solve is inconsistent (G7 would RED)")
            ok(f"delivered cps {cps} inside the declared band {eff}")

        # user-facing duration chain must state delivered vs requested
        chain = plan.get("duration_chain") or {}
        if "requested" not in chain or "delivered" not in chain:
            fail("duration_chain missing requested/delivered (user-facing summary)")
        if downshifts and "note" not in chain:
            fail("duration_chain.note missing although a density downshift fired "
                 "- the user-facing summary must state why")

    print("R3 PROBE: PASS (density downshift in the ladder, impossibility last)")


if __name__ == "__main__":
    main()
