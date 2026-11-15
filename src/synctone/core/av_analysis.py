"""Numerical AV sync analysis of a recording using a sweeping-bar timecode and periodic beeps.

Principle
---------
The app plays a beep exactly at app-clock phase 0 of every cycle (period ``P`` seconds) and draws a bar
whose horizontal position encodes the app-clock phase at the instant each frame was rendered
(left edge = phase 0, right edge = phase 1). In the recording:

* audio: beep ``i`` starts at ``a_i = c + i * P``                   (``c``: audio time of phase 0)
* video: a frame with timestamp ``p`` shows phase ``phi``, so ``p = v + (n + phi) * P``
                                                                    (``v``: video time of phase 0)

``offset = v - c`` (wrapped to +-P/2) is then the audio/video offset of the recorded output. Because every
frame carries its own sub-frame phase reading, there is no frame quantization error and the result does
not depend on the tempo / frame-rate relationship.

This module is decoder-independent: it works on plain NumPy arrays (audio samples, per-frame column
brightness profiles and frame timestamps), so it can be unit-tested with synthetic data.

Sign convention: ``offset_ms = v - c``. A positive value means the video is LATER than the audio.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from scipy.signal import correlate, find_peaks, hilbert

from synctone.core.verifier_audio import generate_beep_sound


@dataclass
class AvOffsetResult:
    """Estimated audio/video offset together with fit-quality indicators."""
    offset_ms: float  # v - c (positive: video later than audio), wrapped to +-period/2
    uncertainty_ms: float  # half width of the range of offsets the data cannot tell apart
    period_ms: float  # cycle length estimated from the beeps
    audio_rms_ms: float  # beep timing residual of the linear fit
    video_rms_ms: float  # bar position residual of the sawtooth fit, expressed in time
    n_beeps: int
    n_frames: int  # frames in which the bar was found and used


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


def fit_audio_clock(beep_times: np.ndarray) -> Tuple[float, float, float]:
    """Fit ``a_i = c + i * P`` to the detected beep times.

    Missed beeps are tolerated (indices are assigned by rounding to the nominal period).

    Returns:
        (period_s, phase_s, rms_s): cycle length, time of cycle phase 0 (offset of the first beep)
        and the RMS residual of the fit.
    """
    a = np.sort(np.asarray(beep_times, dtype=np.float64).ravel())
    if a.size < 3:
        raise ValueError("At least 3 beeps are required to fit the audio clock.")
    nominal = float(np.median(np.diff(a)))
    idx = np.round((a - a[0]) / nominal)
    slope, intercept = np.polyfit(idx, a, 1)
    rms = float(np.sqrt(np.mean((a - (intercept + slope * idx)) ** 2)))
    return float(slope), float(intercept), rms


def bar_positions_from_profiles(profiles: np.ndarray, half_width_px: int = 8) -> np.ndarray:
    """Locate the sweeping bar in each frame from its column brightness profile.

    Args:
        profiles: Array (n_frames, width): brightness of each frame averaged over the rows of the
            region that contains the timecode track.
        half_width_px: Half width of the window used for the sub-pixel centroid.

    Returns:
        Array (n_frames,) of bar centre x positions in pixels (sub-pixel); NaN where no bar was found.
        Static content (borders, text) is removed using the temporal median profile as background.
    """
    prof = np.asarray(profiles, dtype=np.float64)
    if prof.ndim != 2 or prof.shape[0] == 0:
        raise ValueError("profiles must be a non-empty 2D array (n_frames, width).")

    diff = prof - np.median(prof, axis=0, keepdims=True)
    diff[diff < 0.0] = 0.0
    peaks = diff.max(axis=1)
    ref = float(np.percentile(peaks, 90))
    positions = np.full(prof.shape[0], np.nan, dtype=np.float64)
    if ref <= 1e-9:
        return positions

    width = prof.shape[1]
    cols = np.arange(width, dtype=np.float64)
    for k in range(prof.shape[0]):
        if peaks[k] < 0.3 * ref:
            continue
        c = int(np.argmax(diff[k]))
        lo, hi = max(0, c - half_width_px), min(width, c + half_width_px + 1)
        w = diff[k, lo:hi] - 0.2 * peaks[k]  # cut the noise floor around the bar
        w[w < 0.0] = 0.0
        total = w.sum()
        if total > 0.0:
            positions[k] = float((cols[lo:hi] * w).sum() / total)
    return positions


def fit_video_clock(
    frame_times: np.ndarray,
    bar_x: np.ndarray,
    period_s: float,
    step_s: float = 1e-4,
) -> Tuple[float, float, float, int]:
    """Fit the sawtooth bar motion ``x = A + B * frac((t - v) / P)`` to the frames.

    Inside the sweep, ``A`` (track start) and ``v`` cannot be told apart, so ``v`` is pinned by the wrap
    point where the bar jumps back to the start: for each candidate ``v`` the sweep is fitted by linear
    regression and the candidates with the smallest residual (no frame on the wrong side of the wrap)
    form a plateau. ``v`` is the middle of that plateau and its half width is the uncertainty.
    The plateau is narrow only if the frame times are spread over the cycle (period and frame interval
    not commensurate); otherwise the uncertainty grows up to about half a frame.

    Args:
        frame_times: Presentation timestamp of each frame (seconds).
        bar_x: Bar x position of each frame in pixels (NaN where not found).
        period_s: Cycle length (from the audio clock).
        step_s: Resolution of the search over ``v``.

    Returns:
        (phase_s, uncertainty_s, rms_s, n_used): ``v`` (video time of phase 0, modulo the period),
        its uncertainty, the RMS residual of the fit expressed in time, and the number of frames used.
    """
    t = np.asarray(frame_times, dtype=np.float64).ravel()
    x = np.asarray(bar_x, dtype=np.float64).ravel()
    if t.size != x.size:
        raise ValueError("frame_times and bar_x must have the same length.")
    ok = np.isfinite(x)
    t, x = t[ok], x[ok]
    if t.size < 10:
        raise ValueError("Too few frames with a detected bar.")
    if float(np.ptp(x)) < 1.0:
        raise ValueError("The bar does not move: no timecode sweep detected.")

    n = t.size
    m = max(8, int(round(period_s / step_s)))
    candidates = np.arange(m) * (period_s / m)
    sxx = float(np.sum((x - x.mean()) ** 2))
    xc = x - x.mean()

    sse = np.empty(m, dtype=np.float64)
    slope = np.empty(m, dtype=np.float64)
    chunk = 400
    for lo in range(0, m, chunk):
        v = candidates[lo:lo + chunk, None]
        phi = ((t[None, :] - v) / period_s) % 1.0
        pc = phi - phi.mean(axis=1, keepdims=True)
        spp = np.sum(pc * pc, axis=1)
        spx = np.sum(pc * xc[None, :], axis=1)
        b = spx / np.maximum(spp, 1e-12)
        slope[lo:lo + chunk] = b
        sse[lo:lo + chunk] = sxx - b * spx

    best = int(np.argmin(sse))
    plateau = sse <= sse[best] * 1.5 + 1.0  # a frame on the wrong side of the wrap costs ~B^2
    left = right = best
    while plateau[(left - 1) % m] and (best - left) < m - 1:
        left -= 1
    while plateau[(right + 1) % m] and (right - best) < m - 1 - (best - left):
        right += 1
    count = right - left + 1
    mid = (left + right) / 2.0
    v_est = float((mid % m) * (period_s / m))
    uncertainty_s = float(count * (period_s / m) / 2.0)

    mid_idx = int(round(mid)) % m
    px_per_s = abs(float(slope[mid_idx])) / period_s
    rms_px = float(np.sqrt(max(sse[mid_idx], 0.0) / n))
    rms_s = rms_px / px_per_s if px_per_s > 0 else float("nan")
    return v_est, uncertainty_s, rms_s, int(n)


def estimate_av_offset(
    beep_times: np.ndarray,
    frame_times: np.ndarray,
    bar_x: np.ndarray,
) -> AvOffsetResult:
    """Estimate the audio/video offset of a recording from beep onsets and per-frame bar positions.

    The result is unambiguous within +-(period / 2). Use a beep period that is not a multiple of the frame
    interval so that the frames sample the cycle densely (see :func:`fit_video_clock`).
    """
    period, c, audio_rms = fit_audio_clock(beep_times)
    # Only scan frames during which the timecode sweep was in steady state.
    # Trim one cycle after the first beep (so video render delay up to ~500 ms has already started
    # moving the bar) and before the last beep (in case playback was stopped right after it).
    t_arr = np.asarray(frame_times, dtype=np.float64).ravel()
    x_arr = np.asarray(bar_x, dtype=np.float64).ravel()
    beeps_sorted = np.sort(np.asarray(beep_times, dtype=np.float64).ravel())
    inner_window = (t_arr >= beeps_sorted[0] + period * 0.5) & (t_arr <= beeps_sorted[-1] - period * 0.2)
    if np.count_nonzero(inner_window & np.isfinite(x_arr)) >= 20:
        t_arr = t_arr[inner_window]
        x_arr = x_arr[inner_window]
    else:
        in_window = (t_arr >= beeps_sorted[0]) & (t_arr <= beeps_sorted[-1])
        if np.count_nonzero(in_window & np.isfinite(x_arr)) >= 10:
            t_arr = t_arr[in_window]
            x_arr = x_arr[in_window]

    v, video_unc, video_rms, n_used = fit_video_clock(t_arr, x_arr, period)
    offset = ((v - c + period / 2.0) % period) - period / 2.0
    total_unc_ms = (video_unc + audio_rms) * 1000.0
    if total_unc_ms > 80.0 or not np.isfinite(video_rms):
        raise ValueError(
            f"Timecode bar sweep could not be reliably tracked (uncertainty ±{total_unc_ms:.1f} ms). "
            "Make sure the SyncTone window is captured in 'Recording analysis' mode and playing while recording."
        )
    return AvOffsetResult(
        offset_ms=offset * 1000.0,
        uncertainty_ms=total_unc_ms,
        period_ms=period * 1000.0,
        audio_rms_ms=audio_rms * 1000.0,
        video_rms_ms=video_rms * 1000.0,
        n_beeps=int(np.asarray(beep_times).size),
        n_frames=n_used,
    )
