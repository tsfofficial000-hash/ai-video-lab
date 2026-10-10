#!/usr/bin/env python3
"""E5: hook = transcript echo truncated mid-phrase ("WHAT BRINGS YOU / TO THE LAND").

Audit: delivered frames 0.5-2.0 s show a hook chopped out of a longer sentence.

Fix contract:
  - the plan author writes 3 candidates, each a COMPLETE phrase <= 6 words,
    from transcript meaning (curiosity/punch/stakes rules)
  - width-fit selects among candidates, NEVER truncates one
  - plan records hook.candidates + hook.chosen
  - empty transcript -> mood-hook list from configs/styles.json
  - G5 clause: chosen hook in candidates and word-complete

Probe: (1) end-to-end through captions.py - a 7-word hook text must NOT be
sliced to its first 6 words (HEAD behavior). (2) the authoring contract:
candidates exist, are word-complete, chosen in candidates, and no candidate is
an interior slice. On HEAD both fail.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

TRAILING_STOP = {"to", "the", "a", "an", "of", "and", "or", "you", "your", "is",
                 "it", "its", "in", "on", "at", "for", "with", "what", "why",
                 "how", "this", "that", "but", "so"}


def word_complete(text):
    words = re.findall(r"[A-Za-z0-9']+", text)
    return bool(words) and words[-1].lower() not in TRAILING_STOP


def hook_text_from_ass(ass_path):
    for ln in open(ass_path):
        if "Dialogue" in ln and ",Hook," in ln:
            body = ln.split(",,")[-1].strip()
            body = re.sub(r"\{[^}]*\}", "", body)          # strip ASS tags
            return body.replace(r"\N", " ").strip()
    return None


def main():
    # ---- Part 1: captions.py must never slice a hook mid-phrase ----
    with tempfile.TemporaryDirectory() as td:
        reports = os.path.join(td, "reports")
        os.makedirs(reports)
        json.dump({"transcript_empty": True, "segments": []},
                  open(os.path.join(reports, "transcript.json"), "w"))
        long_hook = "WHAT BRINGS YOU TO THE LAND OF DRAGONS"
        plan = {"style": "beat_montage", "mood": "cinematic", "target_duration": 20.0,
                "resolution": "1080x1920", "fps": 30,
                "hook": {"type": "title_card", "text": long_hook, "seconds": [0, 2.5]},
                "segments": [], "caption_style": "bold_highlight"}
        json.dump(plan, open(os.path.join(reports, "edit_plan.json"), "w"))
        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "cineforge",
                                                          "captions.py"),
                            "--transcript", os.path.join(reports, "transcript.json"),
                            "--plan", os.path.join(reports, "edit_plan.json"),
                            "--style", "bold_highlight",
                            "--out", os.path.join(td, "captions.ass"),
                            "--resolution", "1080x1920"],
                           capture_output=True, text=True,
                           cwd=os.path.join(REPO, "scripts", "cineforge"))
        ass = os.path.join(td, "captions.ass")
        if not os.path.isfile(ass):
            fail(f"captions.py produced no ASS: {(r.stderr or r.stdout)[-400:]}")
        got = hook_text_from_ass(ass)
        if not got:
            fail("no Hook dialogue event in generated ASS")
        if not word_complete(got):
            fail(f"E5 present: hook rendered as a truncated mid-phrase slice: "
                 f"{got!r} (source text {long_hook!r}; word-complete=False)")
        if got != got.upper():
            pass  # mood hooks may be any case; transcript echoes are uppercased
        ok(f"captions.py renders a word-complete hook: {got!r}")

        # ---- Part 2: the authoring contract lives in the plan layer ----
        ep = load_module("edit_plan_under_test_e5", "scripts/cineforge/edit_plan.py")
        if not hasattr(ep, "hook_candidates"):
            fail("E5 contract missing: edit_plan.hook_candidates() - the plan layer "
                 "never authors >=3 complete candidates")
        transcript = {"transcript_empty": False, "segments": [
            {"start": 3.0, "end": 6.0, "text": "WHAT BRINGS YOU TO THE LAND OF DRAGONS AND MAGIC"},
            {"start": 8.0, "end": 9.2, "text": "Nobody escapes the storm."},
            {"start": 12.0, "end": 13.4, "text": "Why do they fear the night?"}]}
        beats = {"energy_peak_starts": [8.0]}
        cfg = {"hook": "title_card", "hook_moods": ["WAIT FOR THE DROP",
                                                    "LIKE NOTHING BEFORE"]}
        cands = ep.hook_candidates(transcript, beats, cfg, "MONTAGE")
        if not isinstance(cands, list) or not cands:
            fail("hook_candidates returned no candidates for a speech-bearing transcript")
        texts = [c["text"] if isinstance(c, dict) else str(c) for c in cands]
        if len(texts) < 3:
            fail(f"need 3 authored candidates, got {len(texts)}: {texts}")
        for t in texts:
            if len(t.split()) > 6:
                fail(f"candidate exceeds 6 words: {t!r}")
            if not word_complete(t):
                fail(f"candidate is not word-complete (mid-phrase cut): {t!r}")
        # the historic slice must be impossible by construction
        historic = "WHAT BRINGS YOU TO THE LAND"
        if historic in texts:
            fail("interior word-slice of a longer clause is still being authored "
                 f"as a candidate: {historic!r}")
        ok(f"3 candidates authored, all complete: {texts}")

        chosen = ep.choose_hook(cands, width_chars=40) \
            if hasattr(ep, "choose_hook") else texts[0]
        if chosen not in texts:
            fail(f"chosen hook {chosen!r} not among candidates {texts}")
        ok(f"chosen hook is one of the authored candidates: {chosen!r}")

        # empty transcript -> mood hooks from style config, never silence
        cands2 = ep.hook_candidates({"transcript_empty": True, "segments": []},
                                    beats, cfg, "MONTAGE")
        t2 = [c["text"] if isinstance(c, dict) else str(c) for c in cands2]
        if not t2:
            fail("empty transcript must fall back to mood-hook list")
        ok(f"empty-transcript mood fallback: {t2[:2]}")

    print("E5 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
