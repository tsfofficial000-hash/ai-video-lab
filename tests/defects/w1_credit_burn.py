#!/usr/bin/env python3
"""W1: the shipped cineforge-v2.1 final carries NO on-screen CC-BY credit,
while FINAL_REPORT_v2.1.md claims "attribution burned on-screen".

Root cause chain (audit-verified on the shipped run 38109649950 artifacts):
  stage-06 (06-edit-decision.yml) downloads only stage-02..05 artifacts, so
  reports/media_manifest.json never reaches edit_plan.py -> music_meta={}.
  edit_plan.py then writes plan.music_credit=None (verified:
  reports/cineforge/run-38109649950/edit_plan.json), captions.py never
  emits the music_credit Dialogue event, and the published Short ships a
  CC-BY track with no attribution-with-the-work. Repo-side credit text
  (MEDIA_LICENSES.md) does not satisfy the E3 contract.

Fix contract:
  a) stage-01 uploads a tiny stage-01-manifest artifact; stage-06 downloads
     it so plan.music_credit == manifest.music.credit;
  b) QC pixel-verifies the credit line in the outro band: structural
     (ass carries a music_credit Dialogue event) + differential re-burn
     (bottom band, credit window) - unmeasurable is RED;
  c) gates G10 asserts the full attribution chain when the manifest says
     attribution_required;
  d) the false FINAL_REPORT lines are corrected (v2.1.1 first carries it).

Probe exit 0 = contract holds; exit 1 = defect present.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module, synth_video, pick_font, cf_path, REPO

CREDIT = ("Music: Healing - Kevin MacLeod (incompetech.com), "
          "Licensed under CC BY 4.0")


def fabricate_reports(reports):
    """Minimal report set edit_plan.py accepts (e4 pattern) + CC-BY manifest."""
    os.makedirs(reports, exist_ok=True)
    json.dump({"duration": 40.0, "width": 320, "height": 180, "fps": 30.0,
               "has_audio": True, "size_mb": 1.0},
              open(os.path.join(reports, "source_metadata.json"), "w"))
    luma = []
    bright = [(2.0, 4.0), (6.0, 8.0), (10.0, 12.0), (14.0, 16.0), (18.0, 20.0),
              (22.0, 24.0), (26.0, 28.0), (30.0, 32.0), (34.0, 36.0)]
    for i in range(80):
        t = i * 0.5
        luma.append({"t": t, "y": 110.0 if any(a <= t <= b for a, b in bright)
                     else 18.0})
    json.dump(luma, open(os.path.join(reports, "luma.json"), "w"))
    beats = [round(0.55 * k, 3) for k in range(1, 72)]
    json.dump({"tempo": 109.0, "beats": beats, "energy_peak_starts": [],
               "onsets": beats[:10]},
              open(os.path.join(reports, "beats.json"), "w"))
    json.dump({"transcript_empty": True, "segments": []},
              open(os.path.join(reports, "transcript.json"), "w"))
    json.dump({"silence_ratio": 0.0},
              open(os.path.join(reports, "audio_analysis.json"), "w"))
    json.dump({"music": {"via": "incompetech_ccb", "title": "Healing",
                         "license": "CC BY 4.0 (incompetech.com, Kevin MacLeod)",
                         "attribution_required": True, "credit": CREDIT,
                         "mood": "cinematic", "safe_for_shorts": True}},
              open(os.path.join(reports, "media_manifest.json"), "w"))


def run_edit_plan(td, reports):
    out = os.path.join(td, "out")
    os.makedirs(out, exist_ok=True)
    r = subprocess.run(
        [sys.executable, cf_path("scripts/cineforge/edit_plan.py"),
         "--reports", reports, "--out", out,
         "--style", "beat_montage", "--target-len", "30", "--mood", "cinematic"],
        capture_output=True, text=True, cwd=td,
        env=dict(os.environ, CF_SOURCE_PATH=os.path.join(td, "src.mp4")))
    plan_p = os.path.join(reports, "edit_plan.json")
    if not os.path.isfile(plan_p):
        fail(f"edit_plan.py produced no plan: {(r.stderr or r.stdout)[-400:]}")
    return json.load(open(plan_p))


def run_captions(td, reports):
    """captions.py from a neutral CWD - CWD-relative outputs stay in td."""
    ass_p = os.path.join(td, "captions.ass")
    tr = os.path.join(reports, "transcript.json")
    plan_p = os.path.join(reports, "edit_plan.json")
    r = subprocess.run(
        [sys.executable, cf_path("scripts/cineforge/captions.py"),
         "--transcript", tr, "--plan", plan_p, "--style", "minimal_clean",
         "--out", ass_p, "--resolution", "540x960"],
        capture_output=True, text=True, cwd=td)
    if not os.path.isfile(ass_p):
        fail(f"captions.py produced no ass: {(r.stderr or r.stdout)[-400:]}")
    return ass_p


def ass_dialogues(ass_p):
    rows = []
    for ln in open(ass_p, errors="ignore"):
        if ln.startswith("Dialogue:"):
            parts = ln.rstrip("\n").split(",", 9)
            if len(parts) >= 10:
                text = re.sub(r"\{[^}]*\}", "", parts[9]).strip()
                rows.append((parts[1], parts[2], text))
    return rows


def ass_seconds(ts_str):
    h, m, s = ts_str.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def tiny_ass(path, with_credit=True, dur=6.0):
    """Production-shaped ass at 540x960: header, Cine style, caption events
    and (optionally) the outro credit event per captions.py semantics
    (bottom-anchored pos at h*0.962, fs>=28, alpha&H33)."""
    fam = {"Montserrat": "Montserrat", "Anton": "Anton"}.get(
        os.path.basename(pick_font()).split("-")[0], "DejaVu Sans")
    captions = load_module("captions_under_test_w1",
                           "scripts/cineforge/captions.py")
    hdr = captions.ASS_HEADER.format(
        w=540, h=960, cap_font=fam, hook_font=fam, size=96,
        primary="&H00FFFFFF", outline="&H00000000", outline_w=5, shadow=3,
        ml=32, mr=32, mv=240, hook_size=150)
    events = [f"Dialogue: 0,0:00:00.40,0:00:01.20,Cine,,0,0,0,,A CAPTION LINE"]
    if with_credit:
        c_y = int(960 * 0.962)
        tags = (r"{\pos(" + f"{540 // 2},{c_y})" + r"\fs28" + r"\alpha&H33&}")
        c0, c1 = max(0.0, dur - 2.4), max(0.5, dur - 0.2)

        def ts(t):
            hh = int(t // 3600)
            mm = int((t % 3600) // 60)
            ss = t % 60
            return f"{hh}:{mm:02d}:{ss:05.2f}"
        events.append(f"Dialogue: 1,{ts(c0)},{ts(c1)},Cine,,0,0,0,,{tags}{CREDIT}")
    open(path, "w").write(hdr + "\n" + "\n".join(events) + "\n")
    return path


def burn(src, ass, fontsdir, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                    "-vf", f"ass={ass}:fontsdir={fontsdir}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "copy", dest], check=True)
    return dest


def credit_verdict(res):
    return next((r for r in res if r["check"] == "music_credit_on_screen"), None)


def main():
    qc = load_module("qc_under_test_w1", "scripts/cineforge/qc.py")

    # ---- 1) WORKFLOW WIRING: the manifest must reach edit_plan.py ----
    wf06 = open(cf_path(".github/workflows/06-edit-decision.yml")).read()
    wf01 = open(cf_path(".github/workflows/01-asset-download.yml")).read()
    downloaded = re.findall(r"name:\s*(stage-[\w-]+)", wf06)
    if not ("stage-01-manifest" in downloaded or "stage-01-assets" in downloaded):
        fail(f"W1 present: stage-06 downloads only {downloaded} - the media "
             f"manifest never reaches edit_plan.py, plan.music_credit stays "
             f"None, and the CC-BY credit is never burned")
    ok(f"stage-06 pulls the stage-01 manifest (downloads: {downloaded})")
    if "stage-01-manifest" not in wf01:
        fail("W1 present: 01-asset-download.yml does not upload the tiny "
             "stage-01-manifest artifact (reports/media_manifest.json)")
    ok("stage-01 uploads the stage-01-manifest artifact")

    with tempfile.TemporaryDirectory() as td:
        # synthetic 40s source for edit_plan's ffprobe/duration math
        synth_video(os.path.join(td, "src.mp4"), dur=40.0, w=320, h=180)
        reports = os.path.join(td, "reports")
        fabricate_reports(reports)

        # ---- 2) PLAN: attribution_required must flow into music_credit ----
        plan = run_edit_plan(td, reports)
        if plan.get("music_credit") != CREDIT:
            fail(f"W1 present: plan.music_credit is "
                 f"{plan.get('music_credit')!r} != manifest credit "
                 f"(the shipped v2.1 defect: credit never reaches the plan)")
        ok("plan.music_credit == manifest.music.credit")

        # ---- 3) ASS: captions.py must emit the credit Dialogue event ----
        ass_p = run_captions(td, reports)
        rows = ass_dialogues(ass_p)
        credit_rows = [r for r in rows if CREDIT in r[2]]
        if not credit_rows:
            fail(f"W1 present: no music_credit Dialogue event in the generated "
                 f"ass ({len(rows)} events) - attribution never burns")
        plan_dur = float(plan.get("target_duration") or 0)
        c0 = ass_seconds(credit_rows[0][0])
        if not (plan_dur - 3.0 <= c0 <= plan_dur):
            fail(f"credit event must sit in the outro (start {c0:.2f}s vs plan "
                 f"total {plan_dur:.2f}s)")
        ok(f"ass carries the credit event at {c0:.2f}-{ass_seconds(credit_rows[0][1]):.2f}s")

        # ---- 4) PIXEL: QC verifies the credit in the outro band ----
        with tempfile.TemporaryDirectory() as pd:
            qc.REPO_ROOT = pd
            fontsdir = os.path.dirname(pick_font())
            os.environ["CF_FONTS_DIR"] = fontsdir
            base = synth_video(os.path.join(pd, "base.mp4"), dur=6.0,
                               w=540, h=960, bright=True)
            ass_full = tiny_ass(os.path.join(pd, "full.ass"), with_credit=True)
            ass_noc = tiny_ass(os.path.join(pd, "nocredit.ass"), with_credit=False)
            qplan = {"music_credit": CREDIT, "caption_style": None,
                     "target_duration": 6.0, "resolution": "540x960", "fps": 30}
            qrep = os.path.join(pd, "reports")
            os.makedirs(qrep, exist_ok=True)

            # 4a) credit burned -> differential in the outro band is idempotent
            vid_ok = burn(base, ass_full, fontsdir, os.path.join(pd, "credited.mp4"))
            res, _, _ = qc.check(vid_ok, qplan, qrep, ass=ass_full,
                                 fontsdir=fontsdir)
            v = credit_verdict(res)
            if v is None:
                fail("music_credit_on_screen check missing from QC output")
            if not v["passed"]:
                fail(f"credited final must PASS the outro-band differential "
                     f"(detail: {v['detail']})")
            ok("credited final passes the outro-band pixel verification")

            # 4b) credit NOT burned (the shipped v2.1 artifact state) -> RED
            vid_no = burn(base, ass_noc, fontsdir, os.path.join(pd, "uncredited.mp4"))
            res2, _, _ = qc.check(vid_no, qplan, qrep, ass=ass_full,
                                  fontsdir=fontsdir)
            v2 = credit_verdict(res2)
            if v2 is None or v2["passed"]:
                fail(f"W1 present: a final WITHOUT the burned credit passes QC "
                     f"(detail: {v2['detail'] if v2 else 'check absent'})")
            ok(f"uncredited final correctly REDs: {v2['detail'][:80]}")

            # 4c) ass lacks the credit event (actual v2.1 production state) -> RED
            res3, _, _ = qc.check(base, qplan, qrep, ass=ass_noc,
                                  fontsdir=fontsdir)
            v3 = credit_verdict(res3)
            if v3 is None or v3["passed"]:
                fail(f"W1 present: an ass without a credit event must make the "
                     f"check RED (unmeasurable = RED), got "
                     f"{v3['detail'] if v3 else 'check absent'}")
            ok("ass without credit event REDs (structural leg of the check)")

            # 4d) no attribution owed -> check is n/a, not red
            res4, _, _ = qc.check(base, dict(qplan, music_credit=None), qrep,
                                  ass=ass_noc, fontsdir=fontsdir)
            v4 = credit_verdict(res4)
            if v4 is None or not v4["passed"] or "n/a" not in v4["detail"]:
                fail(f"no-credit plans must skip via n/a "
                     f"(got: {v4['detail'] if v4 else 'absent'})")
            ok("no-attribution plans skip the check (n/a)")

    print("W1 PROBE: PASS (manifest wiring + plan credit + ass event + "
          "outro-band pixel verification all hold)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"W1 PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
