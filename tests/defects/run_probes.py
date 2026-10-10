#!/usr/bin/env python3
"""Probe runner: executes the mandated suite D1-D7 + E1-E7 (14 probes) and the
N1-N4 nits. A probe exiting 0 means the defect is FIXED; non-zero means the
defect is present (expected on pre-fix HEAD).
Exit codes: 0 = all pass (green repo), 1 = >=1 probe failed (defects present),
2 = >=1 probe crashed unexpectedly (infrastructure error)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = ["d1_blackdetect.py", "d2_delivery_bundle.py", "d3_selection.py",
          "d4_composite.py", "d5_grade_wiring.py", "d6_captions_check.py",
          "d7_audio_duck.py",
          "e1_bars.py", "e2_g4_measured.py", "e3_music_sources.py",
          "e4_target_fidelity.py", "e5_hook_candidates.py", "e6_diversity.py",
          "e7_endcard.py"]
NITS = ["nits.py"]


def run_list(names):
    rows, infra_err = [], False
    for p in names:
        r = subprocess.run([sys.executable, os.path.join(HERE, p)],
                           capture_output=True, text=True)
        status = "FIXED" if r.returncode == 0 else "PRESENT"
        if r.returncode not in (0, 1):
            infra_err = True
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        if r.returncode not in (0, 1):
            tail += " | stderr: " + (r.stderr.strip().splitlines() or [""])[-1][:80]
        rows.append((p, status, r.returncode, tail[:110]))
    return rows, infra_err


def main():
    rows, infra_err = run_list(PROBES)
    print(f"{'probe':28} {'defect':10} {'rc':>3}  last line")
    for name, status, rc, tail in rows:
        print(f"{name:28} {status:10} {rc:>3}  {tail}")
    n_present = sum(1 for _, s, _, _ in rows if s == "PRESENT")
    total = len(PROBES)
    print(f"\n{n_present}/{total} defects present, {total - n_present}/{total} fixed")

    n_rows, n_err = run_list(NITS)
    for name, status, rc, tail in n_rows:
        print(f"{name:28} {status:10} {rc:>3}  {tail}")
    n_fixed = sum(1 for _, s, _, _ in n_rows if s == "FIXED")
    print(f"nits: {n_fixed}/{len(NITS)}")

    if infra_err or n_err:
        return 2
    return 0 if (n_present == 0 and n_fixed == len(NITS)) else 1


if __name__ == "__main__":
    sys.exit(main())
