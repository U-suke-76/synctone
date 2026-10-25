"""Numerical AV sync analysis of a recording (beep onsets in audio, flash onsets in video).

This module is decoder-independent: it works on plain NumPy arrays (decoded audio samples and
per-frame mean brightness with frame timestamps), so it can be unit-tested with synthetic data.

Sign convention: ``offset_ms = flash_time - beep_time``.
A positive value means the video is LATER than the audio.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np
from scipy.signal import correlate, find_peaks, hilbert

from synctone.core.verifier_audio import generate_beep_sound


@dataclass
class AvOffsetResult:
    """Estimated audio/video offset together with its reliability indicators."""
    offset_ms: float  # flash_time - beep_time (positive: video later than audio)
    uncertainty_ms: float  # heuristic error bound (quantization bias + statistical spread)
    n_beeps: int
    n_flashes: int
    n_matched: int
    frame_interval_ms: float
    phase_concentration: float  # 0..1; ~1 means beeps never dither against the frame grid (bad)


def detect_beep_onsets(
    audio: np.ndarray,
    sample_rate: int,
    template: Optional[np.ndarray] = None,
    carrier_hz: float = 1760.0,
    min_interval_s: float = 0.2,
    threshold_ratio: float = 0.5,
) -> np.ndarray:
    """Detect beep start times (seconds) using a matched filter against the known beep.

    The returned time is the position at which the template START aligns with the audio.
    Precision is within about one carrier period (~0.57 ms at 1760 Hz) thanks to carrier-level
    refinement and parabolic interpolation.

    Args:
        audio: 1D audio samples (mono).
        sample_rate: Sampling rate of ``audio``.
        template: Beep waveform to search for (defaults to the AV Sync Checker beep).
        carrier_hz: Carrier frequency of the beep, used for the fine search window.
        min_interval_s: Minimum spacing between two detected beeps.
        threshold_ratio: Detection threshold relative to the strongest match (0..1).
    """
    x = np.asarray(audio, dtype=np.float64).ravel()
    if template is None:
        template = generate_beep_sound(sample_rate=sample_rate, amplitude=1.0)
    tpl = np.asarray(template, dtype=np.float64).ravel()
    tpl = tpl - tpl.mean()
    if x.size < tpl.size or tpl.size == 0:
        return np.array([], dtype=np.float64)

    x = x - x.mean()
    # corr[n] is the match of the template placed with its start at sample n
    corr = correlate(x, tpl, mode="valid", method="fft")
    env = np.abs(hilbert(corr))
    peak = float(env.max())
    if peak <= 1e-12:
        return np.array([], dtype=np.float64)

    coarse, _ = find_peaks(
        env,
        height=threshold_ratio * peak,
        distance=max(1, int(min_interval_s * sample_rate)),
    )

    abs_corr = np.abs(corr)
    search = max(1, int(round(1.5 * sample_rate / carrier_hz)))
    times = []
    for p in coarse:
        lo = max(0, p - search)
        hi = min(len(abs_corr), p + search + 1)
        k = lo + int(np.argmax(abs_corr[lo:hi]))
        sub = 0.0
        if 0 < k < len(abs_corr) - 1:
            y0, y1, y2 = abs_corr[k - 1], abs_corr[k], abs_corr[k + 1]
            denom = y0 - 2.0 * y1 + y2
            if abs(denom) > 1e-12:
                sub = float(np.clip(0.5 * (y0 - y2) / denom, -0.5, 0.5))
        times.append((k + sub) / sample_rate)
    return np.asarray(times, dtype=np.float64)


def detect_flash_onsets(
    frame_times: np.ndarray,
    brightness: np.ndarray,
    min_contrast: float = 0.05,
) -> np.ndarray:
    """Detect flash onset times (seconds) from per-frame mean brightness.

    The onset is the timestamp of the first frame whose brightness crosses the midpoint between
    the baseline and the flash level (with hysteresis so a decaying flash is counted once).

    Args:
        frame_times: Presentation timestamp of each frame in seconds.
        brightness: Mean brightness of each frame (any scale, e.g. 0..1).
        min_contrast: Minimum (flash level - baseline) required, in the same unit as brightness.
    """
    t = np.asarray(frame_times, dtype=np.float64).ravel()
    v = np.asarray(brightness, dtype=np.float64).ravel()
    if t.size != v.size:
        raise ValueError("frame_times and brightness must have the same length.")
    if v.size < 3:
        return np.array([], dtype=np.float64)

    lo = float(np.percentile(v, 10))
    hi = float(np.percentile(v, 99.5))
    span = hi - lo
    if span < min_contrast:
        return np.array([], dtype=np.float64)

    up = lo + 0.5 * span
    rearm = lo + 0.3 * span

    onsets = []
    armed = True
    for k in range(v.size):
        if armed and v[k] >= up:
            armed = False
            # A flash already in progress at the very first frame has an unknown onset: skip it
            if k > 0:
                onsets.append(t[k])
        elif not armed and v[k] <= rearm:
            armed = True
    return np.asarray(onsets, dtype=np.float64)


def estimate_av_offset(
    beep_times: np.ndarray,
    flash_times: np.ndarray,
    frame_interval_s: float,
    max_match_s: Optional[float] = None,
) -> AvOffsetResult:
    """Estimate the audio/video offset from detected beep and flash onsets.

    Each beep is paired with the nearest flash. A flash is detected at the first frame at or after
    its true time, so on average it is observed half a frame late; this bias is removed. When the
    beep period is not a multiple of the frame interval, the quantization error averages out over
    the events. ``phase_concentration`` measures how well that dithering works.

    The offset is only unambiguous within +-(beep period / 2).

    Raises:
        ValueError: If fewer than 2 beeps / no flashes were detected, or nothing could be matched.
    """
    a = np.sort(np.asarray(beep_times, dtype=np.float64).ravel())
    f = np.sort(np.asarray(flash_times, dtype=np.float64).ravel())
    if a.size < 2 or f.size < 1:
        raise ValueError("At least 2 beeps and 1 flash are required.")
    if frame_interval_s <= 0:
        raise ValueError("frame_interval_s must be positive.")

    cycle = float(np.median(np.diff(a)))
    limit = max_match_s if max_match_s is not None else cycle / 2.0

    matched_a = []
    deltas = []
    for ai in a:
        j = int(np.argmin(np.abs(f - ai)))
        delta = float(f[j] - ai)
        if abs(delta) <= limit:
            matched_a.append(ai)
            deltas.append(delta)
    if not deltas:
        raise ValueError("No beep could be matched with a flash.")

    d = np.asarray(deltas, dtype=np.float64)
    ma = np.asarray(matched_a, dtype=np.float64)

    # Reject pairs that are clearly inconsistent (more than 1.5 frames from the median)
    med = float(np.median(d))
    keep = np.abs(d - med) <= 1.5 * frame_interval_s
    d, ma = d[keep], ma[keep]

    offset_s = float(np.mean(d)) - frame_interval_s / 2.0

    phases = (ma / frame_interval_s) % 1.0
    concentration = float(np.abs(np.mean(np.exp(2j * np.pi * phases))))
    spread = float(np.std(d)) / np.sqrt(len(d)) if len(d) > 1 else frame_interval_s / 2.0
    uncertainty_s = (frame_interval_s / 2.0) * concentration + spread

    return AvOffsetResult(
        offset_ms=offset_s * 1000.0,
        uncertainty_ms=uncertainty_s * 1000.0,
        n_beeps=int(a.size),
        n_flashes=int(f.size),
        n_matched=int(len(d)),
        frame_interval_ms=frame_interval_s * 1000.0,
        phase_concentration=concentration,
    )
