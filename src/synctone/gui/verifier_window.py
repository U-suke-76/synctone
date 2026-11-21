"""Real-time AV Sync and Auditory Verification Window (AV Sync Checker)."""

import math
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QRadioButton, QButtonGroup, QFrame, QSizePolicy,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QKeyEvent

from synctone.core.av_analysis import AvOffsetResult
from synctone.core.verifier_audio import SyncAudioPlayer
from synctone.gui.game_capture import GameCaptureTargetWindow, _D3D11Presenter  # noqa: F401
from synctone.gui.styles import VERIFIER_DIALOG_QSS
from synctone.gui.workers import RecordingAnalysisWorker
from synctone.obs.client import MAX_RENDER_DELAY_MS, ObsClient
from synctone.i18n import t

# Analysis workers still running after their window was closed (kept alive until they finish)
_orphan_workers: list = []


class SyncCanvas(QWidget):
    """60 FPS Animated Visual & AV Sync Canvas for OBS Window Capture."""

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

        # Flash decay tracker
        self._flash_intensity: float = 0.0

        # Recording-analysis timecode mode: a bar whose x position encodes the app-clock phase
        self.analysis_mode: bool = False

    def stop_timer(self) -> None:
        """Stop the 60fps animation timer."""
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event) -> None:
        self.render_scene(self, self.width(), self.height())

    def render_scene(self, paint_device, w: int, h: int) -> None:
        """Render the current animation frame onto any QPaintDevice (QWidget or QOpenGLWindow)."""
        # Read the clock first so the bar is labelled with the instant this frame is rendered
        analysis_phase = (
            self.player.get_clock_phase() if (self.analysis_mode and self.player.is_running) else 0.0
        )
        painter = QPainter(paint_device)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            if self.analysis_mode:
                self._draw_analysis_mode(painter, w, h, analysis_phase)
                return

            # Background
            painter.fillRect(0, 0, w, h, QColor("#101016"))

            # Obtain current player phase (-0.5 to +0.5)
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

    # Horizontal margin of the analysis track (phase 0 at the left margin, phase 1 at the right one)
    ANALYSIS_MARGIN = 40
    ANALYSIS_BAR_WIDTH = 6.0

    def _draw_analysis_mode(self, painter: QPainter, w: int, h: int, phase: float) -> None:
        """Pure black canvas with a single white bar: easy to decode from a screen recording."""
        painter.fillRect(0, 0, w, h, QColor("#000000"))
        margin = self.ANALYSIS_MARGIN
        track_w = max(1.0, float(w - 2 * margin))
        x = margin + phase * track_w
        y0 = h * 0.2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRect(QRectF(x - self.ANALYSIS_BAR_WIDTH / 2.0, y0, self.ANALYSIS_BAR_WIDTH, h * 0.6))

    def _draw_av_sync_mode(self, painter: QPainter, w: int, h: int, phase: float, is_running: bool) -> None:
        """Render the horizontal sweeper timeline with milliseconds scale and center flash."""
        center_x = w / 2.0
        track_y = h * 0.55
        track_h = 36.0

        # Flash background overlay at center hit
        if self._flash_intensity > 0.0:
            flash_alpha = int(self._flash_intensity * 75)
            flash_color = QColor(0, 229, 255, flash_alpha)
            painter.fillRect(0, 0, w, h, flash_color)

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
            glow_pen = QPen(QColor(0, 229, 255, int(200 * self._flash_intensity)), 8)
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

        # Moving Sweeper Bar
        # phase goes from -0.5 (left) to 0.0 (center) to +0.5 (right)
        bar_x = center_x + phase * (w - 60)
        bar_x = max(20.0, min(float(w - 20), bar_x))

        if is_running:
            # Outer glow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 64, 129, 60)))
            painter.drawRoundedRect(int(bar_x - 6), int(track_y - 24), 12, 48, 6, 6)

            # Core bar
            painter.setBrush(QBrush(QColor("#ff4081")))
            painter.drawRoundedRect(int(bar_x - 3), int(track_y - 20), 6, 40, 3, 3)

            # Top pointer triangle
            pointer_y = track_y - 24
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

    # Tempo used by the recording-analysis mode (cycle = 32.7 frames at 60 fps, 16.4 at 30 fps)
    ANALYSIS_BPM = 110

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
        self.game_capture_window: Optional[GameCaptureTargetWindow] = None

        self.player = SyncAudioPlayer(
            sample_rate=48000,
            bpm=120.0,
            amplitude=0.5,
            output_device_idx=self.output_device_idx,
            dummy_mode=self.dummy_mode,
        )

        self.resize(760, 520)
        self.setMinimumSize(620, 440)
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
        main_layout.addWidget(self.hint_banner)

        # 2. Visual Animation Canvas
        self.canvas = SyncCanvas(self.player, self)
        main_layout.addWidget(self.canvas, stretch=1)

        # 3. Control Panel
        self.ctrl_panel = QFrame()
        self.ctrl_panel.setObjectName("ctrl_panel")
        ctrl_layout = QVBoxLayout(self.ctrl_panel)
        ctrl_layout.setContentsMargins(10, 8, 10, 8)
        ctrl_layout.setSpacing(8)

        # Row 1: Mode selector + hint description
        row1 = QHBoxLayout()
        row1.setSpacing(14)

        self.radio_flash = QRadioButton()
        self.radio_flash.setChecked(True)
        self.radio_flash.toggled.connect(self._on_mode_toggled)
        row1.addWidget(self.radio_flash)

        self.radio_analysis = QRadioButton()
        self.radio_analysis.toggled.connect(self._on_mode_toggled)
        row1.addWidget(self.radio_analysis)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_flash)
        self.mode_group.addButton(self.radio_analysis)

        row1.addStretch()
        ctrl_layout.addLayout(row1)

        # Row 1b: Mode description on its own line so radio labels are never truncated
        self.label_mode_desc = QLabel()
        self.label_mode_desc.setStyleSheet("color: #aaaacc; font-size: 11px;")
        self.label_mode_desc.setWordWrap(True)
        ctrl_layout.addWidget(self.label_mode_desc)

        # Row 2: Play/Stop + Tempo + Volume
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        self.btn_play = QPushButton()
        self.btn_play.setObjectName("play_btn")
        self.btn_play.setMinimumWidth(130)
        self.btn_play.clicked.connect(self._toggle_playback)
        row2.addWidget(self.btn_play)

        row2.addSpacing(12)
        self.label_tempo = QLabel()
        row2.addWidget(self.label_tempo)

        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(40, 240)
        self.spin_bpm.setValue(120)
        self.spin_bpm.setSuffix(" BPM")
        self.spin_bpm.setFixedWidth(115)
        self.spin_bpm.valueChanged.connect(self._on_bpm_changed)
        row2.addWidget(self.spin_bpm)

        row2.addSpacing(12)
        self.label_volume = QLabel()
        row2.addWidget(self.label_volume)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(10, 100)
        self.slider_volume.setValue(50)
        self.slider_volume.setFixedWidth(100)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        row2.addWidget(self.slider_volume)

        row2.addStretch()

        # Recording analysis (only shown in the recording-analysis mode)
        self.btn_analyze = QPushButton()
        self.btn_analyze.setObjectName("analyze_btn")
        self.btn_analyze.clicked.connect(self._choose_and_analyze_recording)
        self.btn_analyze.setVisible(False)
        row2.addWidget(self.btn_analyze)
        ctrl_layout.addLayout(row2)

        # Row 3: OBS Direct Trim Shortcut Bar
        self.obs_trim_frame = QFrame()
        self.obs_trim_frame.setObjectName("obs_trim_frame")
        obs_trim_layout = QHBoxLayout(self.obs_trim_frame)
        obs_trim_layout.setContentsMargins(0, 4, 0, 0)
        obs_trim_layout.setSpacing(6)

        self.label_obs_trim_title = QLabel()
        self.label_obs_trim_title.setStyleSheet("font-weight: bold; color: #82aaff; font-size: 11px;")
        obs_trim_layout.addWidget(self.label_obs_trim_title)

        self.label_obs_info = QLabel()
        self.label_obs_info.setStyleSheet("color: #bbbbcc; font-size: 11px;")
        obs_trim_layout.addWidget(self.label_obs_info)

        obs_trim_layout.addStretch()

        # Trim buttons: -5ms, -1ms, +1ms, +5ms
        for delta in [-5, -1, 1, 5]:
            sign = "+" if delta > 0 else ""
            btn = QPushButton(f"{sign}{delta}ms")
            btn.setObjectName("trim_btn")
            btn.setMinimumWidth(58)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_obs_offset(d))
            obs_trim_layout.addWidget(btn)

        ctrl_layout.addWidget(self.obs_trim_frame)
        main_layout.addWidget(self.ctrl_panel)

    def retranslate_ui(self) -> None:
        """Update strings to current locale."""
        self.setWindowTitle(t("verifier_title"))
        self.label_hint.setText(t("verifier_obs_hint"))
        self.btn_game_capture.setText(t("verifier_game_capture_btn"))
        if self.game_capture_window is not None:
            self.game_capture_window.setTitle(t("verifier_game_capture_title"))
        self.radio_flash.setText(t("verifier_mode_flash"))
        self.radio_analysis.setText(t("verifier_mode_analysis"))
        self.label_tempo.setText(t("verifier_tempo"))
        self.label_volume.setText(t("verifier_volume"))
        self.label_obs_trim_title.setText(
            t("verifier_obs_video_trim") if self.current_obs_video_source else t("verifier_obs_trim")
        )
        self.btn_analyze.setText(
            t("verifier_analyze_running") if self._analysis_worker is not None else t("verifier_analyze_btn")
        )

        self._update_play_button_text()
        self._update_mode_description()
        self._refresh_obs_info()

    def _update_play_button_text(self) -> None:
        if self.player.is_running:
            self.btn_play.setObjectName("stop_btn")
            self.btn_play.setText(t("verifier_stop"))
        else:
            self.btn_play.setObjectName("play_btn")
            self.btn_play.setText(t("verifier_play"))
        self.btn_play.style().unpolish(self.btn_play)
        self.btn_play.style().polish(self.btn_play)

    def _update_mode_description(self) -> None:
        if self.radio_analysis.isChecked():
            self.label_mode_desc.setText(f"💡 {t('verifier_analysis_hint')}")
        else:
            self.label_mode_desc.setText(f"💡 {t('verifier_flash_hint')}")

    def _refresh_obs_info(self) -> None:
        self.label_obs_trim_title.setText(
            t("verifier_obs_video_trim") if self.current_obs_video_source else t("verifier_obs_trim")
        )
        target_name = self.current_obs_video_source or self.current_obs_source
        if not self.obs_client.is_connected or not target_name:
            self.label_obs_info.setText(t("verifier_obs_not_connected"))
            self.obs_trim_frame.setEnabled(False)
            return

        self.obs_trim_frame.setEnabled(True)
        try:
            if self.current_obs_video_source:
                cur_val = self.obs_client.get_render_delay(self.current_obs_video_source)
            else:
                cur_val = self.obs_client.get_sync_offset(target_name)
            self.label_obs_info.setText(
                f"{t('verifier_target_source', name=target_name)} | {t('verifier_obs_current', offset=cur_val)}"
            )
        except Exception:
            self.label_obs_info.setText(t("verifier_obs_not_connected"))

    def _toggle_playback(self) -> None:
        if self.player.is_running:
            self.player.stop()
        else:
            self.player.start()
        self._update_play_button_text()

    def _open_game_capture_window(self) -> None:
        """Open a top-level native OpenGL window that OBS 'Game Capture' can hook directly."""
        if self.game_capture_window is None:
            self.game_capture_window = GameCaptureTargetWindow(self.canvas, self._toggle_playback)
        self.game_capture_window.setTitle(t("verifier_game_capture_title"))
        self.game_capture_window.show()
        self.game_capture_window.raise_()
        self.game_capture_window.requestActivate()

    def _on_mode_toggled(self) -> None:
        analysis = self.radio_analysis.isChecked()
        self.canvas.analysis_mode = analysis
        if analysis:
            # Fixed analysis tempo: not a multiple of common frame intervals so frames sample the cycle densely
            self.spin_bpm.setValue(self.ANALYSIS_BPM)
        self.spin_bpm.setEnabled(not analysis)
        self.btn_analyze.setVisible(analysis)
        self._update_mode_description()

    # --- Recording analysis ---
    def _choose_and_analyze_recording(self) -> None:
        """Let the user pick an OBS recording and analyze it in the background."""
        if self._analysis_worker is not None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, t("verifier_analyze_file_title"), "", t("verifier_analyze_file_filter")
        )
        if path:
            self.start_recording_analysis(path)

    def start_recording_analysis(self, path: str) -> None:
        """Start analyzing the given recording file (result shown when finished)."""
        if self._analysis_worker is not None:
            return
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText(t("verifier_analyze_running"))
        self._analysis_worker = RecordingAnalysisWorker(path)
        self._analysis_worker.finished_analysis.connect(self._on_analysis_finished)
        self._analysis_worker.error_occurred.connect(self._on_analysis_error)
        self._analysis_worker.start()

    def _end_analysis(self) -> None:
        if self._analysis_worker is not None:
            self._analysis_worker.wait(1000)
            self._analysis_worker = None
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText(t("verifier_analyze_btn"))

    # Thresholds for 3-tier AV offset verdict (based on 60 fps = 16.7 ms/frame)
    OFFSET_OK_MS = 8.0      # <= 8 ms (~0.5 frame): practically in sync
    OFFSET_MINOR_MS = 17.0  # <= 17 ms (~1 frame): minor offset

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

    def _on_analysis_finished(self, result: AvOffsetResult) -> None:
        self._end_analysis()
        self.last_analysis_result = result
        summary = self.format_analysis_summary(result)
        delta = int(round(result.offset_ms))
        default_btn = (
            QMessageBox.StandardButton.No
            if abs(result.offset_ms) <= self.OFFSET_OK_MS
            else QMessageBox.StandardButton.Yes
        )

        # 1. Preferred: adjust video source render delay while keeping audio sync offset untouched.
        #    result.offset_ms = v - c (positive: video later than audio, negative: audio later than video).
        #    To align video to audio, change video render delay by -offset_ms.
        if delta != 0 and self.obs_client.is_connected and self.current_obs_video_source:
            try:
                cur_vid = self.obs_client.get_render_delay(self.current_obs_video_source)
            except Exception:
                cur_vid = None
            if cur_vid is not None:
                raw_target = cur_vid - delta
                new_vid = max(0, min(MAX_RENDER_DELAY_MS, raw_target))
                msg = (
                    f"{summary}\n\n"
                    f"{t('verifier_analyze_apply_video_q', name=self.current_obs_video_source, cur=cur_vid, new=new_vid)}"
                )
                if raw_target != new_vid:
                    msg += f"\n{t('verifier_analyze_video_clamp_note', rest=abs(raw_target - new_vid))}"
                answer = QMessageBox.question(
                    self, t("verifier_analyze_result_title"), msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    default_btn,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self._adjust_obs_offset(float(new_vid - cur_vid))
                return

        # 2. Fallback when no video source is available: offer to adjust audio sync offset
        if delta != 0 and self.obs_client.is_connected and self.current_obs_source:
            try:
                cur = self.obs_client.get_sync_offset(self.current_obs_source)
            except Exception:
                cur = None
            if cur is not None:
                new_val = max(0, cur + delta)
                msg = f"{summary}\n\n{t('verifier_analyze_apply_q', name=self.current_obs_source, cur=cur, new=new_val)}"
                if cur + delta < 0:
                    msg += f"\n{t('verifier_analyze_clamp_note', rest=-(cur + delta))}"
                answer = QMessageBox.question(
                    self, t("verifier_analyze_result_title"), msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    default_btn,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self._adjust_obs_offset(float(new_val - cur))
                return

        QMessageBox.information(self, t("verifier_analyze_result_title"), summary)

    def _on_analysis_error(self, error_msg: str) -> None:
        self._end_analysis()
        QMessageBox.warning(
            self, t("verifier_analyze_error_title"), t("verifier_analyze_error_msg", error=error_msg)
        )

    def _on_bpm_changed(self, value: int) -> None:
        self.player.set_bpm(float(value))

    def _on_volume_changed(self, value: int) -> None:
        self.player.set_amplitude(value / 100.0)

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
        self.current_obs_video_source = obs_video_source
        self.player.set_output_device(device_idx)
        self._refresh_obs_info()

    def closeEvent(self, event) -> None:
        """Ensure audio stream and animation timer stop cleanly when window is closed."""
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
