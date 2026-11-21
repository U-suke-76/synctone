"""Audio tone generation and synchronized stream player for AV sync verification."""

import time
from collections import deque
from typing import Optional
import numpy as np
import sounddevice as sd


def generate_beep_sound(
    sample_rate: int = 48000,
    duration: float = 0.04,
    freq: float = 1760.0,
    amplitude: float = 0.6,
) -> np.ndarray:
    """Generate a clean high-frequency beep tone (A6 1760Hz) for visual flash AV sync.

    Uses quick cosine ramp-in/out (3ms) to eliminate click transients while keeping
    sharp auditory attack timing.
    """
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    tone = np.sin(2 * np.pi * freq * t)

    fade_len = int(sample_rate * 0.003)
    envelope = np.ones(n_samples, dtype=np.float32)
    if fade_len > 0 and 2 * fade_len < n_samples:
        fade_in = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, fade_len)))
        envelope[:fade_len] = fade_in
        envelope[-fade_len:] = fade_in[::-1]

    raw = tone * envelope
    peak = np.max(np.abs(raw))
    if peak > 1e-6:
        raw = raw / peak
    sound = raw * amplitude
    return sound.astype(np.float32)


class SyncAudioPlayer:
    """Synchronized lock-free audio stream player for visual AV sync beeps."""

    def __init__(
        self,
        sample_rate: int = 48000,
        bpm: float = 120.0,
        amplitude: float = 0.5,
        output_device_idx: Optional[int] = None,
        dummy_mode: bool = False,
    ):
        self.sample_rate = sample_rate
        self.bpm = max(40.0, min(240.0, float(bpm)))
        self.amplitude = max(0.05, min(1.0, float(amplitude)))
        self.output_device_idx = output_device_idx
        self.dummy_mode = dummy_mode

        self._is_running = False
        self._stream: Optional[sd.OutputStream] = None

        # Lock-free atomic reference fields
        self._current_sample_in_cycle: int = 0
        self._cycle_samples: int = self._calc_cycle_samples()
        # Unwrapped cycle position history (perf_counter time, cycles) used by get_clock_phase()
        self._wraps: int = 0
        self._clock_hist: deque = deque(maxlen=48)
        self._tone_samples: np.ndarray = self._prepare_tone()

        # Wall-clock timer fallback when hardware stream is unavailable
        self._fallback_start_time: float = 0.0
        self._use_fallback: bool = False

    def _calc_cycle_samples(self) -> int:
        seconds_per_beat = 60.0 / max(1e-3, self.bpm)
        return max(1, int(self.sample_rate * seconds_per_beat))

    def _prepare_tone(self) -> np.ndarray:
        return generate_beep_sound(
            sample_rate=self.sample_rate,
            duration=0.04,
            freq=1760.0,
            amplitude=self.amplitude,
        )

    def set_bpm(self, bpm: float) -> None:
        """Update tempo (BPM). Smoothly adjusts cycle length without crackles."""
        self.bpm = max(40.0, min(240.0, float(bpm)))
        self._clock_hist.clear()  # the cycle rate changes: restart the clock estimate
        old_cycle = self._cycle_samples
        new_cycle = self._calc_cycle_samples()
        if old_cycle > 0:
            phase_ratio = self._current_sample_in_cycle / old_cycle
            self._current_sample_in_cycle = int(phase_ratio * new_cycle)
        self._cycle_samples = new_cycle

    def set_amplitude(self, amplitude: float) -> None:
        """Update volume level."""
        self.amplitude = max(0.05, min(1.0, float(amplitude)))
        self._tone_samples = self._prepare_tone()

    def set_output_device(self, device_idx: Optional[int]) -> None:
        """Update output device. Restarts stream if currently running."""
        was_running = self.is_running
        if was_running:
            self.stop()
        self.output_device_idx = device_idx
        if was_running:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        """Start synchronized audio playback."""
        if self._is_running:
            return

        self._current_sample_in_cycle = 0
        self._wraps = 0
        self._clock_hist.clear()
        self._tone_samples = self._prepare_tone()
        self._cycle_samples = self._calc_cycle_samples()

        if self.dummy_mode:
            self._fallback_start_time = time.perf_counter()
            self._use_fallback = True
            self._is_running = True
            return

        candidate_rates = [self.sample_rate]
        try:
            dev_info = sd.query_devices(self.output_device_idx, "output")
            alt_sr = int(round(float(dev_info.get("default_samplerate", 44100))))
            if alt_sr >= 8000 and alt_sr != self.sample_rate:
                candidate_rates.append(alt_sr)
        except Exception:
            pass

        for sr in candidate_rates:
            try:
                if sr != self.sample_rate:
                    self.sample_rate = sr
                    self._tone_samples = self._prepare_tone()
                    self._cycle_samples = self._calc_cycle_samples()
                self._stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=2,
                    dtype="float32",
                    device=self.output_device_idx,
                    callback=self._audio_callback,
                    blocksize=512,
                )
                self._stream.start()
                self._use_fallback = False
                self._is_running = True
                return
            except Exception:
                self._stream = None

        # Fallback for devices without working hardware output (headless / mock test)
        self._fallback_start_time = time.perf_counter()
        self._use_fallback = True
        self._is_running = True


    def stop(self) -> None:
        """Stop playback and close audio stream immediately without deadlocks."""
        self._is_running = False
        st = self._stream
        self._stream = None
        if st is not None:
            try:
                st.abort()
                st.close()
            except Exception:
                pass

    def get_phase(self) -> float:
        """Get the current position in the beat cycle from -0.5 to +0.5.
        
        0.0 represents the exact instant the tone triggers (flash/click point).
        -0.5 is half a beat before trigger, +0.5 is half a beat after trigger.
        """
        if not self._is_running:
            return -0.5

        if self._use_fallback:
            elapsed = time.perf_counter() - self._fallback_start_time
            cycle_sec = 60.0 / max(1e-3, self.bpm)
            rel = (elapsed % cycle_sec) / cycle_sec
        else:
            cycle = self._cycle_samples
            pos = self._current_sample_in_cycle
            rel = (pos % cycle) / max(1, cycle)

        if rel < 0.5:
            return rel
        else:
            return rel - 1.0

    def get_clock_phase(self) -> float:
        """Get the precise app-clock cycle phase (0.0 <= phase < 1.0) at the current instant.

        Phase 0.0 is the instant the tone is triggered. Unlike get_phase(), which only follows the
        audio buffer position (updated in blocks), this estimates the continuous position by anchoring
        the nominal sample rate to the recent callback times, so that a video frame rendered right now
        can be labelled with sub-millisecond accuracy (used by the recording analysis timecode).
        """
        if not self._is_running:
            return 0.0

        now = time.perf_counter()
        cycle_sec = self._cycle_samples / float(self.sample_rate)
        if self._use_fallback:
            return ((now - self._fallback_start_time) / cycle_sec) % 1.0

        hist = list(self._clock_hist)
        if len(hist) < 4:
            return (self._current_sample_in_cycle % self._cycle_samples) / float(self._cycle_samples)

        rate = 1.0 / cycle_sec  # cycles per second at the nominal sample rate
        t0 = hist[0][0]
        intercepts = [u - rate * (t - t0) for t, u in hist]
        a = float(np.median(intercepts))
        return (a + rate * (now - t0)) % 1.0

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        """Real-time sounddevice output stream callback (strictly lock-free and vectorized)."""
        cycle = self._cycle_samples
        tone = self._tone_samples
        tone_len = len(tone)

        outdata.fill(0.0)
        pos = self._current_sample_in_cycle
        wraps = self._wraps
        written = 0

        while written < frames:
            chunk = min(frames - written, cycle - pos)
            if pos < tone_len:
                tone_end = min(pos + chunk, tone_len)
                n_tone = tone_end - pos
                outdata[written:written + n_tone, 0] = tone[pos:tone_end]
                outdata[written:written + n_tone, 1] = tone[pos:tone_end]

            pos += chunk
            written += chunk
            if pos >= cycle:
                pos = 0
                wraps += 1

        self._current_sample_in_cycle = pos
        self._wraps = wraps
        self._clock_hist.append((time.perf_counter(), wraps + pos / float(cycle)))
