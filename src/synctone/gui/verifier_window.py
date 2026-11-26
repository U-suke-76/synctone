"""Real-time AV Sync and Auditory Verification Window (AV Sync Checker)."""

import ctypes
import math
import os
import sys
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QComboBox, QFrame, QSizePolicy, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, QSettings
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QKeyEvent, QImage

from synctone.core.av_analysis import AvOffsetResult
from synctone.core.verifier_audio import SyncAudioPlayer
from synctone.gui.game_capture import GameCaptureTargetWindow, _D3D11Presenter  # noqa: F401
from synctone.gui.styles import VERIFIER_DIALOG_QSS
from synctone.gui.workers import RecordingAnalysisWorker
from synctone.obs.client import (
    MAX_RENDER_DELAY_MS,
    MEASUREMENT_GAME_SOURCE_NAME,
    MEASUREMENT_WINDOW_SOURCE_NAME,
    ObsClient,
)
from synctone.i18n import t

# Analysis workers still running after their window was closed (kept alive until they finish)
_orphan_workers: list = []


class SyncCanvas(QWidget):
    """60 FPS Animated Visual & AV Sync Canvas for OBS Window/Game Capture."""

    def __init__(self, player: SyncAudioPlayer, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.player = player
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 60 FPS animation timer (~16.6ms)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

        # Flash decay tracker (confined to center line & badge so it never disturbs recording analysis)
        self._flash_intensity: float = 0.0

    def stop_timer(self) -> None:
        """Stop the 60fps animation timer."""
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event) -> None:
        self.render_scene(self, self.width(), self.height())

    def render_scene(self, paint_device, w: int, h: int) -> None:
        """Render the current animation frame onto any QPaintDevice (QWidget or QOpenGLWindow)."""
        painter = QPainter(paint_device)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Background
            painter.fillRect(0, 0, w, h, QColor("#101016"))

            # Obtain current player phase (-0.5 to +0.5; 0.0 at center hit / beep)
            phase = self.player.get_phase() if self.player.is_running else -0.5
            is_running = self.player.is_running

            # Trigger flash intensity when phase approaches center (hit point)
            if is_running and abs(phase) < 0.035:
                self._flash_intensity = 1.0
            else:
                self._flash_intensity = max(0.0, self._flash_intensity - 0.08)

            self._draw_av_sync_mode(painter, w, h, phase, is_running)
        finally:
            painter.end()

    def _draw_av_sync_mode(self, painter: QPainter, w: int, h: int, phase: float, is_running: bool) -> None:
        """Render the horizontal sweeper timeline with milliseconds scale and clean center hit indicator."""
        center_x = w / 2.0
        track_y = h * 0.55
        track_h = 36.0

        # Timeline track background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#181824")))
        painter.drawRoundedRect(20, int(track_y - track_h / 2), w - 40, int(track_h), 6, 6)

        # Millisecond scale markings
        # Total time span represented across width = 1 cycle duration (60 / BPM)
        cycle_ms = (60.0 / self.player.bpm) * 1000.0
        half_span_ms = cycle_ms / 2.0

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QPen(QColor("#555570"), 1))

        # Draw ticks every 50ms or 100ms depending on tempo
        step_ms = 50.0 if cycle_ms <= 800.0 else 100.0
        cur_ms = -math.floor(half_span_ms / step_ms) * step_ms

        while cur_ms <= half_span_ms:
            rel = cur_ms / cycle_ms  # -0.5 to 0.5
            x = center_x + rel * (w - 60)
            if 30 <= x <= w - 30:
                is_major = (abs(cur_ms) < 1e-4) or (abs(cur_ms) % (step_ms * 2) < 1e-4)
                tick_h = 14 if is_major else 8
                painter.drawLine(int(x), int(track_y - tick_h / 2), int(x), int(track_y + tick_h / 2))

                if is_major and abs(cur_ms) > 1e-4:
                    label = f"{int(cur_ms):+d}ms"
                    painter.drawText(int(x - 30), int(track_y + 24), 60, 16, Qt.AlignmentFlag.AlignCenter, label)
            cur_ms += step_ms

        # Center Hit Target Line (0 ms)
        hit_pen = QPen(QColor(255, 255, 255, 220), 2)
        if self._flash_intensity > 0.0:
            glow_pen = QPen(QColor(0, 229, 255, int(180 * self._flash_intensity)), 6)
            painter.setPen(glow_pen)
            painter.drawLine(int(center_x), 15, int(center_x), h - 15)

        painter.setPen(hit_pen)
        painter.drawLine(int(center_x), 15, int(center_x), h - 15)

        # Center target badge (HIT 0ms)
        badge_y = track_y - track_h / 2 - 28
        badge_w = 76
        badge_h = 22
        badge_rect_x = center_x - badge_w / 2

        badge_color = QColor(0, 229, 255) if self._flash_intensity > 0.2 else QColor("#222234")
        text_color = QColor("#000000") if self._flash_intensity > 0.2 else QColor("#82aaff")

        painter.setPen(QPen(QColor("#00e5ff"), 1))
        painter.setBrush(QBrush(badge_color))
        painter.drawRoundedRect(int(badge_rect_x), int(badge_y), badge_w, badge_h, 4, 4)

        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(text_color)
        painter.drawText(int(badge_rect_x), int(badge_y), badge_w, badge_h, Qt.AlignmentFlag.AlignCenter, "HIT 0ms")

        # Moving Sweeper Bar (high-contrast bright core so both human eyes and recording analysis track it cleanly)
        # phase goes from -0.5 (left) to 0.0 (center) to +0.5 (right)
        bar_x = center_x + phase * (w - 60)
        bar_x = max(20.0, min(float(w - 20), bar_x))

        if is_running:
            # Outer glow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 64, 129, 75)))
            painter.drawRoundedRect(int(bar_x - 7), int(track_y - 26), 14, 52, 6, 6)

            # Pink body
            painter.setBrush(QBrush(QColor("#ff4081")))
            painter.drawRoundedRect(QRectF(bar_x - 3.5, track_y - 22, 7.0, 44.0), 3, 3)

            # Bright white center core for crisp visual & optical tracking
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawRect(QRectF(bar_x - 1.5, track_y - 20, 3.0, 40.0))

            # Top pointer triangle
            pointer_y = track_y - 26
            painter.setBrush(QBrush(QColor("#ff4081")))
            points = [
                (int(bar_x), int(pointer_y)),
                (int(bar_x - 5), int(pointer_y - 8)),
                (int(bar_x + 5), int(pointer_y - 8)),
            ]
            painter.drawPolygon([QPoint(px, py) for px, py in points])
        else:
            # Idle cue text (drawn below track so it doesn't overlap HIT 0ms badge)
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.setPen(QColor("#8888aa"))
            painter.drawText(0, int(track_y + 42), w, 24, Qt.AlignmentFlag.AlignCenter, t("verifier_play"))


class SyncVerifierWindow(QDialog):
    """Independent verification window for real-time auditory & visual sync testing."""

    # Tempo used during automatic recording measurement (non-commensurate with 30/60 fps)
    ANALYSIS_BPM = 110
    AUTO_RECORD_SECONDS = 8
    AUTO_VIDEO_POLL_INTERVAL_MS = 250
    AUTO_VIDEO_MAX_POLLS = 24       # up to 6.0 s waiting for OBS capture hook
    AUTO_VIDEO_REFRESH_AT_POLL = 10 # nudge OBS source visibility at 2.5 s if still black

    # Thresholds for 3-tier AV offset verdict (based on 60 fps = 16.7 ms/frame)
    OFFSET_OK_MS = 17.0     # <= 17 ms (~1 frame): practically in sync
    OFFSET_MINOR_MS = 33.0  # <= 33 ms (~2 frames): minor offset

    CONSENT_SETTINGS_KEY = "verifier/auto_scene_consent"

    def __init__(
        self,
        obs_client: ObsClient,
        output_device_idx: Optional[int] = None,
        current_obs_source: Optional[str] = None,
        current_obs_video_source: Optional[str] = None,
        on_offset_changed_cb: Optional[Callable[[float], None]] = None,
        on_video_delay_changed_cb: Optional[Callable[[int], None]] = None,
        dummy_mode: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.obs_client = obs_client
        self.output_device_idx = output_device_idx
        self.current_obs_source = current_obs_source
        self.current_obs_video_source = current_obs_video_source
        self.on_offset_changed_cb = on_offset_changed_cb
        self.on_video_delay_changed_cb = on_video_delay_changed_cb
        self.dummy_mode = dummy_mode
        self._analysis_worker: Optional[RecordingAnalysisWorker] = None
        self.last_analysis_result: Optional[AvOffsetResult] = None
        self._pending_apply_delta: Optional[int] = None
        self._pending_apply_is_video: bool = False
        self.game_capture_window: Optional[GameCaptureTargetWindow] = None

        # Auto-recording state
        self._auto_recording: bool = False
        self._obs_recording_started: bool = False
        self._auto_record_remaining: int = 0
        self._pre_auto_was_running: bool = False
        self._pre_auto_bpm: int = 120
        self._pre_auto_scene: Optional[str] = None
        self._auto_opened_game_capture: bool = False
        self._auto_capture_source: str = ""
        self._video_poll_count: int = 0
        self._auto_record_timer = QTimer(self)
        self._auto_record_timer.setInterval(1000)
        self._auto_record_timer.timeout.connect(self._on_auto_record_tick)
        self._wait_for_video_timer = QTimer(self)
        self._wait_for_video_timer.setInterval(self.AUTO_VIDEO_POLL_INTERVAL_MS)
        self._wait_for_video_timer.timeout.connect(self._on_wait_for_video_tick)

        self.player = SyncAudioPlayer(
            sample_rate=48000,
            bpm=120.0,
            amplitude=0.5,
            output_device_idx=self.output_device_idx,
            dummy_mode=self.dummy_mode,
        )

        self.resize(860, 560)
        self.setMinimumSize(780, 480)
        self._apply_dark_theme()
        self._init_ui()
        self.retranslate_ui()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(VERIFIER_DIALOG_QSS)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. OBS Capture Instruction Banner
        self.hint_banner = QFrame()
        self.hint_banner.setObjectName("obs_hint_banner")
        banner_layout = QHBoxLayout(self.hint_banner)
        banner_layout.setContentsMargins(8, 6, 8, 6)
        self.label_hint = QLabel()
        self.label_hint.setStyleSheet("color: #82b1ff; font-weight: bold; font-size: 11px;")
        self.label_hint.setWordWrap(True)
        banner_layout.addWidget(self.label_hint, stretch=1)

        self.btn_game_capture = QPushButton()
        self.btn_game_capture.setObjectName("game_capture_btn")
        self.btn_game_capture.clicked.connect(self._open_game_capture_window)
        banner_layout.addWidget(self.btn_game_capture)

        self.btn_revoke_consent = QPushButton()
        self.btn_revoke_consent.setObjectName("revoke_consent_btn")
        self.btn_revoke_consent.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #3d3d56; color: #aaaacc; "
            "font-size: 11px; padding: 4px 8px; border-radius: 4px; }"
            "QPushButton:hover { color: #ffffff; border-color: #82aaff; }"
        )
        self.btn_revoke_consent.clicked.connect(self._on_revoke_consent_clicked)
        banner_layout.addWidget(self.btn_revoke_consent)
        main_layout.addWidget(self.hint_banner)

        # 2. Visual Animation Canvas (unified visual + analysis canvas)
        self.canvas = SyncCanvas(self.player, self)
        main_layout.addWidget(self.canvas, stretch=1)

        # 3. Control Panel
        self.ctrl_panel = QFrame()
        self.ctrl_panel.setObjectName("ctrl_panel")
        ctrl_layout = QVBoxLayout(self.ctrl_panel)
        ctrl_layout.setContentsMargins(10, 8, 10, 8)
        ctrl_layout.setSpacing(8)

        # Row 1: Play/Stop + Tempo + Volume + Auto Measure + File Analyze
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        self.btn_play = QPushButton()
        self.btn_play.setObjectName("play_btn")
        self.btn_play.setMinimumWidth(140)
        self.btn_play.clicked.connect(self._toggle_playback)
        row1.addWidget(self.btn_play)

        self.label_tempo = QLabel()
        row1.addWidget(self.label_tempo)

        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(40, 240)
        self.spin_bpm.setValue(120)
        self.spin_bpm.setSuffix(" BPM")
        self.spin_bpm.setFixedWidth(118)
        self.spin_bpm.valueChanged.connect(self._on_bpm_changed)
        row1.addWidget(self.spin_bpm)

        self.label_volume = QLabel()
        row1.addWidget(self.label_volume)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(10, 100)
        self.slider_volume.setValue(50)
        self.slider_volume.setFixedWidth(90)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        row1.addWidget(self.slider_volume)

        row1.addStretch()

        self.btn_auto_measure = QPushButton()
        self.btn_auto_measure.setObjectName("auto_measure_btn")
        self.btn_auto_measure.clicked.connect(self._on_auto_measure_clicked)
        row1.addWidget(self.btn_auto_measure)

        self.btn_analyze = QPushButton()
        self.btn_analyze.setObjectName("analyze_btn")
        self.btn_analyze.clicked.connect(self._choose_and_analyze_recording)
        row1.addWidget(self.btn_analyze)
        ctrl_layout.addLayout(row1)

        # Row 2: Persistent In-Window Analysis Result Card
        self.result_frame = QFrame()
        self.result_frame.setObjectName("result_frame")
        res_layout = QHBoxLayout(self.result_frame)
        res_layout.setContentsMargins(8, 6, 8, 6)
        res_layout.setSpacing(10)

        res_text_layout = QVBoxLayout()
        res_text_layout.setContentsMargins(0, 0, 0, 0)
        res_text_layout.setSpacing(2)

        self.label_result_main = QLabel()
        self.label_result_main.setStyleSheet("color: #d8d8ee; font-weight: bold; font-size: 12px;")
        self.label_result_main.setWordWrap(True)
        res_text_layout.addWidget(self.label_result_main)

        self.label_result_sub = QLabel()
        self.label_result_sub.setStyleSheet("color: #9999bb; font-size: 11px;")
        self.label_result_sub.setWordWrap(True)
        res_text_layout.addWidget(self.label_result_sub)

        res_layout.addLayout(res_text_layout, stretch=1)

        self.btn_apply_result = QPushButton()
        self.btn_apply_result.setObjectName("apply_result_btn")
        self.btn_apply_result.setVisible(False)
        self.btn_apply_result.clicked.connect(self._apply_analysis_result)
        res_layout.addWidget(self.btn_apply_result)

        ctrl_layout.addWidget(self.result_frame)

        # Row 3: OBS Direct Trim Shortcut Bar
        self.obs_trim_frame = QFrame()
        self.obs_trim_frame.setObjectName("obs_trim_frame")
        obs_trim_layout = QHBoxLayout(self.obs_trim_frame)
        obs_trim_layout.setContentsMargins(0, 4, 0, 0)
        obs_trim_layout.setSpacing(5)

        self.label_obs_trim_title = QLabel()
        self.label_obs_trim_title.setStyleSheet("font-weight: bold; color: #82aaff; font-size: 11px;")
        obs_trim_layout.addWidget(self.label_obs_trim_title)

        self.combo_video_source = QComboBox()
        self.combo_video_source.setMinimumWidth(160)
        self.combo_video_source.setMaximumWidth(230)
        self.combo_video_source.currentIndexChanged.connect(self._on_video_source_selected)
        obs_trim_layout.addWidget(self.combo_video_source)

        self.label_obs_info = QLabel()
        self.label_obs_info.setStyleSheet("color: #bbbbcc; font-size: 11px;")
        obs_trim_layout.addWidget(self.label_obs_info)

        obs_trim_layout.addStretch()

        # Negative trim buttons: -20ms, -5ms, -1ms
        for delta in [-20, -5, -1]:
            btn = QPushButton(f"{delta}ms")
            btn.setObjectName("trim_btn")
            btn.setMinimumWidth(52)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_obs_offset(d))
            obs_trim_layout.addWidget(btn)

        # Direct numeric input spinbox for OBS delay
        self.spin_obs_delay = QSpinBox()
        self.spin_obs_delay.setObjectName("obs_delay_spin")
        self.spin_obs_delay.setRange(0, 5000)
        self.spin_obs_delay.setSuffix(" ms")
        self.spin_obs_delay.setFixedWidth(104)
        self.spin_obs_delay.editingFinished.connect(self._on_obs_delay_spin_finished)
        obs_trim_layout.addWidget(self.spin_obs_delay)

        # Positive trim buttons: +1ms, +5ms, +20ms
        for delta in [1, 5, 20]:
            btn = QPushButton(f"+{delta}ms")
            btn.setObjectName("trim_btn")
            btn.setMinimumWidth(52)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_obs_offset(d))
            obs_trim_layout.addWidget(btn)

        ctrl_layout.addWidget(self.obs_trim_frame)
        main_layout.addWidget(self.ctrl_panel)

    def retranslate_ui(self) -> None:
        """Update strings to current locale."""
        self.setWindowTitle(t("verifier_title"))
        self.label_hint.setText(t("verifier_obs_hint"))
        self.btn_game_capture.setText(t("verifier_game_capture_btn"))
        self.btn_revoke_consent.setText(t("verifier_revoke_consent_btn"))
        self._update_consent_button()
        if self.game_capture_window is not None:
            self.game_capture_window.setTitle(t("verifier_game_capture_title"))
        self.label_tempo.setText(t("verifier_tempo"))
        self.label_volume.setText(t("verifier_volume"))
        self.label_obs_trim_title.setText(
            t("verifier_obs_video_trim") if self.current_obs_video_source else t("verifier_obs_trim")
        )
        self._update_measure_buttons()
        self._update_play_button_text()
        self._refresh_obs_info()
        if self.last_analysis_result is None and not self._auto_recording and self._analysis_worker is None:
            self.label_result_main.setText(t("verifier_result_idle_title"))
            self.label_result_sub.setText(t("verifier_result_idle_desc"))
            self.btn_apply_result.setVisible(False)
        elif self.last_analysis_result is not None and not self._auto_recording and self._analysis_worker is None:
            self._render_analysis_result(self.last_analysis_result)

    def _update_play_button_text(self) -> None:
        if self.player.is_running:
            self.btn_play.setObjectName("stop_btn")
            self.btn_play.setText(t("verifier_stop"))
        else:
            self.btn_play.setObjectName("play_btn")
            self.btn_play.setText(t("verifier_play"))
        self.btn_play.style().unpolish(self.btn_play)
        self.btn_play.style().polish(self.btn_play)

    def _update_measure_buttons(self) -> None:
        is_busy = self._analysis_worker is not None
        if self._auto_recording:
            self.btn_auto_measure.setEnabled(True)
            self.btn_auto_measure.setText(t("verifier_auto_cancel"))
            self.btn_analyze.setEnabled(False)
            self.btn_analyze.setText(t("verifier_analyze_btn"))
        elif is_busy:
            self.btn_auto_measure.setEnabled(False)
            self.btn_auto_measure.setText(t("verifier_auto_measure_btn"))
            self.btn_analyze.setEnabled(False)
            self.btn_analyze.setText(t("verifier_analyze_running"))
        else:
            self.btn_auto_measure.setEnabled(bool(self.obs_client.is_connected))
            self.btn_auto_measure.setText(t("verifier_auto_measure_btn"))
            self.btn_analyze.setEnabled(True)
            self.btn_analyze.setText(t("verifier_analyze_btn"))

    def _populate_video_sources(self) -> None:
        """Fetch OBS video sources into combo_video_source (preserving current selection if possible)."""
        self.combo_video_source.blockSignals(True)
        self.combo_video_source.clear()
        if not self.obs_client.is_connected:
            self.combo_video_source.setVisible(False)
            self.combo_video_source.blockSignals(False)
            return

        sources = []
        try:
            raw_sources = self.obs_client.get_video_sources()
            if isinstance(raw_sources, list):
                sources = [
                    s for s in raw_sources
                    if getattr(s, "name", "") not in (MEASUREMENT_WINDOW_SOURCE_NAME, MEASUREMENT_GAME_SOURCE_NAME)
                ]
        except Exception:
            sources = []

        if not sources:
            self.combo_video_source.setVisible(False)
            self.combo_video_source.blockSignals(False)
            return

        self.combo_video_source.setVisible(True)
        selected_idx = 0
        for idx, s in enumerate(sources):
            self.combo_video_source.addItem(s.name, s.name)
            if self.current_obs_video_source and s.name == self.current_obs_video_source:
                selected_idx = idx
        self.combo_video_source.setCurrentIndex(selected_idx)
        self.current_obs_video_source = self.combo_video_source.currentData()
        self.combo_video_source.blockSignals(False)

    def _on_video_source_selected(self, index: int) -> None:
        if index < 0:
            return
        name = self.combo_video_source.itemData(index)
        if name:
            self.current_obs_video_source = str(name)
            self._refresh_obs_info()

    def _refresh_obs_info(self) -> None:
        if self.obs_client.is_connected and self.combo_video_source.count() == 0:
            self._populate_video_sources()
        elif not self.obs_client.is_connected:
            self.combo_video_source.setVisible(False)

        self.label_obs_trim_title.setText(
            t("verifier_obs_video_trim") if self.current_obs_video_source else t("verifier_obs_trim")
        )
        target_name = self.current_obs_video_source or self.current_obs_source
        self._update_measure_buttons()
        if not self.obs_client.is_connected or not target_name:
            self.label_obs_info.setVisible(True)
            self.label_obs_info.setText(t("verifier_obs_not_connected"))
            self.obs_trim_frame.setEnabled(False)
            return

        self.obs_trim_frame.setEnabled(True)
        try:
            if self.current_obs_video_source:
                cur_val = self.obs_client.get_render_delay(self.current_obs_video_source)
                self.spin_obs_delay.setRange(0, MAX_RENDER_DELAY_MS)
            else:
                cur_val = self.obs_client.get_sync_offset(target_name)
                self.spin_obs_delay.setRange(0, 5000)
            self.spin_obs_delay.blockSignals(True)
            self.spin_obs_delay.setValue(int(cur_val))
            self.spin_obs_delay.blockSignals(False)
            if not self.combo_video_source.isHidden():
                self.label_obs_info.setVisible(False)
            else:
                self.label_obs_info.setVisible(True)
                self.label_obs_info.setText(
                    f"{t('verifier_target_source', name=target_name)} | {t('verifier_obs_current', offset=cur_val)}"
                )
        except Exception:
            self.label_obs_info.setVisible(True)
            self.label_obs_info.setText(t("verifier_obs_not_connected"))

    def _toggle_playback(self) -> None:
        if self.player.is_running:
            self.player.stop()
        else:
            self.player.start()
        self._update_play_button_text()

    def _open_game_capture_window(self) -> None:
        """Open (or re-show) a top-level native D3D11 window that OBS 'Game Capture' can hook directly."""
        if self.game_capture_window is None:
            self.game_capture_window = GameCaptureTargetWindow(self.canvas, self._toggle_playback)
        self.game_capture_window.setTitle(t("verifier_game_capture_title"))
        self.game_capture_window.show()
        self.game_capture_window.resume_timer()
        self.game_capture_window.raise_()
        self.game_capture_window.requestActivate()

    # --- Auto-scene consent management ---
    def _has_auto_scene_consent(self) -> bool:
        settings = QSettings("SyncTone", "SyncTone")
        val = settings.value(self.CONSENT_SETTINGS_KEY, False)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    def _set_auto_scene_consent(self, consented: bool) -> None:
        settings = QSettings("SyncTone", "SyncTone")
        settings.setValue(self.CONSENT_SETTINGS_KEY, bool(consented))
        self._update_consent_button()

    def _update_consent_button(self) -> None:
        self.btn_revoke_consent.setVisible(self._has_auto_scene_consent())

    def _on_revoke_consent_clicked(self) -> None:
        self._set_auto_scene_consent(False)
        self._show_result_message(
            t("verifier_consent_revoked"),
            t("verifier_result_idle_desc"),
        )

    def _ensure_auto_scene_consent(self) -> bool:
        """Ask for one-time consent before creating a temporary OBS measurement scene."""
        if self._has_auto_scene_consent():
            return True
        answer = QMessageBox.question(
            self,
            t("verifier_consent_title"),
            t("verifier_consent_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._set_auto_scene_consent(True)
            return True
        return False

    # --- One-click OBS auto recording & measurement ---
    def _on_auto_measure_clicked(self) -> None:
        if self._auto_recording:
            self._cancel_auto_measure()
        else:
            self.start_auto_measure()

    def start_auto_measure(self, skip_consent: Optional[bool] = None) -> None:
        """Start automatic OBS recording for a few seconds and analyze the resulting file."""
        if self._auto_recording or self._analysis_worker is not None:
            return
        if not self.obs_client.is_connected:
            self._show_result_message(t("verifier_obs_not_connected"), "", is_error=True)
            return

        bypass_consent = self.dummy_mode if skip_consent is None else skip_consent
        if not bypass_consent and not self._ensure_auto_scene_consent():
            return

        try:
            if self.obs_client.get_record_status():
                self._show_result_message(
                    t("verifier_auto_already_recording_title"),
                    t("verifier_auto_already_recording_desc"),
                    is_error=True,
                )
                return
        except Exception as e:
            self._show_result_message(t("verifier_analyze_error_title"), str(e), is_error=True)
            return

        self._pre_auto_was_running = self.player.is_running
        self._pre_auto_bpm = self.spin_bpm.value()
        self._pre_auto_scene = None

        # Determine whether the selected video source uses game_capture; if so, open the D3D11 target window
        is_game_capture = False
        if self.current_obs_video_source:
            try:
                is_game_capture = (self.obs_client.get_input_kind(self.current_obs_video_source) == "game_capture")
            except Exception:
                is_game_capture = False

        if is_game_capture:
            was_open = self.game_capture_window is not None and self.game_capture_window.isVisible()
            self._open_game_capture_window()
            self._auto_opened_game_capture = not was_open
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            target_title = t("verifier_game_capture_title")
            target_hwnd = int(self.game_capture_window.winId()) if self.game_capture_window else 0
        else:
            self._auto_opened_game_capture = False
            target_title = self.windowTitle()
            target_hwnd = int(self.winId())

        window_class = self._get_win32_class_name(target_hwnd)
        exe_name = os.path.basename(sys.executable)

        output_device_name: Optional[str] = None
        if self.output_device_idx is not None and not self.dummy_mode:
            try:
                import sounddevice as sd
                dev_info = sd.query_devices(self.output_device_idx)
                output_device_name = str(dev_info.get("name", "")) or None
            except Exception:
                output_device_name = None

        # Prepare dedicated measurement scene with a cloned source (does not alter user's original scene/source)
        try:
            orig_scene, capture_kind = self.obs_client.prepare_measurement_scene(
                self.current_obs_video_source,
                window_title=target_title,
                exe_name=exe_name,
                audio_source=self.current_obs_source,
                window_class=window_class,
                output_device_name=output_device_name,
            )
            self._pre_auto_scene = orig_scene or None
            self._auto_capture_source = (
                MEASUREMENT_GAME_SOURCE_NAME if capture_kind == "game_capture" else MEASUREMENT_WINDOW_SOURCE_NAME
            )
        except Exception as e:
            self._restore_pre_auto_state()
            self._show_result_message(t("verifier_analyze_error_title"), str(e), is_error=True)
            return

        # Use non-commensurate tempo for sub-millisecond video phase sampling
        self.spin_bpm.setValue(self.ANALYSIS_BPM)
        if not self.player.is_running:
            self.player.start()
            self._update_play_button_text()

        self._auto_recording = True
        self._obs_recording_started = False
        self._auto_record_remaining = self.AUTO_RECORD_SECONDS
        self._video_poll_count = 0
        self.spin_bpm.setEnabled(False)
        self.btn_apply_result.setVisible(False)
        self._update_measure_buttons()

        # In dummy/test mode start immediately; in real mode verify OBS actually receives non-black frames first
        if self.dummy_mode:
            self._begin_obs_recording()
        else:
            self._show_result_message(
                t("verifier_auto_waiting_video"),
                t("verifier_auto_recording_desc"),
            )
            self._wait_for_video_timer.start()

    @staticmethod
    def _png_has_visible_content(png_bytes: Optional[bytes]) -> bool:
        """Return True if a screenshot PNG is non-empty and contains bright UI elements (not a black frame)."""
        if not png_bytes:
            return False
        img = QImage.fromData(png_bytes)
        if img.isNull() or img.width() <= 0 or img.height() <= 0:
            return False
        gray = img.convertToFormat(QImage.Format.Format_Grayscale8)
        ptr = gray.constBits()
        if not ptr:
            return False
        # Center hit line, badge, and sweeping bar have luminance well above 80 (pure black frame is 0)
        return max(ptr) >= 80

    def _on_wait_for_video_tick(self) -> None:
        if not self._auto_recording:
            self._wait_for_video_timer.stop()
            return

        self._video_poll_count += 1
        png_bytes = None
        if self._auto_capture_source:
            try:
                png_bytes = self.obs_client.get_source_screenshot_png(self._auto_capture_source)
            except Exception:
                png_bytes = None

        if self._png_has_visible_content(png_bytes):
            self._wait_for_video_timer.stop()
            # Brief settle so a few frames flow before recording starts
            QTimer.singleShot(250, self._begin_obs_recording)
            return

        # If still black at 2.5s, toggle visibility once to nudge OBS game_capture to re-hook
        if self._video_poll_count == self.AUTO_VIDEO_REFRESH_AT_POLL and self._auto_capture_source:
            try:
                self.obs_client.refresh_measurement_capture_source(self._auto_capture_source)
            except Exception:
                pass

        if self._video_poll_count >= self.AUTO_VIDEO_MAX_POLLS:
            self._wait_for_video_timer.stop()
            self._auto_recording = False
            self.spin_bpm.setEnabled(True)
            self._restore_pre_auto_state()
            self._update_measure_buttons()
            self._show_result_message(
                t("verifier_analyze_error_title"),
                t("verifier_auto_video_timeout"),
                is_error=True,
            )

    def _begin_obs_recording(self) -> None:
        if not self._auto_recording:
            return
        try:
            self.obs_client.start_record()
        except Exception as e:
            self._auto_recording = False
            self._obs_recording_started = False
            self.spin_bpm.setEnabled(True)
            self._restore_pre_auto_state()
            self._update_measure_buttons()
            self._show_result_message(t("verifier_analyze_error_title"), str(e), is_error=True)
            return
        self._obs_recording_started = True
        self._show_result_message(
            t("verifier_auto_recording_status", sec=self._auto_record_remaining),
            t("verifier_auto_recording_desc"),
        )
        self._auto_record_timer.start()

    def _on_auto_record_tick(self) -> None:
        self._auto_record_remaining -= 1
        if self._auto_record_remaining > 0:
            self._show_result_message(
                t("verifier_auto_recording_status", sec=self._auto_record_remaining),
                t("verifier_auto_recording_desc"),
            )
            return
        self._finish_auto_record()

    def _finish_auto_record(self) -> None:
        self._wait_for_video_timer.stop()
        self._auto_record_timer.stop()
        self._auto_recording = False
        self._obs_recording_started = False
        self.spin_bpm.setEnabled(True)

        output_path = ""
        try:
            output_path = self.obs_client.stop_record()
        except Exception as e:
            self._restore_pre_auto_state()
            self._update_measure_buttons()
            self._show_result_message(t("verifier_analyze_error_title"), str(e), is_error=True)
            return

        self._restore_pre_auto_state()
        self._update_measure_buttons()

        if not output_path:
            self._show_result_message(
                t("verifier_analyze_error_title"),
                t("verifier_auto_no_path"),
                is_error=True,
            )
            return

        self._show_result_message(t("verifier_analyze_running"), output_path)
        # Brief delay so OBS finishes flushing the container trailer before PyAV opens it
        QTimer.singleShot(350, lambda p=output_path: self.start_recording_analysis(p))

    def _cancel_auto_measure(self) -> None:
        if not self._auto_recording:
            return
        self._wait_for_video_timer.stop()
        self._auto_record_timer.stop()
        was_recording = self._obs_recording_started
        self._auto_recording = False
        self._obs_recording_started = False
        self.spin_bpm.setEnabled(True)
        if was_recording:
            try:
                if self.obs_client.is_connected:
                    self.obs_client.stop_record()
            except Exception:
                pass
        self._restore_pre_auto_state()
        self._update_measure_buttons()
        self._show_result_message(t("verifier_result_idle_title"), t("verifier_result_idle_desc"))

    @staticmethod
    def _get_win32_class_name(hwnd: int) -> str:
        """Return the exact Win32 window class name for OBS window/game capture matching."""
        if sys.platform == "win32" and hwnd:
            try:
                buf = ctypes.create_unicode_buffer(256)
                if ctypes.windll.user32.GetClassNameW(hwnd, buf, 256) > 0 and buf.value:
                    return buf.value
            except Exception:
                pass
        return "QtWindow"

    def _restore_pre_auto_state(self) -> None:
        self.spin_bpm.setValue(self._pre_auto_bpm)
        if not self._pre_auto_was_running and self.player.is_running:
            self.player.stop()
            self._update_play_button_text()
        if self._auto_opened_game_capture and self.game_capture_window is not None:
            # Hide and pause timer instead of destroying HWND/D3D11 SwapChain so OBS Game Capture
            # keeps its hook intact and immediately resumes capturing on subsequent measurements.
            self._auto_opened_game_capture = False
            try:
                self.game_capture_window.pause_timer()
                self.game_capture_window.hide()
            except Exception:
                pass
        else:
            self._auto_opened_game_capture = False

        if self._pre_auto_scene and self.obs_client.is_connected:
            scene_to_restore = self._pre_auto_scene
            self._pre_auto_scene = None
            try:
                self.obs_client.set_current_scene(scene_to_restore)
            except Exception:
                pass
            try:
                self.obs_client.cleanup_measurement_scene()
            except Exception:
                pass
        else:
            self._pre_auto_scene = None

    # --- Recording analysis ---
    def _choose_and_analyze_recording(self) -> None:
        """Let the user pick an OBS recording and analyze it in the background."""
        if self._analysis_worker is not None or self._auto_recording:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, t("verifier_analyze_file_title"), "", t("verifier_analyze_file_filter")
        )
        if path:
            self.start_recording_analysis(path)

    def start_recording_analysis(self, path: str, wrap_phase: float = 0.5) -> None:
        """Start analyzing the given recording file (result shown in the window when finished)."""
        if self._analysis_worker is not None:
            return
        self.btn_apply_result.setVisible(False)
        self._show_result_message(t("verifier_analyze_running"), path)
        self._analysis_worker = RecordingAnalysisWorker(path, wrap_phase=wrap_phase)
        self._analysis_worker.finished_analysis.connect(self._on_analysis_finished)
        self._analysis_worker.error_occurred.connect(self._on_analysis_error)
        self._update_measure_buttons()
        self._analysis_worker.start()

    def _end_analysis(self) -> None:
        if self._analysis_worker is not None:
            self._analysis_worker.wait(1000)
            self._analysis_worker = None
        self._update_measure_buttons()

    @classmethod
    def format_analysis_summary(cls, result: AvOffsetResult) -> str:
        """Human readable summary of an analysis result (positive offset: video later than audio)."""
        off = result.offset_ms
        abs_off = abs(off)
        if abs_off < 1.0:
            head = t("verifier_analyze_in_sync")
        elif off > 0:
            head = t("verifier_analyze_video_late", ms=off)
        else:
            head = t("verifier_analyze_audio_late", ms=-off)

        if abs_off <= cls.OFFSET_OK_MS:
            grade = t("verifier_analyze_grade_ok")
        elif abs_off <= cls.OFFSET_MINOR_MS:
            grade = t("verifier_analyze_grade_minor")
        else:
            grade = t("verifier_analyze_grade_large")

        detail = t(
            "verifier_analyze_detail",
            unc=result.uncertainty_ms, beeps=result.n_beeps, frames=result.n_frames,
        )
        return f"{head}\n{grade}\n{detail}"

    def _show_result_message(self, title: str, detail: str, is_error: bool = False) -> None:
        color = "#ff8a80" if is_error else "#d8d8ee"
        self.label_result_main.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        self.label_result_main.setText(title)
        self.label_result_sub.setText(detail)

    def _render_analysis_result(self, result: AvOffsetResult) -> None:
        lines = self.format_analysis_summary(result).split("\n")
        head = lines[0] if len(lines) > 0 else ""
        grade = lines[1] if len(lines) > 1 else ""
        detail = lines[2] if len(lines) > 2 else ""

        abs_off = abs(result.offset_ms)
        if abs_off <= self.OFFSET_OK_MS:
            color = "#69f0ae"
        elif abs_off <= self.OFFSET_MINOR_MS:
            color = "#ffd54f"
        else:
            color = "#ff8a80"

        self.label_result_main.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        self.label_result_main.setText(f"{head}  —  {grade}")
        self.label_result_sub.setText(detail)

        # Prepare one-click apply button if OBS is connected and adjustment is non-zero
        delta = int(round(result.offset_ms))
        self._pending_apply_delta = None
        self._pending_apply_is_video = False
        self.btn_apply_result.setVisible(False)

        if delta != 0 and self.obs_client.is_connected and self.current_obs_video_source:
            try:
                cur_vid = self.obs_client.get_render_delay(self.current_obs_video_source)
            except Exception:
                cur_vid = None
            if cur_vid is not None:
                raw_target = cur_vid - delta
                new_vid = max(0, min(MAX_RENDER_DELAY_MS, raw_target))
                if new_vid != cur_vid:
                    self._pending_apply_delta = int(new_vid - cur_vid)
                    self._pending_apply_is_video = True
                    self.btn_apply_result.setText(
                        t("verifier_apply_result_btn", cur=cur_vid, new=new_vid)
                    )
                    self.btn_apply_result.setEnabled(True)
                    self.btn_apply_result.setVisible(True)
                if raw_target != new_vid:
                    self.label_result_sub.setText(
                        f"{detail}\n{t('verifier_analyze_video_clamp_note', rest=abs(raw_target - new_vid))}"
                    )
                return

        if delta != 0 and self.obs_client.is_connected and self.current_obs_source:
            try:
                cur = self.obs_client.get_sync_offset(self.current_obs_source)
            except Exception:
                cur = None
            if cur is not None:
                new_val = max(0, cur + delta)
                if new_val != cur:
                    self._pending_apply_delta = int(new_val - cur)
                    self._pending_apply_is_video = False
                    self.btn_apply_result.setText(
                        t("verifier_apply_result_btn", cur=cur, new=new_val)
                    )
                    self.btn_apply_result.setEnabled(True)
                    self.btn_apply_result.setVisible(True)
                if cur + delta < 0:
                    self.label_result_sub.setText(
                        f"{detail}\n{t('verifier_analyze_clamp_note', rest=-(cur + delta))}"
                    )

    def _on_analysis_finished(self, result: AvOffsetResult) -> None:
        self._end_analysis()
        self.last_analysis_result = result
        self._render_analysis_result(result)

    def _apply_analysis_result(self) -> None:
        if self._pending_apply_delta is None:
            return
        delta = self._pending_apply_delta
        self._pending_apply_delta = None
        self._adjust_obs_offset(float(delta))
        self.btn_apply_result.setText(t("verifier_apply_result_done"))
        self.btn_apply_result.setEnabled(False)

    def _on_analysis_error(self, error_msg: str) -> None:
        self._end_analysis()
        self._show_result_message(
            t("verifier_analyze_error_title"),
            t("verifier_analyze_error_msg", error=error_msg),
            is_error=True,
        )

    def _on_bpm_changed(self, value: int) -> None:
        self.player.set_bpm(float(value))

    def _on_volume_changed(self, value: int) -> None:
        self.player.set_amplitude(value / 100.0)

    def _on_obs_delay_spin_finished(self) -> None:
        """Apply direct numeric entry from the OBS delay spinbox."""
        if not self.obs_client.is_connected:
            return
        target_val = self.spin_obs_delay.value()
        if self.current_obs_video_source:
            try:
                cur = self.obs_client.get_render_delay(self.current_obs_video_source)
                if target_val != cur:
                    self._adjust_obs_offset(float(target_val - cur))
            except Exception:
                pass
            return
        if self.current_obs_source:
            try:
                cur = self.obs_client.get_sync_offset(self.current_obs_source)
                if target_val != cur:
                    self._adjust_obs_offset(float(target_val - cur))
            except Exception:
                pass

    def _adjust_obs_offset(self, delta_ms: float) -> None:
        """Directly adjust OBS video render delay (preferred) or audio sync offset from the verifier window."""
        if not self.obs_client.is_connected:
            return

        if self.current_obs_video_source:
            try:
                cur = self.obs_client.get_render_delay(self.current_obs_video_source)
                new_val = max(0, min(MAX_RENDER_DELAY_MS, int(round(cur + delta_ms))))
                actual = self.obs_client.set_render_delay(self.current_obs_video_source, new_val)
                self._refresh_obs_info()
                if self.on_video_delay_changed_cb is not None:
                    self.on_video_delay_changed_cb(actual)
            except Exception:
                pass
            return

        if not self.current_obs_source:
            return

        try:
            cur = self.obs_client.get_sync_offset(self.current_obs_source)
            new_val = max(0, int(round(cur + delta_ms)))
            self.obs_client.set_sync_offset(self.current_obs_source, new_val)
            self._refresh_obs_info()

            if self.on_offset_changed_cb is not None:
                self.on_offset_changed_cb(float(new_val))
        except Exception:
            pass

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._toggle_playback()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def update_device_and_source(
        self,
        device_idx: Optional[int],
        obs_source: Optional[str],
        obs_video_source: Optional[str] = None,
    ) -> None:
        """Update hardware output device and OBS source target dynamically."""
        self.output_device_idx = device_idx
        self.current_obs_source = obs_source
        if obs_video_source is not None:
            self.current_obs_video_source = obs_video_source
        self.player.set_output_device(device_idx)
        self._populate_video_sources()
        self._refresh_obs_info()

    def closeEvent(self, event) -> None:
        """Ensure audio stream, auto-recording, and animation timer stop cleanly when window is closed."""
        if self._auto_recording:
            self._cancel_auto_measure()
        self.canvas.stop_timer()
        self.player.stop()
        if self.game_capture_window is not None:
            try:
                self.game_capture_window.stop_timer()
                self.game_capture_window.close()
            except Exception:
                pass
            self.game_capture_window = None
        if self._analysis_worker is not None:
            # Let a running analysis finish in the background without touching this (closed) window
            worker = self._analysis_worker
            self._analysis_worker = None
            worker.finished_analysis.disconnect()
            worker.error_occurred.disconnect()
            _orphan_workers.append(worker)
            worker.finished.connect(lambda w=worker: _orphan_workers.remove(w))
        super().closeEvent(event)
