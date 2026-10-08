#!/usr/bin/env python3
"""TEST B — MoviePy 2.x programmatic edit.

Identical edit intent to the FFmpeg baseline:
trim 2 segments -> 9:16 vertical (darkened fill bg + centered fg) ->
crossfade -> programmatic TextClip titles -> narration/source audio mix ->
TextClip-based subtitle burn-in from Whisper SRT -> hybrid FFmpeg loudnorm.

Emits [METRIC] lines for CI log parsing.
"""
import os
import re
import resource
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(os.path.dirname(BASE), "work")
os.chdir(WORK)


def metric(k, v):
    line = f"[METRIC] {k}={v}"
    print(line, flush=True)
    open("metrics.txt", "a").write(line + "\n")


def fail(msg):
    line = f"[FAIL-B] {msg}"
    print(line, flush=True)
    open("metrics.txt", "a").write(line + "\n")
    sys.exit(1)


T_ALL = time.time()
W, H, FPS = 1080, 1920, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

import moviepy  # noqa: E402
from moviepy import (  # noqa: E402
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)
metric("moviepy_version", moviepy.__version__)

# ---------- 1. Load + trim ----------
src = VideoFileClip("footage_src")
metric("source_resolution", f"{src.w}x{src.h}")
metric("source_duration", round(src.duration, 2))
c1 = src.subclipped(3, 9)
c2 = src.subclipped(12, 18)


# ---------- 2. 9:16 vertical composite (darkened fill bg + contain fg) ----
# NOTE: MoviePy 2.x ships no gaussian/box blur effect, so the classic blurred
# background is replaced by a darkened cover-fill. Documented in the report.
def verticalize(clip, darken=0.45):
    ratio = clip.w / clip.h
    if ratio > W / H:  # wider than 9:16 -> scale to height, crop width
        bg = clip.resized(height=H)
    else:
        bg = clip.resized(width=W)
    bg = bg.cropped(x_center=bg.w / 2, y_center=bg.h / 2, width=W, height=H)
    bg = bg.with_effects([vfx.MultiplyColor(darken)])
    fg = clip.resized(width=W) if ratio > W / H else clip.resized(height=H)
    return CompositeVideoClip([bg, fg.with_position("center")], size=(W, H))


v1 = verticalize(c1)
v2 = verticalize(c2).with_effects([vfx.CrossFadeIn(1.0)])
video = concatenate_videoclips([v1, v2], method="compose", padding=-1)
TOTAL = video.duration
metric("timeline_duration", round(TOTAL, 2))

# ---------- 3. Titles ----------
t1 = (
    TextClip(font=FONT, text="AI VIDEO LAB", font_size=72, color="white",
             stroke_color="black", stroke_width=2, text_align="center")
    .with_start(0.3).with_duration(3.2)
    .with_position(("center", int(H * 0.10)))
    .with_effects([vfx.CrossFadeIn(0.5), vfx.CrossFadeOut(0.5)])
)
t2 = (
    TextClip(font=FONT, text="MOVIEPY 2.x EDIT", font_size=56, color="white",
             stroke_color="black", stroke_width=2, text_align="center")
    .with_start(5.2).with_duration(3.0)
    .with_position(("center", int(H * 0.10)))
    .with_effects([vfx.CrossFadeIn(0.5), vfx.CrossFadeOut(0.5)])
)


# ---------- 4. Subtitles from Whisper SRT (programmatic TextClips) --------
def parse_srt(path):
    cues = []
    blocks = re.split(r"\n\s*\n", open(path, encoding="utf-8").read().strip())
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            a, b = lines[1].split("-->")

            def ts(s):
                s = s.strip().replace(",", ".")
                h, m, sec = s.split(":")
                return int(h) * 3600 + int(m) * 60 + float(sec)

            cues.append((ts(a), ts(b), " ".join(x.strip() for x in lines[2:])))
    return cues


subs_clips = []
if os.path.exists("subs.srt"):
    for (a, b, tx) in parse_srt("subs.srt"):
        if a >= TOTAL:
            continue
        dur = min(b, TOTAL) - a
        if dur <= 0.05:
            continue
        tc = TextClip(font=FONT, text=tx, font_size=40, color="white",
                      stroke_color="black", stroke_width=2,
                      size=(W - 140, None), method="caption", text_align="center")
        subs_clips.append(tc.with_start(a).with_duration(dur)
                          .with_position(("center", int(H * 0.82))))
    metric("subtitle_clips_composited", len(subs_clips))
else:
    metric("subtitle_clips_composited", 0)
    print("[WARN-B] subs.srt not found - rendering without subtitles")

# ---------- 5. Audio mix (source acrossfade + narration) ----------
base = AudioFileClip("src_audio.m4a")
a1 = base.subclipped(3, 9)
a2 = base.subclipped(12, 18).with_start(5.0).with_effects([afx.AudioFadeIn(1.0)])
narr = AudioFileClip("narration.wav").subclipped(0, 10.4).with_start(0.3).with_effects(
    [afx.MultiplyVolume(1.4), afx.AudioFadeOut(0.8)]
)
audio = CompositeAudioClip([a1, a2, narr])

final = (
    CompositeVideoClip([video, t1, t2] + subs_clips, size=(W, H))
    .with_duration(TOTAL)
    .with_audio(audio)
)

# ---------- 6. Render ----------
T0 = time.time()
final.write_videofile("final_moviepy.mp4", codec="libx264", audio_codec="aac",
                      fps=FPS, preset="medium", threads=4, logger=None)
render_s = time.time() - T0
metric("moviepy_render_seconds", round(render_s, 1))
metric("moviepy_peak_rss_mb",
       round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024))

# ---------- 7. Hybrid loudnorm pass (MoviePy has no loudnorm) ----------
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-i", "final_moviepy.mp4", "-c:v", "copy",
     "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-shortest",
     "-c:a", "aac", "-b:a", "192k", "final_moviepy_norm.mp4"],
    check=True,
)
metric("moviepy_total_wall_seconds", round(time.time() - T_ALL, 1))

# ---------- 8. Validate ----------
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
     "-of", "default=noprint_wrappers=1", "final_moviepy_norm.mp4"],
    capture_output=True, text=True,
)
print(probe.stdout)
for line in probe.stdout.splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        metric(f"moviepy_final_{k}", v)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "5", "-i",
                "final_moviepy_norm.mp4", "-frames:v", "1",
                "thumbnail_moviepy.jpg"], check=False)

for c in (narr, base, audio, final, src, c1, c2, v1, v2, video):
    try:
        c.close()
    except Exception:  # noqa: BLE001
        pass
print("[DONE-B]")
