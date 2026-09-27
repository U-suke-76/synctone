"""Audio hardware I/O management using sounddevice."""

from dataclasses import dataclass
from typing import List, Optional, Tuple
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

    def play_and_record(
        self,
        playback_data: np.ndarray,
        output_device_idx: Optional[int] = None,
        input_device_idx: Optional[int] = None,
        record_extra_seconds: float = 0.5,
    ) -> np.ndarray:
        """Play reference signal through output device and simultaneously record from input device.

        Args:
            playback_data: 1D array of audio samples to play.
            output_device_idx: Specific output device index, or None for default.
            input_device_idx: Specific input device index, or None for default.
            record_extra_seconds: Extra recording time after playback finishes (to catch late arrivals).

        Returns:
            1D numpy array of recorded audio (monaural, float32).
        """
        # Ensure 1D or 2D (stereo)
        play_samples = np.asarray(playback_data, dtype=np.float32)
        if play_samples.ndim == 1:
            # Play through both L/R channels
            play_signal = np.column_stack([play_samples, play_samples])
        else:
            play_signal = play_samples

        total_record_samples = len(play_samples) + int(self.sample_rate * record_extra_seconds)

        # Execute synchronized play and record
        device_pair = (input_device_idx, output_device_idx)
        recorded = sd.playrec(
            play_signal,
            samplerate=self.sample_rate,
            channels=1,  # Record monaural
            dtype="float32",
            device=device_pair,
            blocking=True,
        )

        return recorded.flatten()
