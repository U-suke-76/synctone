"""Tests for decoding a real container file (mp4/mkv) with PyAV and analyzing its AV offset."""

import numpy as np
import pytest

av = pytest.importorskip("av")

from synctone.core.recording import decode_recording, analyze_recording
from synctone.core.verifier_audio import generate_beep_sound

SR = 48000
FPS = 60
W, H = 640, 360
PERIOD = 60.0 / 110.0  # analysis tempo


def write_recording(path, video_phase0, audio_phase0, seconds=8.0, audio_codec="aac"):
    """Write a test recording: bar x = W*frac((t - v)/P) video, beeps at c + i*P audio."""
    container = av.open(str(path), "w")
    vs = container.add_stream("mpeg4", rate=FPS)
    vs.width, vs.height, vs.pix_fmt = W, H, "yuv420p"
    vs.bit_rate = 4_000_000
    a_s = container.add_stream(audio_codec, rate=SR)
    a_s.layout = "mono"

    # Video
    for k in range(int(seconds * FPS)):
        t = k / FPS
        x = W * (((t - video_phase0) / PERIOD) % 1.0)
        img = np.zeros((H, W, 3), dtype=np.uint8)
        lo = int(round(x - 3))
        img[int(H * 0.2):int(H * 0.8), max(0, lo):max(0, lo + 6), :] = 255
        frame = av.VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = k
        frame.time_base = __import__("fractions").Fraction(1, FPS)
        for pkt in vs.encode(frame):
            container.mux(pkt)
    for pkt in vs.encode(None):
        container.mux(pkt)

    # Audio
    n_total = int(seconds * SR)
    audio = np.zeros(n_total, dtype=np.float32)
    beep = generate_beep_sound(SR, amplitude=0.5)
    i = 0
    while True:
        start = int(round((audio_phase0 + i * PERIOD) * SR))
        if start + len(beep) >= n_total:
            break
        audio[start:start + len(beep)] += beep
        i += 1
    chunk = 1024
    pos = 0
    while pos < n_total:
        block = audio[pos:pos + chunk]
        frame = av.AudioFrame.from_ndarray(block[None, :], format="flt", layout="mono")
        frame.sample_rate = SR
        frame.pts = pos
        for pkt in a_s.encode(frame):
            container.mux(pkt)
        pos += chunk
    for pkt in a_s.encode(None):
        container.mux(pkt)
    container.close()


def test_decode_recording_shapes(tmp_path):
    path = tmp_path / "rec.mp4"
    write_recording(path, video_phase0=0.3, audio_phase0=0.3, seconds=3.0)
    rec = decode_recording(str(path))
    assert rec.audio_sample_rate == SR
    assert abs(len(rec.audio) / SR - 3.0) < 0.1
    assert rec.profiles.shape[1] == W
    assert abs(len(rec.frame_times) - 3.0 * FPS) <= 2
    assert np.all(np.diff(rec.frame_times) > 0)


@pytest.mark.parametrize("true_offset_ms", [-40.0, 0.0, 55.0])
def test_analyze_recording_recovers_offset_from_mp4(tmp_path, true_offset_ms):
    path = tmp_path / "rec.mp4"
    audio_phase0 = 0.31
    write_recording(path, video_phase0=audio_phase0 + true_offset_ms / 1000.0, audio_phase0=audio_phase0)
    res = analyze_recording(str(path))
    assert res.period_ms == pytest.approx(PERIOD * 1000.0, abs=0.5)
    assert abs(res.offset_ms - true_offset_ms) < 3.0


def test_decode_recording_requires_both_streams(tmp_path):
    path = tmp_path / "video_only.mp4"
    container = av.open(str(path), "w")
    vs = container.add_stream("mpeg4", rate=FPS)
    vs.width, vs.height, vs.pix_fmt = 64, 64, "yuv420p"
    for k in range(5):
        frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
        frame.pts = k
        for pkt in vs.encode(frame):
            container.mux(pkt)
    for pkt in vs.encode(None):
        container.mux(pkt)
    container.close()
    with pytest.raises(ValueError):
        decode_recording(str(path))
