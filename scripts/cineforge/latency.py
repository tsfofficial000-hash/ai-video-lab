#!/usr/bin/env python3
"""Latency CLI: merge/print reports/latency.json; md table generator for LATENCY_REPORT.md."""
import argparse
import json

from utils import jload


def md_table(path):
    data = jload(path, {"stages": []})
    rows = ["| Stage | Status | Duration (s) | Bottleneck | Optimization |",
            "|---|---|---:|---|---|"]
    for s in data.get("stages", []):
        rows.append(f"| {s['stage_name']} | {s['status']} | {s['duration_seconds']} | "
                    f"{s.get('bottleneck_detected') or '-'} | {s.get('optimization_applied') or '-'} |")
    total = sum(s.get("duration_seconds") or 0 for s in data.get("stages", []))
    rows.append(f"| **TOTAL** | {len(data.get('stages', []))} stages | **{total:.1f}** | | |")
    return "\n".join(rows), total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    if a.md:
        table, total = md_table(f"{a.reports}/latency.json")
        print(table)
    else:
        print(json.dumps(jload(f"{a.reports}/latency.json", {}), indent=1))
