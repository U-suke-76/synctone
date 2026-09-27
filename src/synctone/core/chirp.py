"""Chirp signal generator and cross-correlation delay estimator."""

from dataclasses import dataclass
from typing import Tuple, Optional, List
import numpy as np
from scipy.signal import chirp, correlate, windows


@dataclass
class DelayEstimateResult:
    """Result of cross-correlation delay estimation for a single run."""
    delay_samples: float
    delay_ms: float
    confidence: float  # 0.0 to 1.0 (peak sharpness / correlation strength)
    peak_correlation: float
    correlation: np.ndarray
    lags: np.ndarray
    is_inverted: bool = False  # True if microphone has inverted polarity (180 deg out-of-phase)


@dataclass
class MultiMeasureResult:
    """Aggregated result of multiple measurement runs (e.g., 3-run median filter)."""
    individual_results: List[DelayEstimateResult]
    median_delay_ms: float
    mean_delay_ms: float
    jitter_ms: float  # Difference between max and min delay among runs (reproducibility)
    overall_confidence: float
    best_index: int  # Index of run closest to median
    best_result: DelayEstimateResult


def aggregate_measurements(results: List[DelayEstimateResult]) -> MultiMeasureResult:
    """Aggregate multiple delay estimates using median filter and jitter analysis.

    Args:
        results: List of DelayEstimateResult from consecutive runs.

    Returns:
        MultiMeasureResult with median delay, jitter, and best representative result.
    """
    if not results:
        raise ValueError("At least one measurement result is required.")

    delays = np.array([r.delay_ms for r in results], dtype=np.float64)
    confidences = np.array([r.confidence for r in results], dtype=np.float64)

    median_delay = float(np.median(delays))
    mean_delay = float(np.mean(delays))
    jitter = float(np.max(delays) - np.min(delays))
    overall_conf = float(np.mean(confidences))

    # Pick run whose delay is closest to the median
    diffs = np.abs(delays - median_delay)
    best_idx = int(np.argmin(diffs))

    return MultiMeasureResult(
        individual_results=results,
        median_delay_ms=median_delay,
        mean_delay_ms=mean_delay,
        jitter_ms=jitter,
        overall_confidence=overall_conf,
        best_index=best_idx,
        best_result=results[best_idx],
    )


class ChirpAnalyzer:
    """Generates chirp test signals and computes delay via cross-correlation."""

    def __init__(
        self,
        sample_rate: int = 48000,
        f_start: float = 500.0,
        f_end: float = 4000.0,
        duration: float = 0.8,
        pre_padding: float = 0.1,
        post_padding: float = 0.4,
        amplitude: float = 0.5,
    ):
        """Initialize ChirpAnalyzer.

        Args:
            sample_rate: Sampling frequency in Hz (default: 48000).
            f_start: Sweep start frequency in Hz (default: 500).
            f_end: Sweep end frequency in Hz (default: 4000).
            duration: Active sweep duration in seconds (default: 0.8).
            pre_padding: Leading silence in seconds (default: 0.1).
            post_padding: Trailing silence in seconds (default: 0.4).
            amplitude: Signal amplitude (0.0 to 1.0, default: 0.5 for safe volume).
        """
        self.sample_rate = sample_rate
        self.f_start = f_start
        self.f_end = f_end
        self.duration = duration
        self.pre_padding = pre_padding
        self.post_padding = post_padding
        self.amplitude = amplitude

        self._reference_signal = self._generate_reference_signal()

    @property
    def reference_signal(self) -> np.ndarray:
        """The pre-computed reference chirp signal with windowing and padding."""
        return self._reference_signal

    @property
    def total_duration(self) -> float:
        """Total duration of the reference signal including padding in seconds."""
        return self.pre_padding + self.duration + self.post_padding

    def set_amplitude(self, amplitude: float) -> None:
        """Update playback signal amplitude (0.05 to 1.0) and regenerate reference signal."""
        self.amplitude = max(0.05, min(1.0, float(amplitude)))
        self._reference_signal = self._generate_reference_signal()

    def _generate_reference_signal(self) -> np.ndarray:
        """Generate a log-chirp signal with smooth envelope windowing and padding."""
        n_samples_sweep = int(self.sample_rate * self.duration)
        t = np.linspace(0, self.duration, n_samples_sweep, endpoint=False)

        # Logarithmic sweep from f_start to f_end
        sweep = chirp(t, f0=self.f_start, t1=self.duration, f1=self.f_end, method="logarithmic")

        # Apply Tukey window (cosine-tapered) to eliminate click noise at edges
        window = windows.tukey(n_samples_sweep, alpha=0.1)
        windowed_sweep = sweep * window * self.amplitude

        # Pre/post silence padding
        n_pre = int(self.sample_rate * self.pre_padding)
        n_post = int(self.sample_rate * self.post_padding)

        full_signal = np.concatenate([
            np.zeros(n_pre, dtype=np.float32),
            windowed_sweep.astype(np.float32),
            np.zeros(n_post, dtype=np.float32),
        ])
        return full_signal

    def estimate_delay(
        self,
        recorded_signal: np.ndarray,
        reference_signal: Optional[np.ndarray] = None,
        max_delay_ms: float = 2000.0,
    ) -> DelayEstimateResult:
        """Estimate the delay of recorded_signal relative to reference_signal.

        A positive delay means recorded_signal arrives LATER than reference_signal.

        Args:
            recorded_signal: 1D array of recorded audio samples.
            reference_signal: Optional 1D array. If None, uses self.reference_signal.
            max_delay_ms: Maximum expected delay in milliseconds (default: 2000ms).

        Returns:
            DelayEstimateResult with delay in samples, ms, and confidence.
        """
        if reference_signal is None:
            reference_signal = self._reference_signal

        # Ensure 1D and float32/float64
        rec = np.asarray(recorded_signal, dtype=np.float64).flatten()
        ref = np.asarray(reference_signal, dtype=np.float64).flatten()

        # Normalize signals (zero-mean)
        rec = rec - np.mean(rec)
        ref = ref - np.mean(ref)

        rec_norm = np.linalg.norm(rec)
        ref_norm = np.linalg.norm(ref)

        if rec_norm < 1e-8 or ref_norm < 1e-8:
            return DelayEstimateResult(
                delay_samples=0.0,
                delay_ms=0.0,
                confidence=0.0,
                peak_correlation=0.0,
                correlation=np.array([]),
                lags=np.array([]),
            )

        # Cross-correlation: correlate(rec, ref)
        # When rec[n] = ref[n - D], peak occurs at lag = D
        corr = correlate(rec, ref, mode="full", method="fft")
        corr_norm = corr / (rec_norm * ref_norm)

        # Lags array corresponding to corr
        # correlate(in1, in2) length is len(in1) + len(in2) - 1
        # lag = 0 corresponds to index len(ref) - 1
        lags = np.arange(-len(ref) + 1, len(rec))

        # Restrict search range to reasonable positive lags (0 to max_delay_ms)
        # Also allow small negative lags in case of minor clock drift / alignment
        max_delay_samples = int(self.sample_rate * (max_delay_ms / 1000.0))
        min_search_lag = -int(self.sample_rate * 0.05)  # allow up to -50ms
        max_search_lag = max_delay_samples

        valid_mask = (lags >= min_search_lag) & (lags <= max_search_lag)
        if not np.any(valid_mask):
            valid_mask = np.ones_like(lags, dtype=bool)

        masked_lags = lags[valid_mask]
        masked_corr = corr_norm[valid_mask]

        # Find peak using absolute correlation so inverted polarity (180 deg out-of-phase)
        # microphones are correctly detected at the true delay, not at an adjacent sub-peak
        abs_masked_corr = np.abs(masked_corr)
        peak_idx_masked = int(np.argmax(abs_masked_corr))
        peak_lag = masked_lags[peak_idx_masked]
        raw_peak_val = masked_corr[peak_idx_masked]
        is_inverted = bool(raw_peak_val < 0)

        # Work with rectified correlation around the peak for parabolic interpolation
        interp_corr = -masked_corr if is_inverted else masked_corr
        peak_val = float(interp_corr[peak_idx_masked])

        # Parabolic interpolation around peak for sub-sample accuracy
        subsample_offset = 0.0
        if 0 < peak_idx_masked < len(masked_corr) - 1:
            y0 = interp_corr[peak_idx_masked - 1]
            y1 = interp_corr[peak_idx_masked]
            y2 = interp_corr[peak_idx_masked + 1]
            denom = y0 - 2.0 * y1 + y2
            if abs(denom) > 1e-12:
                subsample_offset = 0.5 * (y0 - y2) / denom
                # Clamp offset to [-0.5, 0.5]
                subsample_offset = max(-0.5, min(0.5, subsample_offset))

        refined_delay_samples = float(peak_lag + subsample_offset)
        delay_ms = (refined_delay_samples / self.sample_rate) * 1000.0

        # Compute confidence: ratio of peak to mean/std of correlation baseline
        baseline = np.abs(masked_corr)
        mean_val = np.mean(baseline)
        std_val = np.std(baseline)
        snr = (peak_val - mean_val) / (std_val + 1e-8)
        # Map SNR to 0.0-1.0 confidence score (SNR > 8 is very solid)
        confidence = float(np.clip(snr / 10.0, 0.0, 1.0))

        return DelayEstimateResult(
            delay_samples=refined_delay_samples,
            delay_ms=delay_ms,
            confidence=confidence,
            peak_correlation=float(raw_peak_val),
            correlation=corr_norm,
            lags=lags,
            is_inverted=is_inverted,
        )

    def align_signals(
        self,
        reference_signal: np.ndarray,
        recorded_signal: np.ndarray,
        delay_samples: float,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Align recorded_signal to reference_signal by shifting by delay_samples.

        Returns:
            (time_axis, ref_aligned, rec_aligned) for waveform overlay plotting.
        """
        int_delay = int(round(delay_samples))
        n_ref = len(reference_signal)
        n_rec = len(recorded_signal)

        # Common length
        total_len = max(n_ref, n_rec + max(0, -int_delay))
        time_axis = np.arange(total_len) / self.sample_rate

        ref_aligned = np.zeros(total_len, dtype=np.float32)
        ref_aligned[:n_ref] = reference_signal

        rec_aligned = np.zeros(total_len, dtype=np.float32)
        if int_delay >= 0:
            if int_delay < total_len:
                available = min(n_rec, total_len - int_delay)
                rec_aligned[int_delay:int_delay + available] = recorded_signal[:available]
        else:
            # rec is ahead
            offset = -int_delay
            if offset < n_rec:
                available = min(n_rec - offset, total_len)
                rec_aligned[:available] = recorded_signal[offset:offset + available]

        return time_axis, ref_aligned, rec_aligned
