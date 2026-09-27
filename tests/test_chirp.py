"""Tests for ChirpAnalyzer DSP and delay estimation."""

import pytest
import numpy as np
from synctone.core.chirp import ChirpAnalyzer, DelayEstimateResult, aggregate_measurements


def test_chirp_generation():
    """Verify chirp signal generation parameters."""
    analyzer = ChirpAnalyzer(sample_rate=48000, duration=0.8, pre_padding=0.1, post_padding=0.4)
    sig = analyzer.reference_signal

    expected_len = int(48000 * (0.8 + 0.1 + 0.4))
    assert len(sig) == expected_len
    # Amplitude should not exceed maximum
    assert np.max(np.abs(sig)) <= 0.5 + 1e-5
    # Edges should be zero due to padding
    assert np.all(sig[: int(48000 * 0.05)] == 0)
    assert np.all(sig[-int(48000 * 0.1):] == 0)


def test_set_amplitude():
    """Verify dynamic amplitude adjustment."""
    analyzer = ChirpAnalyzer(sample_rate=48000, amplitude=0.5)
    analyzer.set_amplitude(0.2)
    assert analyzer.amplitude == 0.2
    assert np.max(np.abs(analyzer.reference_signal)) <= 0.2 + 1e-5


def test_zero_delay_detection():
    """Test with identical reference and recorded signals (0 delay)."""
    analyzer = ChirpAnalyzer(sample_rate=48000)
    ref = analyzer.reference_signal

    result = analyzer.estimate_delay(recorded_signal=ref)

    assert abs(result.delay_ms) < 0.05
    assert result.confidence > 0.8
    assert result.peak_correlation > 0.95


@pytest.mark.parametrize("delay_ms", [10.0, 45.0, 120.5, 350.0])
def test_simulated_integer_delays(delay_ms: float):
    """Test delay estimation with various known artificial delays."""
    analyzer = ChirpAnalyzer(sample_rate=48000)
    ref = analyzer.reference_signal

    delay_samples = int(round(48000 * (delay_ms / 1000.0)))
    # Create recorded signal with leading zeros = delay
    rec = np.concatenate([np.zeros(delay_samples, dtype=np.float32), ref])

    result = analyzer.estimate_delay(recorded_signal=rec)

    # Delay estimation should be accurate within 0.1 ms (sample period is ~0.02ms)
    expected_delay_ms = (delay_samples / 48000.0) * 1000.0
    assert abs(result.delay_ms - expected_delay_ms) < 0.05
    assert result.confidence > 0.8


def test_subsample_interpolation():
    """Test fractional sample delay accuracy via parabolic interpolation."""
    analyzer = ChirpAnalyzer(sample_rate=48000)
    ref = analyzer.reference_signal

    # Fractional delay of 500.4 samples
    true_delay_samples = 500.4
    # Simulate fractional delay via linear interpolation
    n_samples = len(ref)
    x = np.arange(n_samples + 600)
    x_shifted = x - true_delay_samples
    rec = np.interp(x_shifted, np.arange(n_samples), ref, left=0.0, right=0.0)

    result = analyzer.estimate_delay(recorded_signal=rec)

    # Error should be well under 0.5 sample (< 0.01 ms)
    assert abs(result.delay_samples - true_delay_samples) < 0.2


def test_noisy_signal_robustness():
    """Verify that delay estimation succeeds even under heavy background noise."""
    analyzer = ChirpAnalyzer(sample_rate=48000)
    ref = analyzer.reference_signal

    delay_samples = 2400  # 50 ms
    rec = np.concatenate([np.zeros(delay_samples, dtype=np.float32), ref])

    # Add Gaussian noise (amplitude ~ 0.15, roughly SNR ~ 10 dB)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.1, size=len(rec)).astype(np.float32)
    rec_noisy = rec + noise

    result = analyzer.estimate_delay(recorded_signal=rec_noisy)

    assert abs(result.delay_samples - delay_samples) < 1.0
    assert result.confidence > 0.6


def test_aggregate_measurements_median():
    """Verify median filtering and jitter calculation across multiple runs."""
    r1 = DelayEstimateResult(delay_samples=2400, delay_ms=50.0, confidence=0.9, peak_correlation=0.9, correlation=np.array([]), lags=np.array([]))
    r2 = DelayEstimateResult(delay_samples=2410, delay_ms=50.2, confidence=0.95, peak_correlation=0.95, correlation=np.array([]), lags=np.array([]))
    # r3 has an outlier due to bump or sneeze
    r3 = DelayEstimateResult(delay_samples=2880, delay_ms=60.0, confidence=0.7, peak_correlation=0.7, correlation=np.array([]), lags=np.array([]))

    multi = aggregate_measurements([r1, r2, r3])

    # Median of [50.0, 50.2, 60.0] is 50.2
    assert multi.median_delay_ms == 50.2
    assert multi.best_index == 1
    assert multi.best_result == r2
    assert abs(multi.jitter_ms - 10.0) < 1e-5
    assert abs(multi.overall_confidence - (0.9 + 0.95 + 0.7) / 3.0) < 1e-5


def test_inverted_polarity_detection():
    """Verify that an inverted polarity microphone (180 deg out-of-phase) is correctly detected at the true delay."""
    analyzer = ChirpAnalyzer(sample_rate=48000)
    ref = analyzer.reference_signal

    delay_samples = 4800  # 100.0 ms
    # Inverted signal (multiply by -1)
    rec_inverted = -1.0 * np.concatenate([np.zeros(delay_samples, dtype=np.float32), ref])

    result = analyzer.estimate_delay(recorded_signal=rec_inverted)

    assert result.is_inverted is True
    assert abs(result.delay_samples - delay_samples) < 0.1
    assert abs(result.delay_ms - 100.0) < 0.05
    assert abs(result.peak_correlation) > 0.95
    assert result.confidence > 0.8
