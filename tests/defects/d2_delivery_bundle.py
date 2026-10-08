#!/usr/bin/env python3
"""D2: 11-final-delivery.yml copies reports/{latency,qc_report,media_manifest}.json from
the repo dir (empty in CI) with `|| true`; artifacts were downloaded into final/ etc.
Result: delivered bundle lacks all three reports. Probe must FAIL on HEAD, PASS after fix.
Fix contract: report files glob'd from downloaded artifact dirs; qc_report.json copy is
mandatory (set -e, no `|| true`); bundle carries the full G8 set."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import cf_path, ok, fail

yml = open(cf_path(".github/workflows/11-final-delivery.yml")).read()

# 1. no repo-dir copies of the three reports (the empty-source bug)
for name in ("latency.json", "qc_report.json", "media_manifest.json"):
    if re.search(rf"cp\s+reports/{re.escape(name)}\b", yml):
        fail(f"still copying reports/{name} from repo dir (empty in CI)")
ok("no repo-dir report copies remain")

# 2. reports resolved via glob from downloaded artifact dirs
for name in ("qc_report.json", "latency.json", "media_manifest.json"):
    if not re.search(rf"glob[^)]*{re.escape(name)}", yml, re.S):
        fail(f"{name} not resolved via glob from downloaded artifacts")
ok("all three reports glob-resolved from downloaded artifact dirs")

# 3. qc_report.json copy is mandatory (no `|| true` on its line)
for line in yml.splitlines():
    if "qc_report" in line and "cp" in line and "|| true" in line:
        fail(f"qc_report.json copy is still optional: {line.strip()}")
ok("qc_report.json copy is mandatory")

# 4. stage-01-assets downloaded (source of media_manifest.json)
if "stage-01-assets" not in yml:
    fail("stage-01-assets artifact not downloaded (media_manifest.json source)")
ok("stage-01-assets downloaded for media_manifest.json")

# 5. G8 bundle completeness
for f in ("contact_sheet.png", "aesthetic_report.md", "edit_plan.json", "final.mp4"):
    if f not in yml:
        fail(f"G8 bundle missing {f}")
ok("G8 bundle carries final.mp4/edit_plan/qc_report/latency/media_manifest/contact_sheet/aesthetic_report")

print("D2 PROBE: PASS (defect fixed)")
