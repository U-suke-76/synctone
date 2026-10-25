"""Audio hardware I/O management using sounddevice."""

from dataclasses import dataclass
import threading
from typing import Callable, List, Optional, Tuple
import numpy as np
import sounddevice as sd


@dataclass
class AudioDeviceInfo:
    """Information about an audio input or output device."""
    index: int
    name: str
    hostapi_name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default_input: bool
    is_default_output: bool


class InputLevelMonitor:
    """Lightweight live microphone peak-level monitor (for pre-measurement level check)."""

    def __init__(self) -> None:
        self._stream: Optional[sd.InputStream] = None
        self._peak: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:
        peak = float(np.max(np.abs(indata))) if frames > 0 else 0.0
        if peak > self._peak:
            self._peak = peak

    def start(self, input_device_idx: Optional[int] = None) -> None:
        """Open the input stream, falling back to the device native sample rate on failure."""
        self.stop()
        rates = [48000, AudioEngine.get_device_default_samplerate(input_device_idx=input_device_idx)]
        last_err: Optional[Exception] = None
        for sr in rates:
            try:
                stream = sd.InputStream(
                    samplerate=sr,
                    channels=1,
                    dtype="float32",
                    device=input_device_idx,
                    blocksize=1024,
                    callback=self._callback,
                )
                stream.start()
                self._stream = stream
                self._peak = 0.0
                return
            except Exception as e:
                last_err = e
        raise RuntimeError(str(last_err))

    def feed(self, peak: float) -> None:
        """Feed an externally measured peak (e.g. from the measurement stream)."""
        if peak > self._peak:
            self._peak = peak

    def read_peak(self) -> float:
        """Return the peak amplitude (0.0-1.0+) since the last call and reset it."""
        peak = self._peak
        self._peak = 0.0
        return peak

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        self._peak = 0.0
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


class AudioEngine:
    """Manages audio device enumeration and playback/recording operations."""

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate

    @staticmethod
    def get_devices() -> Tuple[List[AudioDeviceInfo], List[AudioDeviceInfo]]:
        """List available output and input devices.

        Returns:
            (output_devices, input_devices)
        """
        raw_devices = sd.query_devices()
        default_devs = sd.default.device
        default_in_idx = default_devs[0] if default_devs[0] is not None else -1
        default_out_idx = default_devs[1] if default_devs[1] is not None else -1

        hostapis = sd.query_hostapis()

        output_devices: List[AudioDeviceInfo] = []
        input_devices: List[AudioDeviceInfo] = []

        for idx, dev in enumerate(raw_devices):
            hostapi_idx = dev.get("hostapi", 0)
            hostapi_name = hostapis[hostapi_idx]["name"] if hostapi_idx < len(hostapis) else ""

            info = AudioDeviceInfo(
                index=idx,
                name=dev["name"],
                hostapi_name=hostapi_name,
                max_input_channels=dev["max_input_channels"],
                max_output_channels=dev["max_output_channels"],
                default_samplerate=dev["default_samplerate"],
                is_default_input=(idx == default_in_idx),
                is_default_output=(idx == default_out_idx),
            )

            if dev["max_output_channels"] > 0:
                output_devices.append(info)
            if dev["max_input_channels"] > 0:
                input_devices.append(info)

        return output_devices, input_devices

    def set_sample_rate(self, sample_rate: int) -> None:
        """Update target sample rate."""
        self.sample_rate = int(sample_rate)

    @staticmethod
    def get_device_default_samplerate(
        output_device_idx: Optional[int] = None,
        input_device_idx: Optional[int] = None,
        fallback: int = 44100,
    ) -> int:
        """Query the hardware default sample rate for the selected input/output device."""
        for dev_idx, kind in [(input_device_idx, "input"), (output_device_idx, "output")]:
            try:
                info = sd.query_devices(dev_idx, kind)
                sr = int(round(float(info.get("default_samplerate", 0))))
                if sr >= 8000:
                    return sr
            except Exception:
                pass
        return fallback

    def play_and_record(
        self,
        playback_data: np.ndarray,
        output_device_idx: Optional[int] = None,
        input_device_idx: Optional[int] = None,
        record_extra_seconds: float = 0.5,
        level_callback: Optional[Callable[[float], None]] = None,
    ) -> np.ndarray:
        """Play reference signal through output device and simultaneously record from input device.

        Args:
            playback_data: 1D array of audio samples to play.
            output_device_idx: Specific output device index, or None for default.
            input_device_idx: Specific input device index, or None for default.
            record_extra_seconds: Extra recording time after playback finishes (to catch late arrivals).
            level_callback: Optional callable receiving the live input peak (0.0-1.0+) per audio block.

        Returns:
            1D numpy array of recorded audio (monaural, float32).
        """
        play_samples = np.asarray(playback_data, dtype=np.float32)
        extra_samples = max(0, int(self.sample_rate * record_extra_seconds))

        # Pad trailing silence so sd.playrec continues recording for record_extra_seconds after chirp finishes
        if play_samples.ndim == 1:
            if extra_samples > 0:
                padded_1d = np.concatenate([play_samples, np.zeros(extra_samples, dtype=np.float32)])
            else:
                padded_1d = play_samples
            play_signal = np.column_stack([padded_1d, padded_1d])
        else:
            if extra_samples > 0:
                pad_2d = np.zeros((extra_samples, play_samples.shape[1]), dtype=np.float32)
                play_signal = np.vstack([play_samples, pad_2d])
            else:
                play_signal = play_samples

        device_pair = (input_device_idx, output_device_idx)

        # With a level callback, run a duplex stream so the live mic peak can be reported
        # while the measurement is in progress.
        if level_callback is not None:
            total = len(play_signal)
            buf = np.zeros((total, 1), dtype=np.float32)
            state = {"pos": 0}
            finished = threading.Event()

            def _cb(indata, outdata, frames, time_info, status):
                pos = state["pos"]
                end = min(pos + frames, total)
                k = end - pos
                outdata[:k] = play_signal[pos:end]
                outdata[k:] = 0
                buf[pos:end] = indata[:k]
                try:
                    level_callback(float(np.max(np.abs(indata))))
                except Exception:
                    pass
                state["pos"] = end
                if end >= total:
                    raise sd.CallbackStop

            with sd.Stream(
                samplerate=self.sample_rate,
                channels=(1, play_signal.shape[1]),
                dtype="float32",
                device=device_pair,
                callback=_cb,
                finished_callback=finished.set,
            ):
                finished.wait(timeout=total / self.sample_rate + 5.0)
            return buf.flatten()

        # Execute synchronized play and record
        recorded = sd.playrec(
            play_signal,
            samplerate=self.sample_rate,
            channels=1,  # Record monaural
            dtype="float32",
            device=device_pair,
            blocking=True,
        )

        return recorded.flatten()

