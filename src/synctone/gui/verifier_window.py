"""Real-time AV Sync and Auditory Verification Window (AV Sync Checker)."""

import math
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QRadioButton, QButtonGroup, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QKeyEvent

from synctone.core.verifier_audio import SyncAudioPlayer
from synctone.obs.client import ObsClient
from synctone.i18n import t


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

    def stop_timer(self) -> None:
        """Stop the 60fps animation timer."""
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            w = self.width()
            h = self.height()

            # Background
            painter.fillRect(0, 0, w, h, QColor("#101016"))

            # Obtain current player phase (-0.5 to +0.5)
            phase = self.player.get_phase() if self.player.is_running else -0.5
            is_running = self.player.is_running
            mode = self.player.mode

            # Trigger flash intensity when phase approaches center (hit point)
            if is_running and abs(phase) < 0.035:
                self._flash_intensity = 1.0
            else:
                self._flash_intensity = max(0.0, self._flash_intensity - 0.08)

            # Visual Flash / AV Sync Mode
            if mode == "beep":
                self._draw_av_sync_mode(painter, w, h, phase, is_running)
            else:
                self._draw_click_mode(painter, w, h, phase, is_running)
        finally:
            painter.end()

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

    def _draw_click_mode(self, painter: QPainter, w: int, h: int, phase: float, is_running: bool) -> None:
        """Render a rhythmic pulsating metronome dial for auditory click check."""
        center_x = w / 2.0
        center_y = h / 2.0
        radius = min(w, h) * 0.32

        # Outer rhythm circle
        painter.setPen(QPen(QColor("#252538"), 3))
        painter.setBrush(QBrush(QColor("#151520")))
        painter.drawEllipse(int(center_x - radius), int(center_y - radius), int(radius * 2), int(radius * 2))

        # Flash on beat
        if self._flash_intensity > 0.0:
            glow_rad = radius * (1.0 + self._flash_intensity * 0.12)
            glow_alpha = int(self._flash_intensity * 120)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 64, 129, glow_alpha)))
            painter.drawEllipse(
                int(center_x - glow_rad), int(center_y - glow_rad),
                int(glow_rad * 2), int(glow_rad * 2)
            )

        # Swinging metronome indicator
        # angle goes smoothly from -40 deg to +40 deg
        swing_angle = math.sin(phase * 2 * math.pi) * 42.0  # degrees
        rad = math.radians(swing_angle - 90)  # -90 deg is top
        tip_x = center_x + radius * 0.85 * math.cos(rad)
        tip_y = center_y + radius * 0.85 * math.sin(rad)

        painter.setPen(QPen(QColor("#00e5ff"), 3))
        painter.drawLine(int(center_x), int(center_y), int(tip_x), int(tip_y))

        # Pivot center
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(int(center_x - 6), int(center_y - 6), 12, 12)

        # Pulse tip
        tip_color = QColor("#ff4081") if self._flash_intensity > 0.2 else QColor("#00e5ff")
        painter.setBrush(QBrush(tip_color))
        painter.drawEllipse(int(tip_x - 8), int(tip_y - 8), 16, 16)

        # Label
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#bbbbdd"))
        text = f"{int(self.player.bpm)} BPM" if is_running else t("verifier_play")
        painter.drawText(0, int(center_y + radius + 15), w, 24, Qt.AlignmentFlag.AlignCenter, text)


class SyncVerifierWindow(QDialog):
    """Independent verification window for real-time auditory & visual sync testing."""

    def __init__(
        self,
        obs_client: ObsClient,
        output_device_idx: Optional[int] = None,
        current_obs_source: Optional[str] = None,
        on_offset_changed_cb: Optional[Callable[[float], None]] = None,
        dummy_mode: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.obs_client = obs_client
        self.output_device_idx = output_device_idx
        self.current_obs_source = current_obs_source
        self.on_offset_changed_cb = on_offset_changed_cb
        self.dummy_mode = dummy_mode

        self.player = SyncAudioPlayer(
            sample_rate=48000,
            bpm=120.0,
            amplitude=0.5,
            output_device_idx=self.output_device_idx,
            mode="beep",
            dummy_mode=self.dummy_mode,
        )

        self.resize(760, 520)
        self.setMinimumSize(620, 440)
        self._apply_dark_theme()
        self._init_ui()
        self.retranslate_ui()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #121218;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Meiryo', sans-serif;
            }
            QFrame#obs_hint_banner {
                background-color: #151e34;
                border: 1px solid #1e3a6a;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QFrame#ctrl_panel {
                background-color: #181824;
                border: 1px solid #2a2a38;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton {
                background-color: #232334;
                border: 1px solid #3d3d52;
                border-radius: 5px;
                padding: 6px 12px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #313148;
                border-color: #5c5c7a;
            }
            QPushButton#play_btn {
                background-color: #00897b;
                border: 1px solid #26a69a;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 20px;
                border-radius: 6px;
            }
            QPushButton#play_btn:hover {
                background-color: #009688;
            }
            QPushButton#stop_btn {
                background-color: #c62828;
                border: 1px solid #e53935;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 20px;
                border-radius: 6px;
            }
            QPushButton#stop_btn:hover {
                background-color: #d32f2f;
            }
            QRadioButton {
                color: #ccccdd;
                font-size: 12px;
                font-weight: bold;
                spacing: 6px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
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
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
        """)

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
        banner_layout.addWidget(self.label_hint)
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

        self.radio_click = QRadioButton()
        self.radio_click.toggled.connect(self._on_mode_toggled)
        row1.addWidget(self.radio_click)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_flash)
        self.mode_group.addButton(self.radio_click)

        row1.addSpacing(10)
        self.label_mode_desc = QLabel()
        self.label_mode_desc.setStyleSheet("color: #aaaacc; font-size: 11px;")
        row1.addWidget(self.label_mode_desc, stretch=1)

        ctrl_layout.addLayout(row1)

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
        ctrl_layout.addLayout(row2)

        # Row 3: OBS Direct Trim Shortcut Bar
        self.obs_trim_frame = QFrame()
        self.obs_trim_frame.setStyleSheet("border-top: 1px solid #28283a; padding-top: 6px;")
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
            btn.setFixedWidth(54)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_obs_offset(d))
            obs_trim_layout.addWidget(btn)

        ctrl_layout.addWidget(self.obs_trim_frame)
        main_layout.addWidget(self.ctrl_panel)

    def retranslate_ui(self) -> None:
        """Update strings to current locale."""
        self.setWindowTitle(t("verifier_title"))
        self.label_hint.setText(t("verifier_obs_hint"))
        self.radio_flash.setText(t("verifier_mode_flash"))
        self.radio_click.setText(t("verifier_mode_click"))
        self.label_tempo.setText(t("verifier_tempo"))
        self.label_volume.setText(t("verifier_volume"))
        self.label_obs_trim_title.setText(t("verifier_obs_trim"))

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
        if self.radio_flash.isChecked():
            self.label_mode_desc.setText(f"💡 {t('verifier_flash_hint')}")
        else:
            self.label_mode_desc.setText(f"💡 {t('verifier_click_hint')}")

    def _refresh_obs_info(self) -> None:
        if not self.obs_client.is_connected or not self.current_obs_source:
            self.label_obs_info.setText(t("verifier_obs_not_connected"))
            self.obs_trim_frame.setEnabled(False)
            return

        self.obs_trim_frame.setEnabled(True)
        try:
            cur_offset = self.obs_client.get_sync_offset(self.current_obs_source)
            self.label_obs_info.setText(
                f"{t('verifier_target_source', name=self.current_obs_source)} | {t('verifier_obs_current', offset=cur_offset)}"
            )
        except Exception:
            self.label_obs_info.setText(t("verifier_obs_not_connected"))

    def _toggle_playback(self) -> None:
        if self.player.is_running:
            self.player.stop()
        else:
            self.player.start()
        self._update_play_button_text()

    def _on_mode_toggled(self) -> None:
        mode = "beep" if self.radio_flash.isChecked() else "click"
        self.player.set_mode(mode)
        self._update_mode_description()

    def _on_bpm_changed(self, value: int) -> None:
        self.player.set_bpm(float(value))

    def _on_volume_changed(self, value: int) -> None:
        self.player.set_amplitude(value / 100.0)

    def _adjust_obs_offset(self, delta_ms: float) -> None:
        """Directly adjust current OBS audio sync offset from the verification window."""
        if not self.obs_client.is_connected or not self.current_obs_source:
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

    def update_device_and_source(self, device_idx: Optional[int], obs_source: Optional[str]) -> None:
        """Update hardware output device and OBS source target dynamically."""
        self.output_device_idx = device_idx
        self.current_obs_source = obs_source
        self.player.set_output_device(device_idx)
        self._refresh_obs_info()

    def closeEvent(self, event) -> None:
        """Ensure audio stream and animation timer stop cleanly when window is closed."""
        self.canvas.stop_timer()
        self.player.stop()
        super().closeEvent(event)
