"""Main application window for SyncTone."""

import sys
import os
from typing import List, Optional
import numpy as np

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit,
    QSpinBox, QDoubleSpinBox, QSlider, QProgressBar, QGroupBox, QMessageBox,
    QFrame, QStatusBar, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QTimer, qInstallMessageHandler, QtMsgType
from PySide6.QtGui import QFont

def _qt_message_handler(mode: QtMsgType, context, message: str) -> None:
    """Filter out benign internal Qt font size warnings."""
    if "setPointSize: Point size <= 0" in message:
        return
    if "QFont::setPixelSize" in message:
        return
    sys.stderr.write(f"{message}\n")

qInstallMessageHandler(_qt_message_handler)

from synctone.core.chirp import (
    ChirpAnalyzer, DelayEstimateResult, MultiMeasureResult, aggregate_measurements
)
from synctone.core.audio_io import AudioEngine, AudioDeviceInfo
from synctone.obs.client import ObsClient, ObsAudioSource, ObsVideoSource
from synctone.gui.plot_widget import SyncPlotWidget
from synctone.gui.verifier_window import SyncVerifierWindow
from synctone.i18n import t, LANGUAGES, I18nManager
import sounddevice as sd


class TestToneWorker(QThread):
    """Worker thread to play a gentle test tone for volume checking."""
    def __init__(self, out_device_idx: Optional[int], amplitude: float = 0.5):
        super().__init__()
        self.out_device_idx = out_device_idx
        self.amplitude = amplitude

    def run(self):
        try:
            sr = 48000
            # 0.25 second gentle sine tone (880 Hz, A5) with smooth envelope
            t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
            tone = np.sin(2 * np.pi * 880 * t) * self.amplitude * 0.5
            fade = np.sin(np.linspace(0, np.pi, len(tone)))
            stereo = np.column_stack([tone * fade, tone * fade]).astype(np.float32)
            sd.play(stereo, samplerate=sr, device=self.out_device_idx, blocking=True)
        except Exception:
            pass


class MeasurementWorker(QThread):
    """Worker thread to run single or multi-run measurement and analysis."""
    step_progress = Signal(int, int)  # (current_step, total_steps)
    finished_measurement = Signal(object, object)  # (MultiMeasureResult, recorded_signal)
    error_occurred = Signal(str)

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

    def run(self):
        try:
            results: List[DelayEstimateResult] = []
            recordeds: List[np.ndarray] = []

            for run_idx in range(self.total_runs):
                self.step_progress.emit(run_idx + 1, self.total_runs)
                ref_sig = self.analyzer.reference_signal
                recorded = self.audio_engine.play_and_record(
                    playback_data=ref_sig,
                    output_device_idx=self.out_device_idx,
                    input_device_idx=self.in_device_idx,
                    record_extra_seconds=0.4,
                )
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


class MainWindow(QMainWindow):
    """Main window of SyncTone application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SyncTone - OBS音声同期アシスタント")
        self.resize(1020, 880)
        self.setMinimumSize(850, 750)

        # Settings
        self.settings = QSettings("SyncTone", "SyncTone")

        # Core engines
        self.analyzer = ChirpAnalyzer(sample_rate=48000, amplitude=0.5)
        self.audio_engine = AudioEngine(sample_rate=48000)
        self.obs_client = ObsClient()

        self.worker: Optional[MeasurementWorker] = None
        self.test_worker: Optional[TestToneWorker] = None
        self.last_multi_result: Optional[MultiMeasureResult] = None
        self.last_recorded: Optional[np.ndarray] = None
        self._last_measured_delay_ms: float = 0.0
        self._has_applied_measured: bool = False
        self._latest_obs_offset: Optional[int] = None
        self.obs_sources: List[ObsAudioSource] = []
        self._latest_obs_video_delay: Optional[int] = None
        self.obs_video_sources: List[ObsVideoSource] = []
        self.verifier_window: Optional[SyncVerifierWindow] = None

        self._apply_dark_theme()
        self._init_ui()
        self._load_saved_settings()
        self._refresh_audio_devices()

    def _apply_dark_theme(self) -> None:
        """Apply a sleek, modern dark theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #121218;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Meiryo', sans-serif;
                font-size: 10pt;
            }
            QGroupBox {
                border: 1px solid #2a2a38;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
                color: #82aaff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }
            QPushButton {
                background-color: #1e1e2c;
                border: 1px solid #3d3d52;
                border-radius: 6px;
                padding: 6px 14px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2b2b3f;
                border-color: #5c5c7a;
            }
            QPushButton:pressed {
                background-color: #161622;
            }
            QPushButton:checked {
                background-color: #283593;
                border-color: #5c6bc0;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #14141c;
                color: #555566;
                border-color: #22222e;
            }
            QPushButton#measure_btn {
                background-color: #00897b;
                border: 1px solid #26a69a;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 8px;
            }
            QPushButton#measure_btn:hover {
                background-color: #009688;
                border-color: #4db6ac;
            }
            QPushButton#apply_btn {
                background-color: #1976d2;
                border: 1px solid #42a5f5;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 6px;
            }
            QPushButton#apply_btn:hover {
                background-color: #2196f3;
                border-color: #64b5f6;
            }
            QPushButton#verifier_btn {
                background-color: #3949ab;
                border: 1px solid #5c6bc0;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 8px;
            }
            QPushButton#verifier_btn:hover {
                background-color: #3f51b5;
                border-color: #7986cb;
            }
            QComboBox, QLineEdit {
                background-color: #1a1a24;
                border: 1px solid #333344;
                border-radius: 5px;
                padding: 5px 8px;
                color: #ffffff;
            }
            QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #82aaff;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #1a1a24;
                border: 1px solid #333344;
                border-radius: 5px;
                padding: 4px 22px 4px 8px;
                color: #ffffff;
                font-weight: bold;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
                background-color: #2b2b3f;
                border-left: 1px solid #333344;
                border-bottom: 1px solid #333344;
                border-top-right-radius: 4px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
                background-color: #3d3d5a;
            }
            QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {
                background-color: #1a1a24;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
                background-color: #2b2b3f;
                border-left: 1px solid #333344;
                border-bottom-right-radius: 4px;
            }
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #3d3d5a;
            }
            QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
                background-color: #1a1a24;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QProgressBar {
                border: 1px solid #2a2a38;
                border-radius: 6px;
                text-align: center;
                background-color: #161620;
                min-height: 28px;
                font-weight: bold;
                color: #ffffff;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #00b0ff;
                border-radius: 5px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #2a2a38;
                height: 6px;
                background: #1a1a24;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #82aaff;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #82aaff;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QStatusBar {
                background-color: #0d0d12;
                color: #888899;
            }
        """)

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        # 0. Header bar: Language selector
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(0, 0, 0, 0)
        header_bar.addStretch()
        self.label_lang = QLabel("🌐")
        header_bar.addWidget(self.label_lang)
        self.combo_language = QComboBox()
        self.combo_language.setMinimumWidth(125)
        for code, name in LANGUAGES.items():
            self.combo_language.addItem(name, code)
        cur_code = I18nManager.get_instance().current_lang
        for idx in range(self.combo_language.count()):
            if self.combo_language.itemData(idx) == cur_code:
                self.combo_language.setCurrentIndex(idx)
                break
        self.combo_language.currentIndexChanged.connect(self._on_language_changed)
        header_bar.addWidget(self.combo_language)
        main_layout.addLayout(header_bar)

        # 1. Top Section: OBS Connection & Audio Device Configuration (Side-by-side)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # 1-A. OBS Connection Box
        self.obs_box = QGroupBox()
        self.obs_box.setMinimumWidth(320)
        obs_layout = QGridLayout(self.obs_box)
        obs_layout.setContentsMargins(10, 12, 10, 10)
        obs_layout.setSpacing(8)

        self.label_host_port = QLabel()
        obs_layout.addWidget(self.label_host_port, 0, 0)
        host_port_layout = QHBoxLayout()
        self.obs_host_input = QLineEdit("localhost")
        self.obs_host_input.setPlaceholderText("localhost")
        self.obs_host_input.setMinimumWidth(110)
        self.obs_port_input = QSpinBox()
        self.obs_port_input.setRange(1024, 65535)
        self.obs_port_input.setValue(4455)
        self.obs_port_input.setFixedWidth(96)
        host_port_layout.addWidget(self.obs_host_input, stretch=1)
        host_port_layout.addWidget(self.obs_port_input)
        obs_layout.addLayout(host_port_layout, 0, 1)

        self.label_password = QLabel()
        obs_layout.addWidget(self.label_password, 1, 0)
        self.obs_password_input = QLineEdit()
        self.obs_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_password_input.setPlaceholderText("設定している場合のみ入力")
        obs_layout.addWidget(self.obs_password_input, 1, 1)

        btn_status_layout = QHBoxLayout()
        self.obs_connect_btn = QPushButton()
        self.obs_connect_btn.clicked.connect(self._toggle_obs_connection)
        self.obs_status_label = QLabel()
        self.obs_status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
        btn_status_layout.addWidget(self.obs_connect_btn)
        btn_status_layout.addWidget(self.obs_status_label)
        obs_layout.addLayout(btn_status_layout, 2, 0, 1, 2)

        top_layout.addWidget(self.obs_box, stretch=4)

        # 1-B. Audio Hardware Device Selection & Volume Box
        self.device_box = QGroupBox()
        dev_layout = QGridLayout(self.device_box)
        dev_layout.setContentsMargins(10, 12, 10, 10)
        dev_layout.setSpacing(8)

        self.label_playback = QLabel()
        dev_layout.addWidget(self.label_playback, 0, 0)
        self.combo_out_device = QComboBox()
        self.combo_out_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_out_device.view().setMinimumWidth(420)
        self.combo_out_device.currentIndexChanged.connect(self._on_device_selection_changed)
        dev_layout.addWidget(self.combo_out_device, 0, 1)

        self.label_recording = QLabel()
        dev_layout.addWidget(self.label_recording, 1, 0)
        self.combo_in_device = QComboBox()
        self.combo_in_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_in_device.view().setMinimumWidth(420)
        self.combo_in_device.currentIndexChanged.connect(self._on_device_selection_changed)
        dev_layout.addWidget(self.combo_in_device, 1, 1)

        # Volume controls
        self.label_volume = QLabel()
        dev_layout.addWidget(self.label_volume, 2, 0)
        vol_layout = QHBoxLayout()
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(10, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        self.vol_label = QLabel("50%")
        self.vol_label.setFixedWidth(42)

        self.test_tone_btn = QPushButton()
        self.test_tone_btn.clicked.connect(self._play_test_tone)

        vol_layout.addWidget(self.vol_slider)
        vol_layout.addWidget(self.vol_label)
        vol_layout.addWidget(self.test_tone_btn)
        dev_layout.addLayout(vol_layout, 2, 1)

        top_layout.addWidget(self.device_box, stretch=5)
        main_layout.addLayout(top_layout)

        # 2. Middle Section: Plots (Waveform and Cross-Correlation)
        self.plot_box = QGroupBox()
        self.plot_box.setMinimumHeight(320)
        plot_layout = QVBoxLayout(self.plot_box)
        plot_layout.setContentsMargins(8, 10, 8, 16)
        self.plot_widget = SyncPlotWidget(self)
        self.plot_widget.setMinimumHeight(290)
        plot_layout.addWidget(self.plot_widget)
        main_layout.addWidget(self.plot_box, stretch=5)

        # 3. Bottom Section: Measurement & OBS Application Panel
        self.bottom_box = QGroupBox()
        self.bottom_box.setMinimumHeight(245)
        bottom_layout = QVBoxLayout(self.bottom_box)
        bottom_layout.setContentsMargins(12, 14, 12, 12)
        bottom_layout.setSpacing(10)

        # Top row: Measure button, mode selection, progress bar
        measure_row = QHBoxLayout()
        measure_row.setSpacing(10)

        self.combo_measure_mode = QComboBox()
        self.combo_measure_mode.addItem("3回測定 (標準・おすすめ)", 3)
        self.combo_measure_mode.addItem("1回測定 (クイック)", 1)
        self.combo_measure_mode.addItem("5回測定 (徹底検証・高信頼度)", 5)
        self.combo_measure_mode.currentIndexChanged.connect(self._save_settings)
        measure_row.addWidget(self.combo_measure_mode)

        self.measure_btn = QPushButton()
        self.measure_btn.setObjectName("measure_btn")
        self.measure_btn.clicked.connect(self._start_measurement)
        measure_row.addWidget(self.measure_btn, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 3)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedWidth(80)
        measure_row.addWidget(self.progress_bar)

        self.btn_open_verifier = QPushButton()
        self.btn_open_verifier.setObjectName("verifier_btn")
        self.btn_open_verifier.clicked.connect(self._open_verifier_window)
        measure_row.addWidget(self.btn_open_verifier)

        bottom_layout.addLayout(measure_row)

        # Results and Adjustment Row
        result_row = QHBoxLayout()
        result_row.setSpacing(12)

        # Result badge (Median + Runs history + Jitter) - Slimmer width, utilizing vertical space
        res_frame = QFrame()
        res_frame.setStyleSheet("background-color: #1a1a26; border-radius: 6px; padding: 6px;")
        res_layout = QVBoxLayout(res_frame)
        res_layout.setContentsMargins(8, 8, 8, 8)
        res_layout.setSpacing(6)

        self.delay_label = QLabel("検出遅延: -- ms")
        self.delay_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.delay_label.setStyleSheet("color: #00e5ff;")

        self.runs_label = QLabel("履歴: --")
        self.runs_label.setStyleSheet("color: #bbbbcc; font-size: 11px; line-height: 1.2;")
        self.runs_label.setWordWrap(True)

        self.jitter_badge = QLabel("ばらつき: --")
        self.jitter_badge.setStyleSheet("color: #888899; font-weight: bold; font-size: 11px;")
        self.jitter_badge.setWordWrap(True)

        res_layout.addWidget(self.delay_label)
        res_layout.addWidget(self.runs_label)
        res_layout.addWidget(self.jitter_badge)
        res_layout.addStretch()
        result_row.addWidget(res_frame, stretch=2)

        # Manual Adjustment Controls - 2-tier button layout to eliminate horizontal crowding
        adj_frame = QFrame()
        adj_frame.setStyleSheet("background-color: #1a1a26; border-radius: 6px; padding: 6px;")
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setContentsMargins(8, 6, 8, 6)
        adj_layout.setSpacing(6)

        # Row 1: Primary action button (Full width)
        self.btn_apply_measured = QPushButton()
        self.btn_apply_measured.setEnabled(False)
        self.btn_apply_measured.setStyleSheet("""
            QPushButton {
                background-color: #1565c0;
                color: #ffffff;
                font-weight: bold;
                padding: 5px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:disabled {
                background-color: #262635;
                color: #555566;
                border: 1px solid #333344;
            }
        """)
        self.btn_apply_measured.clicked.connect(self._apply_measured_to_adjustment)
        adj_layout.addWidget(self.btn_apply_measured)

        # Row 2: Secondary buttons side-by-side (OBS value & Raw 0ms)
        btn_sub_row = QHBoxLayout()
        btn_sub_row.setSpacing(6)

        self.btn_apply_obs = QPushButton()
        self.btn_apply_obs.setEnabled(False)
        self.btn_apply_obs.setStyleSheet("""
            QPushButton {
                background-color: #28283c;
                color: #bbbbdd;
                padding: 4px 6px;
                font-size: 11px;
                border: 1px solid #3d3d56;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #383854;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #1f1f2a;
                color: #555566;
                border: 1px solid #2a2a38;
            }
        """)
        self.btn_apply_obs.clicked.connect(self._apply_obs_to_adjustment)
        btn_sub_row.addWidget(self.btn_apply_obs, stretch=3)

        self.btn_reset_zero = QPushButton()
        self.btn_reset_zero.setStyleSheet("padding: 4px 6px; font-size: 11px;")
        self.btn_reset_zero.clicked.connect(self._reset_offset_to_zero)
        btn_sub_row.addWidget(self.btn_reset_zero, stretch=2)

        adj_layout.addLayout(btn_sub_row)

        # Row 3: Label and Spinbox side by side
        spin_row = QHBoxLayout()
        spin_row.setContentsMargins(0, 0, 0, 0)
        self.label_manual_trim = QLabel()
        spin_row.addWidget(self.label_manual_trim)
        spin_row.addStretch()

        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 2000.0)
        self.spin_offset.setDecimals(1)
        self.spin_offset.setSingleStep(0.1)
        self.spin_offset.setSuffix(" ms")
        self.spin_offset.setMinimumWidth(100)
        self.spin_offset.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spin_offset.valueChanged.connect(self._on_spinbox_changed)
        spin_row.addWidget(self.spin_offset)
        adj_layout.addLayout(spin_row)

        # Row 4: Delta trim buttons evenly distributed across full width
        trim_btn_row = QHBoxLayout()
        trim_btn_row.setSpacing(4)
        trim_btn_row.setContentsMargins(0, 0, 0, 0)

        for delta, text in [(-1.0, "-1ms"), (-0.1, "-0.1ms"), (+0.1, "+0.1ms"), (+1.0, "+1ms")]:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 4px 0px;
                    font-size: 11px;
                    font-weight: 500;
                    background-color: #232334;
                    border: 1px solid #3d3d52;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #313148;
                    border-color: #5c5c7a;
                }
            """)
            btn.clicked.connect(lambda checked=False, d=delta: self._adjust_offset(d))
            trim_btn_row.addWidget(btn)

        adj_layout.addLayout(trim_btn_row)

        self.slider_offset = QSlider(Qt.Orientation.Horizontal)
        self.slider_offset.setRange(0, 10000)  # 0.0 to 1000.0 ms (0.1ms step)
        self.slider_offset.valueChanged.connect(self._on_slider_changed)
        adj_layout.addWidget(self.slider_offset)
        result_row.addWidget(adj_frame, stretch=4)

        # OBS Target and Apply - Widest stretch to accommodate long source names
        apply_frame = QFrame()
        apply_frame.setStyleSheet("background-color: #1a1a26; border-radius: 6px; padding: 6px;")
        apply_layout = QVBoxLayout(apply_frame)
        apply_layout.setContentsMargins(8, 4, 8, 4)
        apply_layout.setSpacing(4)

        target_header = QHBoxLayout()
        target_header.setSpacing(6)
        self.label_obs_target = QLabel()
        target_header.addWidget(self.label_obs_target)
        target_header.addStretch()

        self.btn_fetch_obs = QPushButton()
        self.btn_fetch_obs.setEnabled(False)
        self.btn_fetch_obs.setStyleSheet("padding: 3px 8px; font-size: 11px;")
        self.btn_fetch_obs.clicked.connect(self._fetch_current_obs_offset)
        target_header.addWidget(self.btn_fetch_obs)
        apply_layout.addLayout(target_header)

        self.combo_obs_source = QComboBox()
        self.combo_obs_source.addItem("OBS未接続 (ソース選択不可)")
        self.combo_obs_source.setEnabled(False)
        self.combo_obs_source.setMinimumHeight(26)
        self.combo_obs_source.currentIndexChanged.connect(self._on_obs_source_selected)
        # Ensure dropdown popup list is wide enough (380px) so long source names never truncate with '...'
        self.combo_obs_source.view().setMinimumWidth(380)
        apply_layout.addWidget(self.combo_obs_source)

        status_row = QHBoxLayout()
        self.current_offset_label = QLabel()
        self.current_offset_label.setStyleSheet("color: #aaaabb; font-size: 11px;")
        status_row.addWidget(self.current_offset_label)

        self.diff_offset_label = QLabel("")
        self.diff_offset_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        status_row.addWidget(self.diff_offset_label)
        status_row.addStretch()
        apply_layout.addLayout(status_row)

        # Video source synchronization (Render Delay)
        self.check_sync_video = QCheckBox()
        self.check_sync_video.setStyleSheet("font-size: 11px; color: #aaccff; margin-top: 3px; margin-bottom: 2px;")
        self.check_sync_video.toggled.connect(self._on_video_check_toggled)
        apply_layout.addWidget(self.check_sync_video)

        self.video_container = QWidget()
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(2)

        self.combo_obs_video_source = QComboBox()
        self.combo_obs_video_source.addItem("OBS未接続 (映像ソース選択不可)")
        self.combo_obs_video_source.setEnabled(False)
        self.combo_obs_video_source.setMinimumHeight(26)
        self.combo_obs_video_source.currentIndexChanged.connect(self._on_obs_video_source_selected)
        self.combo_obs_video_source.view().setMinimumWidth(380)
        video_layout.addWidget(self.combo_obs_video_source)

        video_status_row = QHBoxLayout()
        self.current_video_delay_label = QLabel()
        self.current_video_delay_label.setStyleSheet("color: #8899aa; font-size: 10px;")
        video_status_row.addWidget(self.current_video_delay_label)
        video_status_row.addStretch()
        video_layout.addLayout(video_status_row)

        self.video_container.setVisible(False)
        apply_layout.addWidget(self.video_container)

        self.apply_btn = QPushButton()
        self.apply_btn.setObjectName("apply_btn")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setMinimumHeight(32)
        self.apply_btn.clicked.connect(self._apply_offset_to_obs)
        apply_layout.addWidget(self.apply_btn)

        result_row.addWidget(apply_frame, stretch=5)
        bottom_layout.addLayout(result_row)
        main_layout.addWidget(self.bottom_box, stretch=3)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initial translation
        self.retranslate_ui()
        self.status_bar.showMessage(t("status_ready"))

    def _on_language_changed(self, index: int) -> None:
        """Handle language selection change from header dropdown."""
        lang_code = self.combo_language.itemData(index)
        if lang_code and lang_code in LANGUAGES:
            I18nManager.get_instance().current_lang = str(lang_code)
            self.settings.setValue("app/language", str(lang_code))
            self.retranslate_ui()
            # Also refresh device names so recommended badges match language
            self._refresh_audio_devices()

    def retranslate_ui(self) -> None:
        """Dynamically update all UI labels, buttons, and group titles in current language."""
        self.setWindowTitle(t("app_title"))

        # Header
        self.label_lang.setText("🌐")

        # Group 1: OBS
        self.obs_box.setTitle(t("obs_group"))
        self.label_host_port.setText(t("obs_host_port"))
        self.label_password.setText(t("obs_password"))
        self.obs_password_input.setPlaceholderText(t("obs_password_placeholder"))
        if self.obs_client.is_connected:
            self.obs_connect_btn.setText(t("obs_disconnect"))
            self.obs_status_label.setText(t("obs_connected"))
        else:
            self.obs_connect_btn.setText(t("obs_connect"))
            self.obs_status_label.setText(t("obs_disconnected"))

        # Group 2: Audio Devices & Volume
        self.device_box.setTitle(t("audio_group"))
        self.label_playback.setText(t("audio_playback"))
        self.label_recording.setText(t("audio_recording"))
        self.label_volume.setText(t("audio_volume"))
        self.test_tone_btn.setText(t("audio_test_tone"))
        self.test_tone_btn.setToolTip(t("audio_test_tooltip"))

        # Group 3: Plot Widget
        self.plot_box.setTitle(t("plot_group"))
        self.plot_widget.retranslate_ui()

        # Group 4: Measurement and OBS Apply
        self.bottom_box.setTitle(t("measure_group"))
        self.combo_measure_mode.blockSignals(True)
        self.combo_measure_mode.setItemText(0, t("mode_3_runs"))
        self.combo_measure_mode.setItemText(1, t("mode_1_run"))
        self.combo_measure_mode.setItemText(2, t("mode_5_runs"))
        self.combo_measure_mode.blockSignals(False)

        if self.worker is None or not self.worker.isRunning():
            self.measure_btn.setText(t("btn_start_measure"))

        self.btn_open_verifier.setText(t("btn_open_verifier"))
        self.btn_open_verifier.setToolTip(t("btn_open_verifier_tooltip"))
        if self.verifier_window is not None and self.verifier_window.isVisible():
            self.verifier_window.retranslate_ui()

        self.btn_reset_zero.setText(t("btn_reset_zero"))
        self.label_manual_trim.setText(t("manual_trim"))

        # Applied / measured button
        if self._last_measured_delay_ms > 0.0:
            if abs(self.spin_offset.value() - self._last_measured_delay_ms) < 0.05:
                self.btn_apply_measured.setText(t("btn_applied_measured", delay=self._last_measured_delay_ms))
            else:
                self.btn_apply_measured.setText(t("btn_apply_measured", delay=self._last_measured_delay_ms))
        else:
            self.btn_apply_measured.setText(t("btn_apply_measured_unmeasured"))

        # OBS current value button
        if self._latest_obs_offset is not None:
            self.btn_apply_obs.setText(t("btn_apply_obs", offset=self._latest_obs_offset))
            self.btn_apply_obs.setEnabled(True)
        else:
            self.btn_apply_obs.setText(t("btn_apply_obs_none"))
            self.btn_apply_obs.setEnabled(False)

        # OBS Target and Apply
        self.label_obs_target.setText(t("obs_target_source"))
        self.btn_fetch_obs.setText(t("btn_fetch_obs"))
        self.btn_fetch_obs.setToolTip(t("btn_fetch_obs_tooltip"))
        self.apply_btn.setText(t("btn_apply_to_obs"))

        # Video sync options
        self.check_sync_video.setText(t("obs_sync_video"))

        if not self.obs_client.is_connected:
            if self.combo_obs_source.count() > 0:
                self.combo_obs_source.setItemText(0, t("obs_not_connected_source"))
            self.current_offset_label.setText(t("current_obs_none"))

            if self.combo_obs_video_source.count() > 0:
                self.combo_obs_video_source.setItemText(0, t("obs_not_connected_video_source"))
            self.current_video_delay_label.setText(t("current_video_delay_none"))
        else:
            idx = self.combo_obs_source.currentIndex()
            if 0 <= idx < len(self.obs_sources):
                src = self.obs_sources[idx]
                self.current_offset_label.setText(t("current_obs_val", offset=src.sync_offset_ms))
            else:
                self.current_offset_label.setText(t("current_obs_none"))

            v_idx = self.combo_obs_video_source.currentIndex()
            if 0 <= v_idx < len(self.obs_video_sources):
                v_src = self.obs_video_sources[v_idx]
                self.current_video_delay_label.setText(t("current_video_delay_val", delay=v_src.render_delay_ms))
            else:
                self.current_video_delay_label.setText(t("current_video_delay_none"))

        self._update_obs_diff_display()

        # Results badges
        if self.last_multi_result:
            median_ms = max(0.0, self.last_multi_result.median_delay_ms)
            self.delay_label.setText(t("detected_delay", delay=median_ms))
            runs_strs = [f"{r.delay_ms:.1f}ms" for r in self.last_multi_result.individual_results]
            if len(runs_strs) > 1:
                self.runs_label.setText(t("runs_history", history=" / ".join(runs_strs)))
            else:
                self.runs_label.setText(t("single_run", run=runs_strs[0]))

            if len(self.last_multi_result.individual_results) > 1:
                jitter = self.last_multi_result.jitter_ms
                if jitter < 0.05:
                    self.jitter_badge.setText(t("badge_perfect"))
                elif jitter <= 1.0:
                    self.jitter_badge.setText(t("badge_max_diff_stable", diff=jitter))
                elif jitter <= 3.0:
                    self.jitter_badge.setText(t("badge_max_diff_moderate", diff=jitter))
                else:
                    self.jitter_badge.setText(t("badge_max_diff_noisy", diff=jitter))
            else:
                conf_pct = int(self.last_multi_result.overall_confidence * 100)
                self.jitter_badge.setText(t("badge_confidence", conf=conf_pct))
        else:
            self.delay_label.setText(t("detected_delay", delay=0.0).replace("0.0", "--"))
            self.runs_label.setText(f"{t('runs_history', history='--').split(':')[0]}: --")
            self.jitter_badge.setText(t("badge_pending"))

    # --- Settings Persistence ---
    def _load_saved_settings(self) -> None:
        """Load persistent settings from QSettings."""
        saved_lang = self.settings.value("app/language", "")
        if saved_lang and saved_lang in LANGUAGES:
            I18nManager.get_instance().current_lang = str(saved_lang)
            self.combo_language.blockSignals(True)
            for idx in range(self.combo_language.count()):
                if self.combo_language.itemData(idx) == saved_lang:
                    self.combo_language.setCurrentIndex(idx)
                    break
            self.combo_language.blockSignals(False)
            self.retranslate_ui()

        host = self.settings.value("obs/host", "localhost")
        port = int(self.settings.value("obs/port", 4455))
        password = self.settings.value("obs/password", "")
        vol = int(self.settings.value("audio/volume_pct", 50))
        mode_idx = int(self.settings.value("measure/mode_idx", 0))

        self.obs_host_input.setText(host)
        self.obs_port_input.setValue(port)
        self.obs_password_input.setText(password)

        self.vol_slider.setValue(vol)
        self.vol_label.setText(f"{vol}%")
        self.analyzer.set_amplitude(vol / 100.0)

        if 0 <= mode_idx < self.combo_measure_mode.count():
            self.combo_measure_mode.setCurrentIndex(mode_idx)
            total = int(self.combo_measure_mode.currentData() or 3)
            self.progress_bar.setRange(0, total)

        sync_video = self.settings.value("obs/sync_video", False, type=bool)
        self.check_sync_video.setChecked(sync_video)
        self.video_container.setVisible(sync_video)

    def _save_settings(self) -> None:
        """Save settings to QSettings."""
        cur_lang = self.combo_language.currentData()
        if cur_lang:
            self.settings.setValue("app/language", cur_lang)
        self.settings.setValue("obs/host", self.obs_host_input.text().strip())
        self.settings.setValue("obs/port", self.obs_port_input.value())
        self.settings.setValue("obs/password", self.obs_password_input.text())
        self.settings.setValue("obs/sync_video", self.check_sync_video.isChecked())
        total = int(self.combo_measure_mode.currentData() or 3)
        self.progress_bar.setRange(0, total)
        self.settings.setValue("audio/volume_pct", self.vol_slider.value())
        self.settings.setValue("measure/mode_idx", self.combo_measure_mode.currentIndex())

        if self.combo_out_device.count() > 0:
            self.settings.setValue("audio/output_device_name", self.combo_out_device.currentText())
        if self.combo_in_device.count() > 0:
            self.settings.setValue("audio/input_device_name", self.combo_in_device.currentText())

    def _on_volume_changed(self, value: int) -> None:
        self.vol_label.setText(f"{value}%")
        self.analyzer.set_amplitude(value / 100.0)
        self._save_settings()

    def _play_test_tone(self) -> None:
        out_idx = self.combo_out_device.currentData()
        amp = self.vol_slider.value() / 100.0
        self.test_worker = TestToneWorker(out_device_idx=out_idx, amplitude=amp)
        self.test_worker.start()
        self.status_bar.showMessage(t("status_test_tone_played"))

    def _on_device_selection_changed(self) -> None:
        self._save_settings()
        if self.verifier_window is not None and self.verifier_window.isVisible():
            out_idx = self.combo_out_device.currentData()
            cur_src = self._get_selected_obs_source_name()
            self.verifier_window.update_device_and_source(out_idx, cur_src)

    # --- Device Management ---
    def _refresh_audio_devices(self) -> None:
        self.combo_out_device.blockSignals(True)
        self.combo_in_device.blockSignals(True)
        self.combo_out_device.clear()
        self.combo_in_device.clear()

        try:
            out_devs, in_devs = self.audio_engine.get_devices()
            saved_out = self.settings.value("audio/output_device_name", "")
            saved_in = self.settings.value("audio/input_device_name", "")

            def get_api_rank(hostapi: str) -> int:
                h = hostapi.lower()
                if "wasapi" in h:
                    return 0
                if "directsound" in h:
                    return 1
                if "wdm" in h:
                    return 2
                if "mme" in h:
                    return 3
                return 4

            # Sort so WASAPI comes first, then DirectSound, WDM-KS, and MME last
            out_devs.sort(key=lambda d: (get_api_rank(d.hostapi_name), not d.is_default_output, d.name))
            in_devs.sort(key=lambda d: (get_api_rank(d.hostapi_name), not d.is_default_input, d.name))

            def make_label(dev: AudioDeviceInfo, is_output: bool) -> str:
                h = dev.hostapi_name
                is_def = dev.is_default_output if is_output else dev.is_default_input
                if "wasapi" in h.lower():
                    badge = t("device_rec_wasapi")
                elif "mme" in h.lower():
                    badge = t("device_compat_mme")
                else:
                    badge = f"({h})"
                def_badge = t("device_default") if is_def else ""
                return f"{dev.name} {badge}{def_badge}"

            out_match_idx = -1
            first_wasapi_out = -1
            for idx, dev in enumerate(out_devs):
                label = make_label(dev, is_output=True)
                self.combo_out_device.addItem(label, dev.index)
                if "wasapi" in dev.hostapi_name.lower():
                    if first_wasapi_out == -1 or dev.is_default_output:
                        first_wasapi_out = idx
                if saved_out and (saved_out == label or saved_out in label):
                    out_match_idx = idx

            in_match_idx = -1
            first_wasapi_in = -1
            for idx, dev in enumerate(in_devs):
                label = make_label(dev, is_output=False)
                self.combo_in_device.addItem(label, dev.index)
                if "wasapi" in dev.hostapi_name.lower():
                    if first_wasapi_in == -1 or dev.is_default_input:
                        first_wasapi_in = idx
                if saved_in and (saved_in == label or saved_in in label):
                    in_match_idx = idx

            # Choose best default
            chosen_out = out_match_idx if out_match_idx >= 0 else (first_wasapi_out if first_wasapi_out >= 0 else 0)
            chosen_in = in_match_idx if in_match_idx >= 0 else (first_wasapi_in if first_wasapi_in >= 0 else 0)

            if self.combo_out_device.count() > 0:
                self.combo_out_device.setCurrentIndex(chosen_out)
            if self.combo_in_device.count() > 0:
                self.combo_in_device.setCurrentIndex(chosen_in)

            self.status_bar.showMessage(t("status_device_refreshed", out_count=len(out_devs), in_count=len(in_devs)))
        except Exception as e:
            QMessageBox.warning(self, t("dialog_device_error_title"), t("dialog_device_error_msg", error=str(e)))
        finally:
            self.combo_out_device.blockSignals(False)
            self.combo_in_device.blockSignals(False)

    # --- OBS Integration ---
    def _toggle_obs_connection(self) -> None:
        if self.obs_client.is_connected:
            self.obs_client.disconnect()
            self._update_obs_ui_disconnected()
        else:
            host = self.obs_host_input.text().strip() or "localhost"
            port = self.obs_port_input.value()
            password = self.obs_password_input.text()

            self.obs_client.host = host
            self.obs_client.port = port
            self.obs_client.password = password

            try:
                self.obs_client.connect()
                self._update_obs_ui_connected()
                self._save_settings()
            except Exception as e:
                self._update_obs_ui_disconnected()
                QMessageBox.critical(
                    self,
                    t("dialog_obs_connect_error_title"),
                    t("dialog_obs_connect_error_msg", port=port, error=str(e))
                )

    def _update_obs_ui_connected(self) -> None:
        self.obs_status_label.setText(t("obs_connected"))
        self.obs_status_label.setStyleSheet("color: #00e676; font-weight: bold;")
        self.obs_connect_btn.setText(t("obs_disconnect"))
        self.obs_host_input.setEnabled(False)
        self.obs_port_input.setEnabled(False)
        self.obs_password_input.setEnabled(False)

        # Load audio sources
        self._reload_obs_sources()

    def _update_obs_ui_disconnected(self) -> None:
        self.obs_status_label.setText(t("obs_disconnected"))
        self.obs_status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
        self.obs_connect_btn.setText(t("obs_connect"))
        self.obs_host_input.setEnabled(True)
        self.obs_port_input.setEnabled(True)
        self.obs_password_input.setEnabled(True)

        self.combo_obs_source.clear()
        self.combo_obs_source.addItem(t("obs_not_connected_source"))
        self.combo_obs_source.setEnabled(False)
        self.btn_fetch_obs.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.current_offset_label.setText(t("current_obs_none"))
        self.diff_offset_label.setText("")
        self._latest_obs_offset = None
        self.btn_apply_obs.setText(t("btn_apply_obs_none"))
        self.btn_apply_obs.setEnabled(False)

        self.combo_obs_video_source.clear()
        self.combo_obs_video_source.addItem(t("obs_not_connected_video_source"))
        self.combo_obs_video_source.setEnabled(False)
        self.current_video_delay_label.setText(t("current_video_delay_none"))
        self._latest_obs_video_delay = None
        self.obs_video_sources.clear()
        if self.verifier_window is not None and self.verifier_window.isVisible():
            out_idx = self.combo_out_device.currentData()
            self.verifier_window.update_device_and_source(out_idx, None)

    def _reload_obs_sources(self) -> None:
        self.combo_obs_source.clear()
        self.combo_obs_video_source.clear()
        try:
            self.obs_sources = self.obs_client.get_audio_sources()
            if not self.obs_sources:
                self.combo_obs_source.addItem(t("obs_no_sources"))
                self.combo_obs_source.setEnabled(False)
                self.btn_fetch_obs.setEnabled(False)
                self.apply_btn.setEnabled(False)
                self._latest_obs_offset = None
                self.btn_apply_obs.setText(t("btn_apply_obs_none"))
                self.btn_apply_obs.setEnabled(False)
            else:
                self.combo_obs_source.setEnabled(True)
                self.btn_fetch_obs.setEnabled(True)
                self.apply_btn.setEnabled(True)

                recommended_idx = 0
                for idx, src in enumerate(self.obs_sources):
                    label = f"{src.name} [{src.sync_offset_ms} ms]"
                    if "output" in src.kind.lower() or "desktop" in src.name.lower() or "オケ" in src.name or "デスクトップ" in src.name:
                        label += f" {t('obs_recommended_source')}"
                        recommended_idx = idx
                    self.combo_obs_source.addItem(label, src)
                    self.combo_obs_source.setItemData(idx, label, Qt.ItemDataRole.ToolTipRole)

                self.combo_obs_source.setCurrentIndex(recommended_idx)
                self._on_obs_source_selected(recommended_idx)

            # Load video sources
            try:
                self.obs_video_sources = self.obs_client.get_video_sources()
                if not self.obs_video_sources:
                    self.combo_obs_video_source.addItem(t("obs_no_video_sources"))
                    self.combo_obs_video_source.setEnabled(False)
                else:
                    self.combo_obs_video_source.setEnabled(True)
                    for v_idx, v_src in enumerate(self.obs_video_sources):
                        v_label = f"{v_src.name} [{v_src.render_delay_ms} ms]"
                        self.combo_obs_video_source.addItem(v_label, v_src)
                        self.combo_obs_video_source.setItemData(v_idx, v_label, Qt.ItemDataRole.ToolTipRole)
                    self.combo_obs_video_source.setCurrentIndex(0)
                    self._on_obs_video_source_selected(0)
            except Exception:
                self.combo_obs_video_source.addItem(t("obs_no_video_sources"))
                self.combo_obs_video_source.setEnabled(False)

            self.status_bar.showMessage(t("status_obs_loaded", count=len(self.obs_sources)))
        except Exception as e:
            QMessageBox.warning(self, t("dialog_source_error_title"), t("dialog_source_error_msg", error=str(e)))

    def _on_video_check_toggled(self, checked: bool) -> None:
        self.video_container.setVisible(checked)
        self._save_settings()

    def _on_obs_video_source_selected(self, index: int) -> None:
        if 0 <= index < len(self.obs_video_sources):
            v_src = self.obs_video_sources[index]
            self._latest_obs_video_delay = v_src.render_delay_ms
            self.current_video_delay_label.setText(t("current_video_delay_val", delay=v_src.render_delay_ms))
        else:
            self._latest_obs_video_delay = None
            self.current_video_delay_label.setText(t("current_video_delay_none"))

    def _fetch_current_obs_offset(self) -> None:
        """Fetch real-time sync offset from OBS for the currently selected audio source and apply to preview."""
        if not self.obs_client.is_connected:
            return
        idx = self.combo_obs_source.currentIndex()
        if idx < 0 or not self.obs_sources:
            return
        src = self.combo_obs_source.itemData(idx)
        if not isinstance(src, ObsAudioSource):
            return

        try:
            latest_offset = self.obs_client.get_sync_offset(src.name)
            src.sync_offset_ms = latest_offset
            self._latest_obs_offset = latest_offset

            # Update combo text
            label = f"{src.name} [{latest_offset} ms]"
            if "output" in src.kind.lower() or "desktop" in src.name.lower() or "オケ" in src.name or "デスクトップ" in src.name:
                label += f" {t('obs_recommended_source')}"
            self.combo_obs_source.setItemText(idx, label)
            self.combo_obs_source.setItemData(idx, label, Qt.ItemDataRole.ToolTipRole)
            self.current_offset_label.setText(t("current_obs_val", offset=latest_offset))

            # Update button in manual adjustment row
            self.btn_apply_obs.setText(t("btn_apply_obs", offset=latest_offset))
            self.btn_apply_obs.setEnabled(True)

            # Automatically reflect to manual adjustment spinbox so user immediately sees waveform shift!
            self.spin_offset.setValue(float(latest_offset))

            self._update_obs_diff_display()
            self.status_bar.showMessage(t("status_fetched_obs", name=src.name, offset=latest_offset))
        except Exception as e:
            QMessageBox.warning(self, t("dialog_fetch_error_title"), t("dialog_fetch_error_msg", error=str(e)))

    def _update_obs_diff_display(self) -> None:
        """Update difference indicator between current OBS offset and target offset."""
        if not self.obs_client.is_connected:
            self.diff_offset_label.setText("")
            return
        idx = self.combo_obs_source.currentIndex()
        if idx < 0 or not self.obs_sources:
            self.diff_offset_label.setText("")
            return
        src = self.combo_obs_source.itemData(idx)
        if not isinstance(src, ObsAudioSource):
            self.diff_offset_label.setText("")
            return

        current_ms = float(src.sync_offset_ms)
        target_ms = round(float(self.spin_offset.value()), 1)
        diff = target_ms - current_ms

        if self._last_measured_delay_ms > 0.0 or target_ms > 0.0:
            if abs(diff) < 0.05:
                self.diff_offset_label.setText(t("diff_matched"))
                self.diff_offset_label.setStyleSheet("color: #00e676; font-size: 11px; font-weight: bold;")
            elif diff > 0:
                self.diff_offset_label.setText(t("diff_needed", diff=diff))
                self.diff_offset_label.setStyleSheet("color: #00e5ff; font-size: 11px; font-weight: bold;")
            else:
                self.diff_offset_label.setText(t("diff_value", diff=diff))
                self.diff_offset_label.setStyleSheet("color: #ffca28; font-size: 11px; font-weight: bold;")
        else:
            self.diff_offset_label.setText("")

    def _on_obs_source_selected(self, index: int) -> None:
        if index < 0 or not self.obs_sources:
            return
        src = self.combo_obs_source.itemData(index)
        if isinstance(src, ObsAudioSource):
            self._latest_obs_offset = src.sync_offset_ms
            self.btn_apply_obs.setText(t("btn_apply_obs", offset=src.sync_offset_ms))
            self.btn_apply_obs.setEnabled(True)
            self.current_offset_label.setText(t("current_obs_val", offset=src.sync_offset_ms))
            self._update_obs_diff_display()
            if self.verifier_window is not None and self.verifier_window.isVisible():
                out_idx = self.combo_out_device.currentData()
                self.verifier_window.update_device_and_source(out_idx, src.name)

    # --- Measurement Flow ---
    def _start_measurement(self) -> None:
        out_idx = self.combo_out_device.currentData()
        in_idx = self.combo_in_device.currentData()
        total_runs = int(self.combo_measure_mode.currentData() or 3)

        self.measure_btn.setEnabled(False)
        self.measure_btn.setText(t("btn_measuring", current=1, total=total_runs))
        self.progress_bar.setRange(0, total_runs)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage(t("status_measuring", total=total_runs))

        self.worker = MeasurementWorker(
            analyzer=self.analyzer,
            audio_engine=self.audio_engine,
            out_device_idx=out_idx,
            in_device_idx=in_idx,
            total_runs=total_runs,
        )
        self.worker.step_progress.connect(self._on_step_progress)
        self.worker.finished_measurement.connect(self._on_measurement_finished)
        self.worker.error_occurred.connect(self._on_measurement_error)
        self.worker.start()

    def _on_step_progress(self, current: int, total: int) -> None:
        self.measure_btn.setText(t("btn_measuring", current=current, total=total))
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(t("status_sampling", current=current, total=total))

    def _on_measurement_finished(self, multi: MultiMeasureResult, best_recorded: np.ndarray) -> None:
        self.measure_btn.setEnabled(True)
        self.measure_btn.setText(t("btn_start_measure"))
        self.progress_bar.setValue(self.progress_bar.maximum())

        self.last_multi_result = multi
        self.last_recorded = best_recorded

        median_ms = max(0.0, multi.median_delay_ms)
        self.delay_label.setText(t("detected_delay", delay=median_ms))

        # Runs history text
        runs_strs = [f"{r.delay_ms:.1f}ms" for r in multi.individual_results]
        if len(runs_strs) > 1:
            self.runs_label.setText(t("runs_history", history=" / ".join(runs_strs)))
        else:
            self.runs_label.setText(t("single_run", run=runs_strs[0]))

        # Jitter and stability badge
        if len(multi.individual_results) > 1:
            jitter = multi.jitter_ms
            if jitter < 0.05:
                stab_txt = t("badge_perfect")
                stab_color = "#00e676"
            elif jitter <= 1.0:
                stab_txt = t("badge_max_diff_stable", diff=jitter)
                stab_color = "#00e676"
            elif jitter <= 3.0:
                stab_txt = t("badge_max_diff_moderate", diff=jitter)
                stab_color = "#ffca28"
            else:
                stab_txt = t("badge_max_diff_noisy", diff=jitter)
                stab_color = "#ff5252"
            self.jitter_badge.setText(stab_txt)
            self.jitter_badge.setStyleSheet(f"color: {stab_color}; font-weight: bold; font-size: 11px;")
        else:
            conf_pct = int(multi.overall_confidence * 100)
            self.jitter_badge.setText(t("badge_confidence", conf=conf_pct))
            self.jitter_badge.setStyleSheet("color: #00e676; font-weight: bold; font-size: 11px;")

        # Set manual adjustment controls with 0.1ms precision
        precise_ms = round(median_ms, 1)
        self._last_measured_delay_ms = precise_ms
        self.btn_apply_measured.setEnabled(True)

        if self._has_applied_measured or self.spin_offset.value() > 0.0:
            self._has_applied_measured = True
            self.spin_offset.blockSignals(True)
            self.slider_offset.blockSignals(True)
            self.spin_offset.setValue(precise_ms)
            slider_val = int(round(min(1000.0, precise_ms) * 10))
            self.slider_offset.setValue(slider_val)
            self.spin_offset.blockSignals(False)
            self.slider_offset.blockSignals(False)

            self.btn_apply_measured.setText(t("btn_applied_measured", delay=precise_ms))

            self.plot_widget.set_data(
                ref_signal=self.analyzer.reference_signal,
                rec_signal=best_recorded,
                sample_rate=self.analyzer.sample_rate,
                result=multi.best_result,
                initial_offset_ms=precise_ms,
            )
            self.status_bar.showMessage(t("status_measured_auto", delay=precise_ms))
        else:
            self.spin_offset.blockSignals(True)
            self.slider_offset.blockSignals(True)
            self.spin_offset.setValue(0.0)
            self.slider_offset.setValue(0)
            self.spin_offset.blockSignals(False)
            self.slider_offset.blockSignals(False)

            self.btn_apply_measured.setText(t("btn_apply_measured", delay=precise_ms))

            self.plot_widget.set_data(
                ref_signal=self.analyzer.reference_signal,
                rec_signal=best_recorded,
                sample_rate=self.analyzer.sample_rate,
                result=multi.best_result,
                initial_offset_ms=0.0,
            )
            self.status_bar.showMessage(t("status_measured_guide", delay=precise_ms))
        self._update_obs_diff_display()

    def _on_measurement_error(self, error_msg: str) -> None:
        self.measure_btn.setEnabled(True)
        self.measure_btn.setText(t("btn_start_measure"))
        self.progress_bar.setValue(0)
        self.status_bar.showMessage(t("status_error"))
        QMessageBox.critical(self, t("dialog_measure_error_title"), t("dialog_measure_error_msg", error=error_msg))

    # --- Manual Adjustment ---
    def _apply_measured_to_adjustment(self) -> None:
        """Apply the last measured delay into manual spinbox."""
        if self._last_measured_delay_ms <= 0.0:
            return
        self._has_applied_measured = True
        self.spin_offset.setValue(self._last_measured_delay_ms)
        self.btn_apply_measured.setText(t("btn_applied_measured", delay=self._last_measured_delay_ms))
        self.status_bar.showMessage(t("status_applied_adj", delay=self._last_measured_delay_ms))
        self._update_obs_diff_display()

    def _apply_obs_to_adjustment(self) -> None:
        """Apply current OBS offset to manual adjustment to preview current OBS alignment."""
        if self._latest_obs_offset is None:
            return
        self.spin_offset.setValue(float(self._latest_obs_offset))
        self._update_obs_diff_display()
        src_name = ""
        idx = self.combo_obs_source.currentIndex()
        if 0 <= idx < len(self.obs_sources):
            src_name = self.obs_sources[idx].name
        self.status_bar.showMessage(t("status_fetched_obs", name=src_name, offset=self._latest_obs_offset))

    def _reset_offset_to_zero(self) -> None:
        """Reset manual offset to 0ms to inspect uncorrected raw delay."""
        self.spin_offset.setValue(0.0)
        if self._last_measured_delay_ms > 0.0:
            self.btn_apply_measured.setText(t("btn_apply_measured", delay=self._last_measured_delay_ms))
        self._update_obs_diff_display()
        self.status_bar.showMessage(t("status_reset_zero"))

    def _adjust_offset(self, delta: float) -> None:
        """Adjust offset by a relative delta (+1, -1, +0.1, -0.1 ms)."""
        new_val = max(0.0, min(self.spin_offset.maximum(), self.spin_offset.value() + delta))
        self.spin_offset.setValue(round(new_val, 1))

    def _on_spinbox_changed(self, value: float) -> None:
        self.slider_offset.blockSignals(True)
        slider_val = int(round(min(1000.0, value) * 10))
        self.slider_offset.setValue(slider_val)
        self.slider_offset.blockSignals(False)
        self.plot_widget.update_manual_offset(float(value))

        # Update apply button text
        if self._last_measured_delay_ms > 0.0:
            if abs(value - self._last_measured_delay_ms) < 0.05:
                self.btn_apply_measured.setText(t("btn_applied_measured", delay=self._last_measured_delay_ms))
            else:
                self.btn_apply_measured.setText(t("btn_apply_measured", delay=self._last_measured_delay_ms))

        self._update_obs_diff_display()

    def _on_slider_changed(self, value: int) -> None:
        float_val = value / 10.0
        self.spin_offset.blockSignals(True)
        self.spin_offset.setValue(float_val)
        self.spin_offset.blockSignals(False)
        self.plot_widget.update_manual_offset(float_val)

        # Update apply button text
        if self._last_measured_delay_ms > 0.0:
            if abs(float_val - self._last_measured_delay_ms) < 0.05:
                self.btn_apply_measured.setText(t("btn_applied_measured", delay=self._last_measured_delay_ms))
            else:
                self.btn_apply_measured.setText(t("btn_apply_measured", delay=self._last_measured_delay_ms))
        self._update_obs_diff_display()

    # --- Apply to OBS ---
    def _apply_offset_to_obs(self) -> None:
        if not self.obs_client.is_connected:
            QMessageBox.warning(self, t("dialog_obs_unconnected_title"), t("dialog_obs_unconnected_msg"))
            return

        idx = self.combo_obs_source.currentIndex()
        if idx < 0 or not self.obs_sources:
            return

        src = self.combo_obs_source.itemData(idx)
        if not isinstance(src, ObsAudioSource):
            return

        target_offset_ms = round(self.spin_offset.value(), 1)
        # Round to integer for OBS Studio compatibility
        target_int_ms = int(round(target_offset_ms))
        diff = target_int_ms - src.sync_offset_ms
        diff_str = f"+{diff} ms" if diff > 0 else f"{diff} ms"

        # Check video sync
        sync_video = self.check_sync_video.isChecked()
        video_src: Optional[ObsVideoSource] = None
        v_idx = self.combo_obs_video_source.currentIndex()
        if sync_video and 0 <= v_idx < len(self.obs_video_sources):
            cand_v_src = self.combo_obs_video_source.itemData(v_idx)
            if isinstance(cand_v_src, ObsVideoSource):
                video_src = cand_v_src

        if video_src:
            video_target_ms = min(500, target_int_ms)
            limit_note = f"\n{t('warn_render_delay_limit')}" if target_int_ms > 500 else ""
            confirm_msg = t(
                "dialog_confirm_apply_with_video_msg",
                audio_name=src.name,
                audio_target=target_int_ms,
                video_name=video_src.name,
                video_target=video_target_ms,
                limit_note=limit_note,
            )
        else:
            confirm_msg = t(
                "dialog_confirm_apply_msg",
                name=src.name,
                current=src.sync_offset_ms,
                target=target_int_ms,
                diff=diff_str,
            )

        confirm = QMessageBox.question(
            self,
            t("dialog_confirm_apply_title"),
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            # 1. Apply audio offset (rounded to integer)
            actual_audio_ms = self.obs_client.set_sync_offset(src.name, target_int_ms)
            src.sync_offset_ms = actual_audio_ms
            self._has_applied_measured = True
            self.current_offset_label.setText(t("current_obs_val", offset=actual_audio_ms))

            label = f"{src.name} [{actual_audio_ms} ms]"
            if "output" in src.kind.lower() or "desktop" in src.name.lower() or "オケ" in src.name or "デスクトップ" in src.name:
                label += f" {t('obs_recommended_source')}"
            self.combo_obs_source.setItemText(idx, label)
            self.combo_obs_source.setItemData(idx, label, Qt.ItemDataRole.ToolTipRole)
            self._update_obs_diff_display()

            # 2. Apply video render delay if enabled
            if video_src:
                actual_vid_ms = self.obs_client.set_render_delay(video_src.name, target_int_ms)
                video_src.render_delay_ms = actual_vid_ms
                self._latest_obs_video_delay = actual_vid_ms
                v_label = f"{video_src.name} [{actual_vid_ms} ms]"
                self.combo_obs_video_source.setItemText(v_idx, v_label)
                self.combo_obs_video_source.setItemData(v_idx, v_label, Qt.ItemDataRole.ToolTipRole)
                self.current_video_delay_label.setText(t("current_video_delay_val", delay=actual_vid_ms))

                QMessageBox.information(
                    self,
                    t("dialog_applied_title"),
                    t(
                        "dialog_applied_with_video_msg",
                        audio_name=src.name,
                        audio_target=actual_audio_ms,
                        video_name=video_src.name,
                        video_target=actual_vid_ms,
                    ),
                )
                self.status_bar.showMessage(
                    t(
                        "status_applied_obs_with_video",
                        audio_name=src.name,
                        audio_offset=actual_audio_ms,
                        video_name=video_src.name,
                        video_offset=actual_vid_ms,
                    )
                )
            else:
                QMessageBox.information(
                    self,
                    t("dialog_applied_title"),
                    t("dialog_applied_msg", name=src.name, target=actual_audio_ms)
                )
                self.status_bar.showMessage(t("status_applied_obs", name=src.name, offset=actual_audio_ms))
        except Exception as e:
            QMessageBox.critical(self, t("dialog_apply_error_title"), t("dialog_apply_error_msg", error=str(e)))

    def _get_selected_obs_source_name(self) -> Optional[str]:
        """Helper to get currently selected OBS audio source name if connected."""
        if not self.obs_client.is_connected or not self.obs_sources:
            return None
        idx = self.combo_obs_source.currentIndex()
        if 0 <= idx < len(self.obs_sources):
            src = self.combo_obs_source.itemData(idx)
            if isinstance(src, ObsAudioSource):
                return src.name
        return None

    def _open_verifier_window(self) -> None:
        """Open or focus the independent AV Sync Verifier window."""
        out_idx = self.combo_out_device.currentData()
        cur_source = self._get_selected_obs_source_name()

        if self.verifier_window is None or not self.verifier_window.isVisible():
            dummy = os.environ.get("SYNCTONE_TEST_DUMMY_AUDIO", "0") == "1"
            self.verifier_window = SyncVerifierWindow(
                obs_client=self.obs_client,
                output_device_idx=out_idx,
                current_obs_source=cur_source,
                on_offset_changed_cb=self._on_verifier_offset_changed,
                dummy_mode=dummy,
                parent=self,
            )
            self.verifier_window.show()
        else:
            self.verifier_window.update_device_and_source(out_idx, cur_source)
            self.verifier_window.raise_()
            self.verifier_window.activateWindow()

    def _on_verifier_offset_changed(self, new_val: float) -> None:
        """Callback when offset is trimmed from the verifier window."""
        self.spin_offset.blockSignals(True)
        self.spin_offset.setValue(new_val)
        self.spin_offset.blockSignals(False)
        self.slider_offset.blockSignals(True)
        self.slider_offset.setValue(int(round(min(1000.0, new_val) * 10)))
        self.slider_offset.blockSignals(False)
        self.plot_widget.update_manual_offset(new_val)
        self._latest_obs_offset = int(round(new_val))
        self._update_obs_diff_display()

    def resizeEvent(self, event) -> None:
        """Handle window resizing smoothly in real-time."""
        super().resizeEvent(event)

    def closeEvent(self, event):
        if self.verifier_window is not None:
            try:
                self.verifier_window.close()
            except Exception:
                pass
        self._save_settings()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
