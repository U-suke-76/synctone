"""Main application window for SyncTone."""

import sys
import os
import atexit
from typing import List, Optional
import numpy as np

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit,
    QSpinBox, QDoubleSpinBox, QSlider, QProgressBar, QGroupBox, QMessageBox,
    QFrame, QStatusBar, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, QSettings, QTimer, qInstallMessageHandler, QtMsgType
from PySide6.QtGui import QFont

def _qt_message_handler(mode: QtMsgType, context, message: str) -> None:
    """Filter out benign internal Qt font size warnings."""
    if sys is None or sys.stderr is None:
        return
    if "setPointSize: Point size <= 0" in message:
        return
    if "QFont::setPixelSize" in message:
        return
    sys.stderr.write(f"{message}\n")

qInstallMessageHandler(_qt_message_handler)
atexit.register(lambda: qInstallMessageHandler(None))

from synctone.core.chirp import ChirpAnalyzer, MultiMeasureResult
from synctone.core.audio_io import AudioEngine, AudioDeviceInfo, InputLevelMonitor
from synctone.obs.client import MAX_RENDER_DELAY_MS, ObsClient, ObsAudioSource, ObsVideoSource
from synctone.gui.plot_widget import SyncPlotWidget
from synctone.gui.verifier_window import SyncVerifierWindow
from synctone.gui.workers import MeasurementWorker, TestToneWorker  # noqa: F401 (re-exported)
from synctone.gui.styles import (
    APPLY_MEASURED_BTN_QSS,
    APPLY_OBS_BTN_QSS,
    DARK_THEME_QSS,
    PANEL_FRAME_QSS,
    TRIM_DELTA_BTN_QSS,
    level_bar_style,
)
from synctone.i18n import t, LANGUAGES, I18nManager

# Keywords identifying sources that usually carry the backing track (desktop / output audio)
_RECOMMENDED_SOURCE_KEYWORDS_CI = ("desktop",)
_RECOMMENDED_SOURCE_KEYWORDS = ("オケ", "デスクトップ")


def _is_recommended_obs_source(src: ObsAudioSource) -> bool:
    """Return True if the OBS audio source looks like the desktop/backing-track output."""
    if "output" in src.kind.lower():
        return True
    if any(k in src.name.lower() for k in _RECOMMENDED_SOURCE_KEYWORDS_CI):
        return True
    return any(k in src.name for k in _RECOMMENDED_SOURCE_KEYWORDS)


def _format_obs_audio_label(src: ObsAudioSource) -> str:
    """Combo box label for an OBS audio source, e.g. 'Desktop [120 ms] (recommended)'."""
    label = f"{src.name} [{src.sync_offset_ms} ms]"
    if _is_recommended_obs_source(src):
        label += f" {t('obs_recommended_source')}"
    return label


def _format_obs_video_label(src: ObsVideoSource) -> str:
    """Combo box label for an OBS video source, e.g. 'Camera [80 ms]'."""
    return f"{src.name} [{src.render_delay_ms} ms]"


def _set_combo_item_label(combo: QComboBox, idx: int, label: str) -> None:
    """Update both the visible text and tooltip of a combo box item."""
    combo.setItemText(idx, label)
    combo.setItemData(idx, label, Qt.ItemDataRole.ToolTipRole)


class MainWindow(QMainWindow):
    """Main window of SyncTone application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SyncTone - OBS音声同期アシスタント")
        self.resize(1140, 950)
        self.setMinimumSize(980, 820)

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
        self._start_level_monitor()

    def _apply_dark_theme(self) -> None:
        """Apply a sleek, modern dark theme stylesheet."""
        self.setStyleSheet(DARK_THEME_QSS)

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 6, 12, 6)
        main_layout.setSpacing(6)

        # 0. Header bar: Language selector
        main_layout.addLayout(self._build_header_bar())

        # 1. Top Section: OBS Connection & Audio Device Configuration (Side-by-side)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        top_layout.addWidget(self._build_obs_box(), stretch=3)
        top_layout.addWidget(self._build_device_box(), stretch=5)
        main_layout.addLayout(top_layout, stretch=0)

        # 2. Middle Section: Plots (Waveform and Cross-Correlation) - Give maximum vertical expansion!
        main_layout.addWidget(self._build_plot_box(), stretch=10)

        # 3. Bottom Section: Measurement & OBS Application Panel
        main_layout.addWidget(self._build_bottom_box(), stretch=0)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initial translation
        self.retranslate_ui()
        self.status_bar.showMessage(t("status_ready"))

    def _build_header_bar(self) -> QHBoxLayout:
        """Header bar with the language selector."""
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
        return header_bar

    def _build_obs_box(self) -> QGroupBox:
        """1-A. OBS Connection Box."""
        self.obs_box = QGroupBox()
        self.obs_box.setMinimumWidth(310)
        obs_layout = QGridLayout(self.obs_box)
        obs_layout.setContentsMargins(10, 8, 10, 8)
        obs_layout.setSpacing(6)

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
        return self.obs_box

    def _build_device_box(self) -> QGroupBox:
        """1-B. Audio Hardware Device Selection & Volume Box (with live input level meter)."""
        self.device_box = QGroupBox()
        dev_layout = QGridLayout(self.device_box)
        dev_layout.setContentsMargins(10, 8, 10, 8)
        dev_layout.setSpacing(6)

        self.label_playback = QLabel()
        dev_layout.addWidget(self.label_playback, 0, 0)
        self.combo_out_device = QComboBox()
        self.combo_out_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_out_device.view().setMinimumWidth(460)
        self.combo_out_device.currentIndexChanged.connect(self._on_device_selection_changed)
        dev_layout.addWidget(self.combo_out_device, 0, 1)

        self.label_recording = QLabel()
        dev_layout.addWidget(self.label_recording, 1, 0)
        self.combo_in_device = QComboBox()
        self.combo_in_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_in_device.view().setMinimumWidth(460)
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

        self.refresh_devices_btn = QPushButton()
        self.refresh_devices_btn.clicked.connect(self._refresh_audio_devices)

        vol_layout.addWidget(self.vol_slider)
        vol_layout.addWidget(self.vol_label)
        vol_layout.addWidget(self.test_tone_btn)
        vol_layout.addWidget(self.refresh_devices_btn)
        dev_layout.addLayout(vol_layout, 2, 1)

        # Live microphone input level meter (pre-measurement check)
        self.level_icon = QLabel()
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(14)
        self.level_bar.setMinimumHeight(14)
        self.level_bar.setStyleSheet(self._level_bar_style("#00e676"))
        self.level_label = QLabel("-- dB")
        self.level_label.setFixedWidth(64)
        self.level_label.setStyleSheet("color: #aaaabb; font-size: 11px;")
        level_layout = QHBoxLayout()
        level_layout.addWidget(self.level_icon)
        level_layout.addWidget(self.level_bar, stretch=1)
        level_layout.addWidget(self.level_label)
        dev_layout.addLayout(level_layout, 3, 1)

        self.level_monitor = InputLevelMonitor()
        self._level_smoothed: float = 0.0
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(50)
        self._level_timer.timeout.connect(self._update_level_meter)
        return self.device_box

    def _build_plot_box(self) -> QGroupBox:
        """2. Waveform / cross-correlation plot area."""
        self.plot_box = QGroupBox()
        self.plot_box.setMinimumHeight(390)
        self.plot_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        plot_layout = QVBoxLayout(self.plot_box)
        plot_layout.setContentsMargins(8, 6, 8, 8)
        self.plot_widget = SyncPlotWidget(self)
        self.plot_widget.setMinimumHeight(360)
        self.plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        plot_layout.addWidget(self.plot_widget)
        return self.plot_box

    def _build_bottom_box(self) -> QGroupBox:
        """3. Measurement controls, results, manual adjustment and OBS apply panel."""
        self.bottom_box = QGroupBox()
        bottom_layout = QVBoxLayout(self.bottom_box)
        bottom_layout.setContentsMargins(10, 8, 10, 8)
        bottom_layout.setSpacing(8)

        bottom_layout.addLayout(self._build_measure_row())

        # Results and Adjustment Row
        result_row = QHBoxLayout()
        result_row.setSpacing(10)
        result_row.addWidget(self._build_result_frame(), stretch=3)
        result_row.addWidget(self._build_adjust_frame(), stretch=4)
        # OBS Target and Apply - Widest stretch to accommodate long source names
        result_row.addWidget(self._build_apply_frame(), stretch=5)
        bottom_layout.addLayout(result_row)
        return self.bottom_box

    def _build_measure_row(self) -> QHBoxLayout:
        """Measure button, mode selection, progress bar and verifier button."""
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
        return measure_row

    def _build_result_frame(self) -> QFrame:
        """Result badge (Median + Runs history + Jitter)."""
        res_frame = QFrame()
        res_frame.setStyleSheet(PANEL_FRAME_QSS)
        res_layout = QVBoxLayout(res_frame)
        res_layout.setContentsMargins(8, 6, 8, 6)
        res_layout.setSpacing(5)

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
        return res_frame

    def _build_adjust_frame(self) -> QFrame:
        """Manual Adjustment Controls - 2-tier button layout to eliminate horizontal crowding."""
        adj_frame = QFrame()
        adj_frame.setStyleSheet(PANEL_FRAME_QSS)
        adj_layout = QVBoxLayout(adj_frame)
        adj_layout.setContentsMargins(8, 6, 8, 6)
        adj_layout.setSpacing(5)

        # Row 1: Primary action button (Full width)
        self.btn_apply_measured = QPushButton()
        self.btn_apply_measured.setEnabled(False)
        self.btn_apply_measured.setStyleSheet(APPLY_MEASURED_BTN_QSS)
        self.btn_apply_measured.clicked.connect(self._apply_measured_to_adjustment)
        adj_layout.addWidget(self.btn_apply_measured)

        # Row 2: Secondary buttons side-by-side (OBS value & Raw 0ms)
        btn_sub_row = QHBoxLayout()
        btn_sub_row.setSpacing(6)

        self.btn_apply_obs = QPushButton()
        self.btn_apply_obs.setEnabled(False)
        self.btn_apply_obs.setStyleSheet(APPLY_OBS_BTN_QSS)
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
        self.spin_offset.setMinimumWidth(105)
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
            btn.setStyleSheet(TRIM_DELTA_BTN_QSS)
            btn.clicked.connect(lambda checked=False, d=delta: self._adjust_offset(d))
            trim_btn_row.addWidget(btn)

        adj_layout.addLayout(trim_btn_row)

        self.slider_offset = QSlider(Qt.Orientation.Horizontal)
        self.slider_offset.setRange(0, 10000)  # 0.0 to 1000.0 ms (0.1ms step)
        self.slider_offset.valueChanged.connect(self._on_slider_changed)
        adj_layout.addWidget(self.slider_offset)
        adj_layout.addStretch()
        return adj_frame

    def _build_apply_frame(self) -> QFrame:
        """OBS target source selection (audio + optional video) and apply button."""
        apply_frame = QFrame()
        apply_frame.setStyleSheet(PANEL_FRAME_QSS)
        apply_layout = QVBoxLayout(apply_frame)
        apply_layout.setContentsMargins(8, 6, 8, 6)
        apply_layout.setSpacing(5)

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
        # Ensure dropdown popup list is wide enough (420px) so long source names never truncate with '...'
        self.combo_obs_source.view().setMinimumWidth(420)
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

        # Video source synchronization was moved to the AV Sync Verifier window.
        # Keep hidden attributes only for backward compatibility with internal helpers.
        self.check_sync_video = QCheckBox()
        self.check_sync_video.setVisible(False)
        self.check_sync_video.setChecked(False)
        self.check_sync_video.toggled.connect(self._on_video_check_toggled)

        self.video_container = QWidget()
        self.video_container.setVisible(False)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 2)
        video_layout.setSpacing(4)

        self.combo_obs_video_source = QComboBox()
        self.combo_obs_video_source.addItem("OBS未接続 (映像ソース選択不可)")
        self.combo_obs_video_source.setEnabled(False)
        self.combo_obs_video_source.setMinimumHeight(26)
        self.combo_obs_video_source.currentIndexChanged.connect(self._on_obs_video_source_selected)
        self.combo_obs_video_source.view().setMinimumWidth(420)
        video_layout.addWidget(self.combo_obs_video_source)

        video_status_row = QHBoxLayout()
        self.current_video_delay_label = QLabel()
        self.current_video_delay_label.setStyleSheet("color: #8899aa; font-size: 10px;")
        video_status_row.addWidget(self.current_video_delay_label)
        video_status_row.addStretch()
        video_layout.addLayout(video_status_row)

        apply_layout.addStretch()

        self.apply_btn = QPushButton()
        self.apply_btn.setObjectName("apply_btn")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setMinimumHeight(32)
        self.apply_btn.clicked.connect(self._apply_offset_to_obs)
        apply_layout.addWidget(self.apply_btn)
        return apply_frame


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
        self.refresh_devices_btn.setText(t("audio_refresh"))
        self.refresh_devices_btn.setToolTip(t("audio_refresh_tooltip"))
        self.level_icon.setText(t("audio_level"))
        self.level_icon.setToolTip(t("audio_level_tooltip"))
        self.level_bar.setToolTip(t("audio_level_tooltip"))

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
        self._sync_apply_measured_button_text()

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
            src = self._selected_obs_audio_source()
            if src is not None:
                self.current_offset_label.setText(t("current_obs_val", offset=src.sync_offset_ms))
            else:
                self.current_offset_label.setText(t("current_obs_none"))

            v_src = self._selected_obs_video_source()
            if v_src is not None:
                self.current_video_delay_label.setText(t("current_video_delay_val", delay=v_src.render_delay_ms))
            else:
                self.current_video_delay_label.setText(t("current_video_delay_none"))

        self._update_obs_diff_display()
        self._refresh_measurement_result_labels()

    def _refresh_measurement_result_labels(self) -> None:
        """Render the delay, run history, and stability/level badge for the last measurement."""
        if self.last_multi_result:
            median_ms = max(0.0, self.last_multi_result.median_delay_ms)
            self.delay_label.setText(t("detected_delay", delay=median_ms))
            runs_strs = [f"{r.delay_ms:.1f}ms" for r in self.last_multi_result.individual_results]
            if len(runs_strs) > 1:
                self.runs_label.setText(t("runs_history", history=" / ".join(runs_strs)))
            else:
                self.runs_label.setText(t("single_run", run=runs_strs[0]))

            self._update_stability_and_level_badge(self.last_multi_result, self.last_recorded)
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

        # Keep video sync unchecked on MainWindow (managed inside SyncVerifierWindow)
        self.check_sync_video.setChecked(False)
        self.video_container.setVisible(False)

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

    @staticmethod
    def _level_bar_style(color: str) -> str:
        return level_bar_style(color)

    def _start_level_monitor(self) -> None:
        # Skip opening real hardware in dummy/test mode
        if os.environ.get("SYNCTONE_TEST_DUMMY_AUDIO", "0") == "1":
            self._level_timer.start()
            return
        try:
            self.level_monitor.start(self.combo_in_device.currentData())
            self._level_timer.start()
        except Exception as e:
            # Meter is a convenience feature: fail silently (no popup) and show the reason as a tooltip
            self._stop_level_monitor()
            self.level_label.setText("N/A")
            self.level_bar.setToolTip(t("audio_level_error", error=str(e)))

    def _stop_level_monitor(self) -> None:
        self._level_timer.stop()
        self.level_monitor.stop()
        self._level_smoothed = 0.0
        self.level_bar.setValue(0)
        self.level_label.setText("-- dB")
        self.level_bar.setStyleSheet(self._level_bar_style("#00e676"))

    def _update_level_meter(self) -> None:
        """Poll peak level and update the meter (dB scale -60..0, fast attack / slow release)."""
        peak = self.level_monitor.read_peak()
        if peak > self._level_smoothed:
            self._level_smoothed = peak
        else:
            self._level_smoothed *= 0.85
        level = self._level_smoothed
        db = 20.0 * np.log10(level) if level > 1e-6 else -120.0
        self.level_bar.setValue(int(round(max(0.0, min(1.0, (db + 60.0) / 60.0)) * 100)))
        if level >= 0.98:
            color, text = "#ff5252", t("audio_level_clip")
        elif level < 0.015:
            color, text = "#ffca28", None
        else:
            color, text = "#00e676", None
        self.level_bar.setStyleSheet(self._level_bar_style(color))
        if text:
            self.level_label.setText(text)
        else:
            self.level_label.setText(f"{db:.0f} dB" if db > -100.0 else "-- dB")

    def _on_device_selection_changed(self) -> None:
        self._save_settings()
        # Restart live level meter on the newly selected input device (not while measuring)
        if self.worker is None or not self.worker.isRunning():
            self._start_level_monitor()
        self._sync_verifier_targets()

    # --- Device Management ---
    @staticmethod
    def _get_hostapi_rank(hostapi: str) -> int:
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

    @staticmethod
    def _format_device_label(dev: AudioDeviceInfo, is_output: bool) -> str:
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

    def _populate_device_combo(
        self,
        combo: QComboBox,
        devices: List[AudioDeviceInfo],
        saved_name: str,
        is_output: bool,
    ) -> None:
        """Sort devices by host API preference, populate combo box, and select the best match."""
        devices.sort(
            key=lambda d: (
                self._get_hostapi_rank(d.hostapi_name),
                not (d.is_default_output if is_output else d.is_default_input),
                d.name,
            )
        )
        match_idx = -1
        first_wasapi = -1
        for idx, dev in enumerate(devices):
            label = self._format_device_label(dev, is_output=is_output)
            combo.addItem(label, dev.index)
            is_def = dev.is_default_output if is_output else dev.is_default_input
            if "wasapi" in dev.hostapi_name.lower() and (first_wasapi == -1 or is_def):
                first_wasapi = idx
            if saved_name and (saved_name == label or saved_name in label):
                match_idx = idx

        if combo.count() > 0:
            chosen = match_idx if match_idx >= 0 else (first_wasapi if first_wasapi >= 0 else 0)
            combo.setCurrentIndex(chosen)

    def _refresh_audio_devices(self) -> None:
        self.combo_out_device.blockSignals(True)
        self.combo_in_device.blockSignals(True)
        self.combo_out_device.clear()
        self.combo_in_device.clear()

        try:
            out_devs, in_devs = self.audio_engine.get_devices()
            saved_out = str(self.settings.value("audio/output_device_name", "") or "")
            saved_in = str(self.settings.value("audio/input_device_name", "") or "")

            self._populate_device_combo(self.combo_out_device, out_devs, saved_out, is_output=True)
            self._populate_device_combo(self.combo_in_device, in_devs, saved_in, is_output=False)

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
        self._sync_verifier_targets()

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
                    label = _format_obs_audio_label(src)
                    if _is_recommended_obs_source(src):
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
                        v_label = _format_obs_video_label(v_src)
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
        self._sync_verifier_targets()

    def _fetch_current_obs_offset(self) -> None:
        """Fetch real-time sync offset from OBS for the currently selected audio source and apply to preview."""
        if not self.obs_client.is_connected:
            return
        src = self._selected_obs_audio_source()
        if src is None:
            return

        try:
            latest_offset = self.obs_client.get_sync_offset(src.name)
            src.sync_offset_ms = latest_offset
            self._latest_obs_offset = latest_offset

            # Update combo text
            self._refresh_selected_audio_label(src)
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
        src = self._selected_obs_audio_source()
        if src is None:
            self.diff_offset_label.setText("")
            return

        current_ms = float(src.sync_offset_ms)
        spin_ms = round(float(self.spin_offset.value()), 1)
        # If the spinbox is still at 0.0ms before the user applies a measurement, compare against the
        # measured delay so we never show a misleading "-126.0 ms" diff against raw 0.0ms.
        target_ms = (
            self._last_measured_delay_ms
            if (spin_ms == 0.0 and self._last_measured_delay_ms > 0.0 and not self._has_applied_measured)
            else spin_ms
        )
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
            self._sync_verifier_targets()

    # --- Measurement Flow ---
    def _start_measurement(self) -> None:
        out_idx = self.combo_out_device.currentData()
        in_idx = self.combo_in_device.currentData()
        total_runs = int(self.combo_measure_mode.currentData() or 3)

        # Release the mic stream so the measurement stream can use it exclusively;
        # the live meter keeps running, fed by the measurement stream itself.
        self.level_monitor.stop()
        self._level_smoothed = 0.0
        self._level_timer.start()

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
        self.worker.level_peak.connect(self.level_monitor.feed)
        self.worker.start()

    def _end_measurement_level_meter(self) -> None:
        """Resume always-on mic level monitoring after a measurement."""
        self._start_level_monitor()

    def _on_step_progress(self, current: int, total: int) -> None:
        self.measure_btn.setText(t("btn_measuring", current=current, total=total))
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(t("status_sampling", current=current, total=total))

    def _on_measurement_finished(self, multi: MultiMeasureResult, best_recorded: np.ndarray) -> None:
        self._end_measurement_level_meter()
        self.measure_btn.setEnabled(True)
        self.measure_btn.setText(t("btn_start_measure"))
        self.progress_bar.setValue(self.progress_bar.maximum())

        self.last_multi_result = multi
        self.last_recorded = best_recorded

        self._refresh_measurement_result_labels()

        # Set manual adjustment controls with 0.1ms precision (preserve user's current manual offset!)
        median_ms = max(0.0, multi.median_delay_ms)
        precise_ms = round(median_ms, 1)
        self._last_measured_delay_ms = precise_ms
        self.btn_apply_measured.setEnabled(True)

        current_offset_ms = round(float(self.spin_offset.value()), 1)
        self._sync_apply_measured_button_text(current_offset_ms)

        self.plot_widget.set_data(
            ref_signal=self.analyzer.reference_signal,
            rec_signal=best_recorded,
            sample_rate=self.analyzer.sample_rate,
            result=multi.best_result,
            initial_offset_ms=current_offset_ms,
        )
        self.status_bar.showMessage(t("status_measured_guide", delay=precise_ms))
        self._update_obs_diff_display()


    def _on_measurement_error(self, error_msg: str) -> None:
        self._end_measurement_level_meter()
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
        src = self._selected_obs_audio_source()
        src_name = src.name if src is not None else ""
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

    def _sync_apply_measured_button_text(self, value: Optional[float] = None) -> None:
        """Show 'applied' on the measured-delay button when the manual offset matches it."""
        if self._last_measured_delay_ms <= 0.0:
            self.btn_apply_measured.setText(t("btn_apply_measured_unmeasured"))
            return
        cur_val = self.spin_offset.value() if value is None else value
        key = "btn_applied_measured" if abs(cur_val - self._last_measured_delay_ms) < 0.05 else "btn_apply_measured"
        self.btn_apply_measured.setText(t(key, delay=self._last_measured_delay_ms))

    def _on_spinbox_changed(self, value: float) -> None:
        self.slider_offset.blockSignals(True)
        slider_val = int(round(min(1000.0, value) * 10))
        self.slider_offset.setValue(slider_val)
        self.slider_offset.blockSignals(False)
        self.plot_widget.update_manual_offset(float(value))
        self._sync_apply_measured_button_text(value)
        self._update_obs_diff_display()

    def _on_slider_changed(self, value: int) -> None:
        float_val = value / 10.0
        self.spin_offset.blockSignals(True)
        self.spin_offset.setValue(float_val)
        self.spin_offset.blockSignals(False)
        self.plot_widget.update_manual_offset(float_val)
        self._sync_apply_measured_button_text(float_val)
        self._update_obs_diff_display()

    # --- Apply to OBS ---
    def _apply_offset_to_obs(self) -> None:
        """Apply the manual offset to the selected OBS audio (and optionally video) source."""
        if not self.obs_client.is_connected:
            QMessageBox.warning(self, t("dialog_obs_unconnected_title"), t("dialog_obs_unconnected_msg"))
            return

        src = self._selected_obs_audio_source()
        if src is None:
            return

        target_offset_ms = round(self.spin_offset.value(), 1)
        # Round to integer for OBS Studio compatibility
        target_int_ms = int(round(target_offset_ms))
        video_src = self._selected_obs_video_source() if self.check_sync_video.isChecked() else None

        if not self._confirm_apply_to_obs(src, video_src, target_int_ms):
            return

        try:
            actual_audio_ms = self._apply_audio_offset(src, target_int_ms)
            if video_src:
                actual_vid_ms = self._apply_video_delay(video_src, target_int_ms)
                self._notify_applied_with_video(src.name, actual_audio_ms, video_src.name, actual_vid_ms)
            else:
                QMessageBox.information(
                    self,
                    t("dialog_applied_title"),
                    t("dialog_applied_msg", name=src.name, target=actual_audio_ms)
                )
                self.status_bar.showMessage(t("status_applied_obs", name=src.name, offset=actual_audio_ms))
        except Exception as e:
            QMessageBox.critical(self, t("dialog_apply_error_title"), t("dialog_apply_error_msg", error=str(e)))

    def _confirm_apply_to_obs(
        self, src: ObsAudioSource, video_src: Optional[ObsVideoSource], target_int_ms: int
    ) -> bool:
        """Ask the user to confirm applying offsets to OBS. Returns True if confirmed."""
        if video_src:
            video_target_ms = min(MAX_RENDER_DELAY_MS, target_int_ms)
            limit_note = f"\n{t('warn_render_delay_limit')}" if target_int_ms > MAX_RENDER_DELAY_MS else ""
            confirm_msg = t(
                "dialog_confirm_apply_with_video_msg",
                audio_name=src.name,
                audio_target=target_int_ms,
                video_name=video_src.name,
                video_target=video_target_ms,
                limit_note=limit_note,
            )
        else:
            diff = target_int_ms - src.sync_offset_ms
            diff_str = f"+{diff} ms" if diff > 0 else f"{diff} ms"
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
        return confirm == QMessageBox.StandardButton.Yes

    def _apply_audio_offset(self, src: ObsAudioSource, target_int_ms: int) -> int:
        """Set the audio sync offset on OBS and refresh related UI. Returns the actual value."""
        actual_audio_ms = self.obs_client.set_sync_offset(src.name, target_int_ms)
        src.sync_offset_ms = actual_audio_ms
        self._has_applied_measured = True
        self.current_offset_label.setText(t("current_obs_val", offset=actual_audio_ms))
        self._refresh_selected_audio_label(src)
        self._update_obs_diff_display()
        return actual_audio_ms

    def _notify_applied_with_video(
        self, audio_name: str, audio_ms: int, video_name: str, video_ms: int
    ) -> None:
        """Show the success dialog / status message after applying audio + video offsets."""
        QMessageBox.information(
            self,
            t("dialog_applied_title"),
            t(
                "dialog_applied_with_video_msg",
                audio_name=audio_name,
                audio_target=audio_ms,
                video_name=video_name,
                video_target=video_ms,
            ),
        )
        self.status_bar.showMessage(
            t(
                "status_applied_obs_with_video",
                audio_name=audio_name,
                audio_offset=audio_ms,
                video_name=video_name,
                video_offset=video_ms,
            )
        )

    def _selected_obs_audio_source(self) -> Optional[ObsAudioSource]:
        """Return the OBS audio source currently selected in the combo box (or None)."""
        idx = self.combo_obs_source.currentIndex()
        if idx < 0 or not self.obs_sources:
            return None
        src = self.combo_obs_source.itemData(idx)
        return src if isinstance(src, ObsAudioSource) else None

    def _selected_obs_video_source(self) -> Optional[ObsVideoSource]:
        """Return the OBS video source currently selected in the combo box (or None)."""
        v_idx = self.combo_obs_video_source.currentIndex()
        if not (0 <= v_idx < len(self.obs_video_sources)):
            return None
        v_src = self.combo_obs_video_source.itemData(v_idx)
        return v_src if isinstance(v_src, ObsVideoSource) else None

    def _refresh_selected_audio_label(self, src: ObsAudioSource) -> None:
        """Re-render the combo label of the selected audio source after its offset changed."""
        _set_combo_item_label(self.combo_obs_source, self.combo_obs_source.currentIndex(), _format_obs_audio_label(src))

    def _apply_video_delay(self, v_src: ObsVideoSource, target_ms: int) -> int:
        """Set render delay on OBS for the selected video source and refresh related UI."""
        actual_vid_ms = self.obs_client.set_render_delay(v_src.name, target_ms)
        v_src.render_delay_ms = actual_vid_ms
        self._latest_obs_video_delay = actual_vid_ms
        _set_combo_item_label(
            self.combo_obs_video_source,
            self.combo_obs_video_source.currentIndex(),
            _format_obs_video_label(v_src),
        )
        self.current_video_delay_label.setText(t("current_video_delay_val", delay=actual_vid_ms))
        return actual_vid_ms

    def _get_selected_obs_source_name(self) -> Optional[str]:
        """Helper to get currently selected OBS audio source name if connected."""
        if not self.obs_client.is_connected:
            return None
        src = self._selected_obs_audio_source()
        return src.name if src is not None else None

    def _get_selected_obs_video_source_name(self) -> Optional[str]:
        """Helper to get currently selected OBS video source name if connected and video sync is enabled."""
        if not self.obs_client.is_connected or not self.check_sync_video.isChecked():
            return None
        v_src = self._selected_obs_video_source()
        return v_src.name if v_src is not None else None

    def _sync_verifier_targets(self) -> None:
        """Keep the open verifier window's device, audio source, and video source in sync."""
        if self.verifier_window is not None and self.verifier_window.isVisible():
            self.verifier_window.update_device_and_source(
                self.combo_out_device.currentData(),
                self._get_selected_obs_source_name(),
                self._get_selected_obs_video_source_name(),
            )

    def _open_verifier_window(self) -> None:
        """Open or focus the independent AV Sync Verifier window."""
        out_idx = self.combo_out_device.currentData()
        cur_source = self._get_selected_obs_source_name()
        cur_video_source = self._get_selected_obs_video_source_name()

        if self.verifier_window is None or not self.verifier_window.isVisible():
            dummy = os.environ.get("SYNCTONE_TEST_DUMMY_AUDIO", "0") == "1"
            self.verifier_window = SyncVerifierWindow(
                obs_client=self.obs_client,
                output_device_idx=out_idx,
                current_obs_source=cur_source,
                current_obs_video_source=cur_video_source,
                on_offset_changed_cb=self._on_verifier_offset_changed,
                on_video_delay_changed_cb=self._on_verifier_video_delay_changed,
                dummy_mode=dummy,
                parent=self,
            )
            self.verifier_window.show()
        else:
            self.verifier_window.update_device_and_source(out_idx, cur_source, cur_video_source)
            self.verifier_window.raise_()
            self.verifier_window.activateWindow()

    def _update_stability_and_level_badge(
        self,
        multi: MultiMeasureResult,
        recorded: Optional[np.ndarray] = None,
    ) -> None:
        """Update jitter/stability badge and append audio level diagnostics (clipping/low volume)."""
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
        else:
            conf_pct = int(multi.overall_confidence * 100)
            stab_txt = t("badge_confidence", conf=conf_pct)
            stab_color = "#00e676" if conf_pct >= 60 else "#ffca28"

        # Check recorded signal peak level for clipping (>0.98) or near-silence (<0.015)
        if recorded is not None and len(recorded) > 0:
            peak_amp = float(np.max(np.abs(recorded)))
            if peak_amp >= 0.98:
                stab_txt = f"{stab_txt}\n{t('warn_clipping')}"
                stab_color = "#ffca28"
            elif 0.0 < peak_amp < 0.015:
                stab_txt = f"{stab_txt}\n{t('warn_low_volume')}"
                stab_color = "#ff5252"

        self.jitter_badge.setText(stab_txt)
        self.jitter_badge.setStyleSheet(f"color: {stab_color}; font-weight: bold; font-size: 11px;")

    def _on_verifier_offset_changed(self, new_val: float) -> None:
        """Callback when offset is trimmed from the verifier window."""
        self.spin_offset.blockSignals(True)
        self.spin_offset.setValue(new_val)
        self.spin_offset.blockSignals(False)
        self.slider_offset.blockSignals(True)
        self.slider_offset.setValue(int(round(min(1000.0, new_val) * 10)))
        self.slider_offset.blockSignals(False)
        self.plot_widget.update_manual_offset(new_val)
        target_int = int(round(new_val))
        self._latest_obs_offset = target_int

        # Update audio source combo & label in MainWindow
        idx = self.combo_obs_source.currentIndex()
        if 0 <= idx < len(self.obs_sources):
            src = self.obs_sources[idx]
            src.sync_offset_ms = target_int
            self.current_offset_label.setText(t("current_obs_val", offset=target_int))
            _set_combo_item_label(self.combo_obs_source, idx, _format_obs_audio_label(src))

        # Also synchronize linked video source render delay if enabled
        if self.obs_client.is_connected and self.check_sync_video.isChecked():
            v_src = self._selected_obs_video_source()
            if v_src is not None:
                try:
                    self._apply_video_delay(v_src, target_int)
                except Exception:
                    pass

        self._update_obs_diff_display()

    def _on_verifier_video_delay_changed(self, actual_vid_ms: int) -> None:
        """Callback when video render delay is adjusted from the verifier window (audio offset stays untouched)."""
        v_src = self._selected_obs_video_source()
        if v_src is not None:
            v_src.render_delay_ms = actual_vid_ms
            _set_combo_item_label(
                self.combo_obs_video_source,
                self.combo_obs_video_source.currentIndex(),
                _format_obs_video_label(v_src),
            )
        self._latest_obs_video_delay = actual_vid_ms
        self.current_video_delay_label.setText(t("current_video_delay_val", delay=actual_vid_ms))


    def closeEvent(self, event):
        self._level_timer.stop()
        self.level_monitor.stop()
        if self.test_worker is not None and self.test_worker.isRunning():
            self.test_worker.wait(1000)
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(1000)
        if self.verifier_window is not None:
            try:
                self.verifier_window.close()
                self.verifier_window.deleteLater()
                self.verifier_window = None
            except Exception:
                pass
        self._save_settings()
        super().closeEvent(event)


def main():
    from PySide6.QtCore import QDir, QLockFile

    app = QApplication(sys.argv)
    lock_file = QLockFile(os.path.join(QDir.tempPath(), "SyncTone.lock"))
    lock_file.setStaleLockTime(0)
    if not lock_file.tryLock(100):
        QMessageBox.information(
            None,
            "SyncTone",
            "SyncTone はすでに起動しています。\n(SyncTone is already running.)",
        )
        sys.exit(0)

    window = MainWindow()
    window.show()
    exit_code = app.exec()
    lock_file.unlock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
