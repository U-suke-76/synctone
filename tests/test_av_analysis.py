"""Tests for the decoder-independent AV sync analysis (synthetic audio / frame brightness)."""

import numpy as np
import pytest

from synctone.core.av_analysis import (
    detect_beep_onsets, detect_flash_onsets, estimate_av_offset,
)
from synctone.core.verifier_audio import generate_beep_sound

SR = 48000
FPS = 60.0


def make_audio(beep_times, duration, gain=0.3, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    audio = rng.normal(0.0, noise, int(duration * SR))
    beep = generate_beep_sound(SR, amplitude=1.0) * gain
    for bt in beep_times:
        i = int(round(bt * SR))
        audio[i:i + len(beep)] += beep[: len(audio) - i]
    return audio


def make_brightness(flash_times, duration, fps=FPS):
    """Per-frame brightness: baseline 0.1, instant flash then exponential decay."""
    times = np.arange(int(duration * fps)) / fps
    v = np.full_like(times, 0.1)
    for ft in flash_times:
        after = times >= ft
        v[after] = np.maximum(v[after], 0.1 + 0.8 * np.exp(-(times[after] - ft) / 0.05))
    return times, v


def beep_schedule(bpm, n, start=0.3):
    return start + np.arange(n) * 60.0 / bpm


def test_detect_beep_onsets_subms_accuracy():
    truth = beep_schedule(110.4, 12)
    audio = make_audio(truth, duration=8.0)
    found = detect_beep_onsets(audio, SR)
    assert len(found) == len(truth)
    assert np.max(np.abs(found - truth)) < 0.0007  # within ~one carrier period


def test_detect_beep_onsets_gain_and_inversion_invariant():
    truth = beep_schedule(100, 6)
    audio = -make_audio(truth, duration=5.0, gain=0.05)
    found = detect_beep_onsets(audio, SR)
    assert len(found) == len(truth)
    assert np.max(np.abs(found - truth)) < 0.0007


def test_detect_beep_onsets_silence_and_short_input():
    assert len(detect_beep_onsets(np.zeros(SR), SR)) == 0
    assert len(detect_beep_onsets(np.zeros(10), SR)) == 0


def test_detect_flash_onsets_counts_each_flash_once():
    truth = beep_schedule(110.4, 12)
    times, v = make_brightness(truth, duration=8.0)
    onsets = detect_flash_onsets(times, v)
    assert len(onsets) == len(truth)
    # Each onset is the first frame at/after the true flash time
    assert np.all(onsets >= truth - 1e-9)
    assert np.all(onsets - truth < 1.0 / FPS + 1e-9)


def test_detect_flash_onsets_flat_signal():
    times = np.arange(100) / FPS
    assert len(detect_flash_onsets(times, np.full(100, 0.3))) == 0


@pytest.mark.parametrize("true_offset_ms", [-30.0, 0.0, 23.0, 80.0])
def test_estimate_av_offset_recovers_known_offset(true_offset_ms):
    beeps = beep_schedule(110.4, 14)
    audio = make_audio(beeps, duration=9.0)
    times, v = make_brightness(beeps + true_offset_ms / 1000.0, duration=9.0)

    res = estimate_av_offset(
        detect_beep_onsets(audio, SR), detect_flash_onsets(times, v), 1.0 / FPS
    )
    assert res.n_matched >= 12
    assert abs(res.offset_ms - true_offset_ms) < 4.0
    assert res.phase_concentration < 0.5
    # The reported uncertainty must actually cover the observed error
    assert abs(res.offset_ms - true_offset_ms) <= res.uncertainty_ms + 1.0


def test_estimate_av_offset_flags_commensurate_tempo():
    """120 BPM at 60 fps is exactly 30 frames: no dithering, so reliability must be flagged."""
    beeps = beep_schedule(120.0, 14)
    audio = make_audio(beeps, duration=9.0)
    times, v = make_brightness(beeps + 0.023, duration=9.0)

    res = estimate_av_offset(
        detect_beep_onsets(audio, SR), detect_flash_onsets(times, v), 1.0 / FPS
    )
    assert res.phase_concentration > 0.95
    assert res.uncertainty_ms > 7.0


def test_estimate_av_offset_requires_events():
    with pytest.raises(ValueError):
        estimate_av_offset(np.array([1.0]), np.array([1.0]), 1.0 / FPS)
    with pytest.raises(ValueError):
        estimate_av_offset(np.array([1.0, 2.0]), np.array([]), 1.0 / FPS)
