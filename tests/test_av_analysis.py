"""Tests for the decoder-independent AV sync analysis (synthetic audio and bar profiles)."""

import numpy as np
import pytest

from synctone.core.av_analysis import (
    detect_beep_onsets, fit_audio_clock, bar_positions_from_profiles,
    fit_video_clock, estimate_av_offset,
)
from synctone.core.verifier_audio import generate_beep_sound

SR = 48000
FPS = 60.0
WIDTH = 1000


def make_audio(beep_times, duration, gain=0.3, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    audio = rng.normal(0.0, noise, int(duration * SR))
    beep = generate_beep_sound(SR, amplitude=1.0) * gain
    for bt in beep_times:
        i = int(round(bt * SR))
        audio[i:i + len(beep)] += beep[: len(audio) - i]
    return audio


def make_profiles(frame_times, period, video_phase0, seed=1, with_static=True):
    """Column profiles of frames showing a bar at x = WIDTH*frac((t - v)/P) (+ static clutter)."""
    rng = np.random.default_rng(seed)
    cols = np.arange(WIDTH, dtype=np.float64)
    prof = np.full((len(frame_times), WIDTH), 20.0)
    if with_static:
        prof[:, 40:44] += 90.0   # window border
        prof[:, 700:760] += 30.0  # static text
    x = WIDTH * (((frame_times - video_phase0) / period) % 1.0)
    prof += 200.0 * np.exp(-0.5 * ((cols[None, :] - x[:, None]) / 2.0) ** 2)
    prof += rng.normal(0.0, 2.0, prof.shape)
    return prof


def frame_clock(duration, seed=2, jitter_ms=0.2):
    rng = np.random.default_rng(seed)
    return np.arange(int(duration * FPS)) / FPS + rng.normal(0.0, jitter_ms / 1000.0, int(duration * FPS))


def test_detect_beep_onsets_subms_accuracy():
    truth = 0.3 + np.arange(12) * 0.5436
    audio = make_audio(truth, duration=8.0)
    found = detect_beep_onsets(audio, SR)
    assert len(found) == len(truth)
    assert np.max(np.abs(found - truth)) < 0.0007  # within ~one carrier period


def test_detect_beep_onsets_gain_and_inversion_invariant():
    truth = 0.3 + np.arange(6) * 0.6
    audio = -make_audio(truth, duration=5.0, gain=0.05)
    found = detect_beep_onsets(audio, SR)
    assert len(found) == len(truth)
    assert np.max(np.abs(found - truth)) < 0.0007


def test_detect_beep_onsets_silence_and_short_input():
    assert len(detect_beep_onsets(np.zeros(SR), SR)) == 0
    assert len(detect_beep_onsets(np.zeros(10), SR)) == 0


def test_fit_audio_clock_tolerates_missed_beep():
    truth = 0.3 + np.arange(10) * 0.5
    kept = np.delete(truth, 4)
    period, phase, rms = fit_audio_clock(kept)
    assert period == pytest.approx(0.5, abs=1e-9)
    assert phase == pytest.approx(0.3, abs=1e-9)
    assert rms < 1e-9


def test_fit_audio_clock_needs_three_beeps():
    with pytest.raises(ValueError):
        fit_audio_clock(np.array([1.0, 1.5]))


def test_bar_positions_ignore_static_clutter_and_are_subpixel():
    times = frame_clock(5.0)
    prof = make_profiles(times, period=0.5, video_phase0=0.0)
    x = bar_positions_from_profiles(prof)
    truth = WIDTH * ((times / 0.5) % 1.0)
    ok = np.isfinite(x)
    assert ok.mean() > 0.95
    assert np.median(np.abs(x[ok] - truth[ok])) < 0.3  # sub-pixel


@pytest.mark.parametrize("period", [60.0 / 110.4, 0.5436])  # not a multiple of the frame interval
@pytest.mark.parametrize("true_offset_ms", [-45.0, 0.0, 37.0, 120.0])
def test_estimate_av_offset_recovers_known_offset(period, true_offset_ms):
    audio_phase = 0.31
    beeps = audio_phase + np.arange(16) * period
    audio = make_audio(beeps, duration=16 * period + 0.8)

    times = frame_clock(8.0)
    video_phase0 = audio_phase + true_offset_ms / 1000.0
    prof = make_profiles(times, period, video_phase0)

    res = estimate_av_offset(
        detect_beep_onsets(audio, SR), times, bar_positions_from_profiles(prof)
    )
    assert res.period_ms == pytest.approx(period * 1000.0, abs=0.01)
    assert abs(res.offset_ms - true_offset_ms) < 1.5
    assert res.uncertainty_ms < 3.0
    assert res.video_rms_ms < 2.0


@pytest.mark.parametrize("true_offset_ms", [-45.0, 37.0])
def test_estimate_av_offset_commensurate_period_is_flagged_not_hidden(true_offset_ms):
    """120 BPM at 60 fps is exactly 30 frames: the frames cannot pin the wrap point better than
    about a frame, so the error may be large but the reported uncertainty must cover it."""
    period = 0.5
    audio_phase = 0.31
    beeps = audio_phase + np.arange(16) * period
    audio = make_audio(beeps, duration=16 * period + 0.8)
    times = np.arange(int(8.0 * FPS)) / FPS  # exact frame grid, no jitter
    prof = make_profiles(times, period, audio_phase + true_offset_ms / 1000.0)

    res = estimate_av_offset(
        detect_beep_onsets(audio, SR), times, bar_positions_from_profiles(prof)
    )
    assert res.uncertainty_ms > 5.0
    assert abs(res.offset_ms - true_offset_ms) <= res.uncertainty_ms + 0.5


def test_estimate_av_offset_tolerates_missing_bar_frames():
    period = 60.0 / 110.4
    beeps = 0.2 + np.arange(14) * period
    audio = make_audio(beeps, duration=14 * period + 0.8)
    times = frame_clock(7.0)
    prof = make_profiles(times, period, 0.2 + 0.03)
    prof[::7] = 20.0  # frames where the bar is not visible
    res = estimate_av_offset(
        detect_beep_onsets(audio, SR), times, bar_positions_from_profiles(prof)
    )
    assert abs(res.offset_ms - 30.0) < 1.5


def test_fit_video_clock_rejects_static_video():
    times = frame_clock(3.0)
    with pytest.raises(ValueError):
        fit_video_clock(times, np.full(len(times), 400.0), 0.5)


def test_estimate_av_offset_ignores_idle_frames_outside_beep_window():
    """Frames before/after playback (where the bar is frozen) must not ruin the sweep fit."""
    period = 60.0 / 110.0
    audio_phase = 3.0
    beeps = audio_phase + np.arange(14) * period  # playback from t=3.0s to t~10.6s
    audio = make_audio(beeps, duration=14.0)
    times = frame_clock(14.0)
    prof = make_profiles(times, period, audio_phase + 0.035)
    # Before t=3.0 and after last beep, the bar is stationary at x=200
    idle = (times < 2.9) | (times > beeps[-1] + 0.1)
    cols = np.arange(WIDTH, dtype=np.float64)
    prof[idle] = 20.0 + 200.0 * np.exp(-0.5 * ((cols[None, :] - 200.0) / 2.0) ** 2)

    res = estimate_av_offset(
        detect_beep_onsets(audio, SR), times, bar_positions_from_profiles(prof)
    )
    assert abs(res.offset_ms - 35.0) < 2.0
    assert res.uncertainty_ms < 5.0


def test_estimate_av_offset_rejects_untracked_sweep():
    """If the video does not show a sweeping bar (flat / random positions), raise ValueError."""
    period = 60.0 / 110.0
    beeps = 0.5 + np.arange(14) * period
    times = frame_clock(9.0)
    rng = np.random.default_rng(42)
    bad_bar_x = rng.uniform(50.0, 900.0, size=len(times))
    with pytest.raises(ValueError, match="uncertainty"):
        estimate_av_offset(beeps, times, bad_bar_x)

