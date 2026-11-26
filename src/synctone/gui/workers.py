"""Background worker threads used by the SyncTone main window."""

from typing import List, Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

from synctone.core.audio_io import AudioEngine
from synctone.core.chirp import ChirpAnalyzer, DelayEstimateResult, aggregate_measurements


class TestToneWorker(QThread):
    """Worker thread to play a gentle test tone for volume checking."""
    def __init__(self, out_device_idx: Optional[int], amplitude: float = 0.5):
        super().__init__()
        self.out_device_idx = out_device_idx
        self.amplitude = amplitude

    def run(self):
        for sr in [48000, AudioEngine.get_device_default_samplerate(output_device_idx=self.out_device_idx, fallback=44100)]:
            try:
                # 0.25 second gentle sine tone (880 Hz, A5) with smooth envelope
                t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
                tone = np.sin(2 * np.pi * 880 * t) * self.amplitude * 0.5
                fade = np.sin(np.linspace(0, np.pi, len(tone)))
                stereo = np.column_stack([tone * fade, tone * fade]).astype(np.float32)
                sd.play(stereo, samplerate=sr, device=self.out_device_idx, blocking=True)
                break
            except Exception:
                continue


class MeasurementWorker(QThread):
    """Worker thread to run single or multi-run measurement and analysis."""
    step_progress = Signal(int, int)  # (current_step, total_steps)
    finished_measurement = Signal(object, object)  # (MultiMeasureResult, recorded_signal)
    error_occurred = Signal(str)
    level_peak = Signal(float)  # live mic peak during measurement

    def __init__(
        self,
        analyzer: ChirpAnalyzer,
        audio_engine: AudioEngine,
        out_device_idx: Optional[int],
        in_device_idx: Optional[int],
        total_runs: int = 3,
    ):
        super().__init__()
        self.analyzer = analyzer
        self.audio_engine = audio_engine
        self.out_device_idx = out_device_idx
        self.in_device_idx = in_device_idx
        self.total_runs = total_runs

    def _record_once(self) -> np.ndarray:
        """Play the reference chirp and record the loopback signal."""
        return self.audio_engine.play_and_record(
            playback_data=self.analyzer.reference_signal,
            output_device_idx=self.out_device_idx,
            input_device_idx=self.in_device_idx,
            record_extra_seconds=0.4,
            level_callback=self.level_peak.emit,
        )

    def run(self):
        try:
            results: List[DelayEstimateResult] = []
            recordeds: List[np.ndarray] = []

            for run_idx in range(self.total_runs):
                self.step_progress.emit(run_idx + 1, self.total_runs)
                try:
                    recorded = self._record_once()
                except Exception:
                    # Fallback to device native sample rate (e.g. 44100 Hz) if 48000 Hz fails
                    alt_sr = AudioEngine.get_device_default_samplerate(
                        output_device_idx=self.out_device_idx,
                        input_device_idx=self.in_device_idx,
                        fallback=44100,
                    )
                    self.audio_engine.set_sample_rate(alt_sr)
                    self.analyzer.set_sample_rate(alt_sr)
                    recorded = self._record_once()

                res = self.analyzer.estimate_delay(recorded_signal=recorded)
                results.append(res)
                recordeds.append(recorded)

                if run_idx < self.total_runs - 1:
                    self.msleep(250)  # Pause between sweeps

            multi_result = aggregate_measurements(results)
            best_recorded = recordeds[multi_result.best_index]
            self.finished_measurement.emit(multi_result, best_recorded)
        except Exception as e:
            self.error_occurred.emit(str(e))


class RecordingAnalysisWorker(QThread):
    """Worker thread to decode an OBS recording and estimate its audio/video offset."""
    finished_analysis = Signal(object)  # AvOffsetResult
    error_occurred = Signal(str)

    def __init__(self, path: str, max_seconds: Optional[float] = 120.0, wrap_phase: float = 0.5):
        super().__init__()
        self.path = path
        self.max_seconds = max_seconds
        self.wrap_phase = wrap_phase

    def run(self):
        try:
            from synctone.core.recording import analyze_recording  # lazy: pulls in PyAV
            self.finished_analysis.emit(
                analyze_recording(self.path, max_seconds=self.max_seconds, wrap_phase=self.wrap_phase)
            )
        except Exception as e:
            self.error_occurred.emit(str(e))
