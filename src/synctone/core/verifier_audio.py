"""Audio tone generation and synchronized stream player for AV sync verification."""

import time
from typing import Optional
import numpy as np
import sounddevice as sd


def generate_click_sound(
    sample_rate: int = 48000,
    duration: float = 0.035,
    freq: float = 1200.0,
    amplitude: float = 0.6,
) -> np.ndarray:
    """Generate a sharp woodblock-like click sound for auditory delay detection.
    
    Fast attack and exponential decay make delay differences (flam/double trigger)
    instantly perceptible to human ears down to a few milliseconds.
    """
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    
    # Fundamental + 2nd harmonic
    tone = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.2 * t)
    # Steep exponential decay envelope
    envelope = np.exp(-t / (duration * 0.22))
    raw = tone * envelope
    peak = np.max(np.abs(raw))
    if peak > 1e-6:
        raw = raw / peak
    sound = raw * amplitude
    return sound.astype(np.float32)


def generate_beep_sound(
    sample_rate: int = 48000,
    duration: float = 0.04,
    freq: float = 1760.0,
    amplitude: float = 0.6,
) -> np.ndarray:
    """Generate a clean high-frequency beep tone (A6 1760Hz) for visual flash AV sync.
    
    Uses quick cosine ramp-in/out (2ms) to eliminate click transients while keeping
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
    """Synchronized lock-free audio stream player for metronome clicks and visual AV sync beeps."""

    def __init__(
        self,
        sample_rate: int = 48000,
        bpm: float = 120.0,
        amplitude: float = 0.5,
        output_device_idx: Optional[int] = None,
        mode: str = "beep",  # "beep" or "click"
        dummy_mode: bool = False,
    ):
        self.sample_rate = sample_rate
        self.bpm = max(40.0, min(240.0, float(bpm)))
        self.amplitude = max(0.05, min(1.0, float(amplitude)))
        self.output_device_idx = output_device_idx
        self.mode = mode
        self.dummy_mode = dummy_mode

        self._is_running = False
        self._stream: Optional[sd.OutputStream] = None

        # Lock-free atomic reference fields
        self._current_sample_in_cycle: int = 0
        self._cycle_samples: int = self._calc_cycle_samples()
        self._tone_samples: np.ndarray = self._prepare_tone()

        # Wall-clock timer fallback when hardware stream is unavailable
        self._fallback_start_time: float = 0.0
        self._use_fallback: bool = False

    def _calc_cycle_samples(self) -> int:
        seconds_per_beat = 60.0 / max(1e-3, self.bpm)
        return max(1, int(self.sample_rate * seconds_per_beat))

    def _prepare_tone(self) -> np.ndarray:
        if self.mode == "click":
            return generate_click_sound(
                sample_rate=self.sample_rate,
                duration=0.035,
                freq=1200.0,
                amplitude=self.amplitude,
            )
        else:
            return generate_beep_sound(
                sample_rate=self.sample_rate,
                duration=0.04,
                freq=1760.0,
                amplitude=self.amplitude,
            )

    def set_bpm(self, bpm: float) -> None:
        """Update tempo (BPM). Smoothly adjusts cycle length without crackles."""
        self.bpm = max(40.0, min(240.0, float(bpm)))
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

    def set_mode(self, mode: str) -> None:
        """Switch between 'beep' (AV Sync visual flash) and 'click' (auditory metronome)."""
        self.mode = mode
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
        self._tone_samples = self._prepare_tone()
        self._cycle_samples = self._calc_cycle_samples()

        if self.dummy_mode:
            self._fallback_start_time = time.perf_counter()
            self._use_fallback = True
            self._is_running = True
            return

        try:
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
        except Exception:
            # Fallback for devices without working hardware output (headless / mock test)
            self._stream = None
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

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        """Real-time sounddevice output stream callback (strictly lock-free)."""
        cycle = self._cycle_samples
        tone = self._tone_samples
        tone_len = len(tone)

        buf = np.zeros((frames, 2), dtype=np.float32)
        pos = self._current_sample_in_cycle

        for i in range(frames):
            if pos < tone_len:
                sample_val = tone[pos]
                buf[i, 0] = sample_val
                buf[i, 1] = sample_val

            pos += 1
            if pos >= cycle:
                pos = 0

        self._current_sample_in_cycle = pos
        outdata[:] = buf
