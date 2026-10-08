#!/usr/bin/env python3
"""Probe runner: executes d1..d7. A probe exiting 0 means the defect is FIXED;
non-zero means the defect is present (expected on pre-fix HEAD).
Exit codes: 0 = all pass (green repo), 1 = >=1 probe failed (defects present),
2 = >=1 probe crashed unexpectedly (infrastructure error)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = ["d1_blackdetect.py", "d2_delivery_bundle.py", "d3_selection.py",
          "d4_composite.py", "d5_grade_wiring.py", "d6_captions_check.py",
          "d7_audio_duck.py"]


def main():
    rows, infra_err = [], False
    for p in PROBES:
        r = subprocess.run([sys.executable, os.path.join(HERE, p)],
                           capture_output=True, text=True)
        status = "FIXED" if r.returncode == 0 else "PRESENT"
        if r.returncode not in (0, 1):
            infra_err = True
        rows.append((p, status, r.returncode,
                     (r.stdout.strip().splitlines() or [""])[-1][:90]))
    print(f"{'probe':26} {'defect':10} {'rc':>3}  last line")
    for name, status, rc, tail in rows:
        print(f"{name:26} {status:10} {rc:>3}  {tail}")
    n_present = sum(1 for _, s, _, _ in rows if s == "PRESENT")
    print(f"\n{n_present}/7 defects present, {7 - n_present}/7 fixed")
    if infra_err:
        return 2
    return 0 if n_present == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
