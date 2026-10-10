#!/usr/bin/env python3
"""Nits N1-N4 (v2.1 robustness pass) - each a one-line-class contract check.

N1 caption pixel-test must be differential (burn vs no-burn delta >= 0.3%),
not absolute - bright in-band content must not false-pass.
N2 assemble.find_font() must include fetch_fonts output (media/fonts / CF_FONTS_DIR).
N3 probes must be hermetic: common.font honors CF_FONTS_DIR (no system DejaVu dep).
N4 whisper tier rung: CF_WHISPER_TIER=tiny must be honored + logged.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def synth_bright_band(path, dur=4.0, w=540, h=960):
    """Video whose caption band is bright near-white content, NO captions."""
    vf = (f"gradients=s={w}x{h}:d={dur}:c0=0xE8E8F0:c1=0xFFFFFF,format=yuv420p,"
          f"drawbox=x=0:y=ih*0.60:w=iw:h=ih*0.32:color=white:t=fill")
    subprocess_run = __import__("subprocess").run
    r = subprocess_run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
                        "-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}",
                        "-map", "0:v", "-map", "1:a", "-t", str(dur), "-r", "30",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", path], capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"synth_bright_band failed: {r.stderr[-200:]}")
    return path


def n1():
    qc = load_module("qc_under_test_n1", "scripts/cineforge/qc.py")
    if not hasattr(qc, "differential_caption_check"):
        fail("N1 contract missing: qc.differential_caption_check (burn vs no-burn)")
    with tempfile.TemporaryDirectory() as td:
        # a video with burned captions
        capped = os.path.join(td, "capped.mp4")
        clean = synth_bright_band(os.path.join(td, "clean.mp4"))
        ass = os.path.join(td, "cap.ass")
        open(ass, "w").write(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 540\nPlayResY: 960\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cine,DejaVu Sans,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,"
            "100,100,0,0,1,4,2,2,20,20,120,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:04.00,Cine,,0,0,0,,CAPTION TEXT HERE\n")
        __import__("subprocess").run(
            ["ffmpeg", "-v", "error", "-y", "-i", clean, "-vf", f"ass={ass}",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
             "-c:a", "copy", capped], check=True)
        cues = [1.0, 2.0, 3.0]
        d_capped = qc.differential_caption_check(capped, ass, cues, fontsdir=None)
        d_clean = qc.differential_caption_check(clean, ass, cues, fontsdir=None)
        if not d_capped.get("passed"):
            fail(f"N1: differential test fails a genuinely captioned video: {d_capped}")
        if d_clean.get("passed"):
            fail(f"N1 present: bright in-band content still false-passes the "
                 f"caption test (deltas: {d_clean.get('deltas')})")
        if d_capped.get("max_delta", 0) < 0.003:
            fail(f"N1: differential threshold wrong: max_delta={d_capped.get('max_delta')}")
        ok(f"N1 differential: captioned max_delta={d_capped.get('max_delta'):.4f} "
           f"PASS, bright-band no-caption max_delta={d_clean.get('max_delta'):.4f} FAIL")


def n2():
    asm = load_module("assemble_under_test_n2", "scripts/montage/assemble.py")
    with tempfile.TemporaryDirectory() as td:
        fdir = os.path.join(td, "fonts")
        os.makedirs(fdir)
        fake = os.path.join(fdir, "Anton-Regular.ttf")
        open(fake, "w").write("x")
        old = os.environ.get("CF_FONTS_DIR")
        os.environ["CF_FONTS_DIR"] = fdir
        try:
            got = asm.find_font()
        finally:
            if old is None:
                os.environ.pop("CF_FONTS_DIR", None)
            else:
                os.environ["CF_FONTS_DIR"] = old
        if os.path.dirname(got) != fdir:
            fail(f"N2 present: find_font ignores CF_FONTS_DIR (returned {got})")
        ok(f"N2 find_font honors fetch_fonts output dir: {got}")


def n3():
    import common as c
    with tempfile.TemporaryDirectory() as td:
        fdir = os.path.join(td, "f")
        os.makedirs(fdir)
        open(os.path.join(fdir, "Montserrat-Bold.ttf"), "w").write("x")
        old = os.environ.get("CF_FONTS_DIR")
        os.environ["CF_FONTS_DIR"] = fdir
        try:
            got = c.pick_font()
        finally:
            if old is None:
                os.environ.pop("CF_FONTS_DIR", None)
            else:
                os.environ["CF_FONTS_DIR"] = old
        if got != os.path.join(fdir, "Montserrat-Bold.ttf"):
            fail(f"N3 present: probe helper ignores CF_FONTS_DIR (returned {got})")
        ok(f"N3 probes are hermetic via CF_FONTS_DIR: {os.path.basename(got)}")


def n4():
    tr = load_module("transcribe_under_test_n4", "scripts/cineforge/transcribe.py")
    if not hasattr(tr, "model_ladder"):
        fail("N4 contract missing: transcribe.model_ladder (CF_WHISPER_TIER rung)")
    os.environ["CF_WHISPER_TIER"] = "tiny"
    try:
        ladder = tr.model_ladder()
    finally:
        os.environ.pop("CF_WHISPER_TIER", None)
    if ladder[:1] != ["tiny"]:
        fail(f"N4 present: CF_WHISPER_TIER=tiny not honored (ladder {ladder})")
    os.environ.pop("CF_WHISPER_TIER", None)
    if tr.model_ladder()[0] != "small":
        fail(f"default ladder must start at small (got {tr.model_ladder()})")
    if not hasattr(tr, "log_environment"):
        fail("N4 contract missing: transcribe.log_environment -> environment.json")
    with tempfile.TemporaryDirectory() as td:
        rep = os.path.join(td, "reports")
        os.makedirs(rep)
        tr.log_environment(rep, used_model="tiny")
        env = json.load(open(os.path.join(rep, "environment.json")))
        if env.get("whisper_model") != "tiny":
            fail(f"environment.json missing whisper tier record: {env}")
    ok("N4 whisper tier rung + environment.json logging present")


def main():
    n1()
    n2()
    n3()
    n4()
    print("NITS PROBE: PASS (4/4 fixed)")


if __name__ == "__main__":
    main()
