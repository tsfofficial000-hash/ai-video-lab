#!/usr/bin/env python3
"""Shared helpers for defect probes. Probe exit 0 = defect fixed, exit 1 = defect present."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def cf_path(*parts):
    return os.path.join(REPO, *parts)


def load_module(name, rel_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, cf_path(rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(cf_path(rel_path)))
    spec.loader.exec_module(mod)
    return mod


def synth_video(path, dur=4.0, w=540, h=960, bright=True, drawtext=None):
    """Synthetic test clip: moving gradient (bright) or dark flat."""
    if bright:
        color = "gradients=s={w}x{h}:d={dur}:c0=0x303050:c1=0xE0E0FF,format=yuv420p".format(
            w=w, h=h, dur=dur)
    else:
        color = "color=c=black:s={w}x{h}:d={dur},format=yuv420p".format(w=w, h=h, dur=dur)
    vf = color
    if drawtext:
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        vf += (",drawtext=fontfile=" + font + ":text='" + drawtext +
               "':fontsize=72:fontcolor=white:x=(w-tw)/2:y=h*0.72:box=1:boxcolor=black@0.5")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf,
           "-t", str(dur), "-r", "30", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True)
    return path


def synth_black_windows(path, dur=8.0, w=320, h=240):
    """Bright video with black segments at 0-1.5s and 6.0-8.0s (for blackdetect)."""
    c1 = f"color=c=black:s={w}x{h}:d=1.5"
    c2 = f"gradients=s={w}x{h}:d={dur - 1.5 - 2.0}:c0=0x404060:c1=0xF0F0FF"
    c3 = f"color=c=black:s={w}x{h}:d=2.0"
    fc = "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]"
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", c1, "-f", "lavfi", "-i", c2, "-f", "lavfi", "-i", c3,
           "-filter_complex", fc, "-map", "[v]", "-t", str(dur), "-r", "30", path]
    subprocess.run(cmd, check=True)
    return path


def blackdetect_stderr(path):
    """Run ffmpeg blackdetect, return stderr text."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf",
                        "blackdetect=d=0.4:pix_th=0.12:pic_th=0.90", "-f", "null", "-"],
                       capture_output=True, text=True)
    return p.stderr


def ok(msg):
    print(f"  PASS: {msg}")


def fail(msg):
    print(f"  FAIL: {msg}")
    sys.exit(1)
