"""Real-time AV Sync and Auditory Verification Window (AV Sync Checker)."""

import ctypes
import math
import os
import sys
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QRadioButton, QButtonGroup, QFrame, QSizePolicy,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QKeyEvent, QWindow, QImage, QResizeEvent, QExposeEvent

from synctone.core.av_analysis import AvOffsetResult
from synctone.core.verifier_audio import SyncAudioPlayer
from synctone.gui.workers import RecordingAnalysisWorker
from synctone.obs.client import ObsClient
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


class _D3D11Presenter:
    """Direct3D 11 SwapChain presenter bound explicitly to the highest-VRAM discrete GPU adapter."""

    def __init__(self, hwnd: int, width: int, height: int):
        from ctypes import wintypes

        self.width = max(64, int(width))
        self.height = max(64, int(height))
        self.hwnd = int(hwnd)
        self.swapchain = ctypes.c_void_p()
        self.device = ctypes.c_void_p()
        self.context = ctypes.c_void_p()
        self.backbuf = ctypes.c_void_p()
        self._present_fn = None
        self._update_subresource_fn = None

        dxgi = ctypes.windll.dxgi
        d3d11 = ctypes.windll.d3d11

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class DXGI_ADAPTER_DESC1(ctypes.Structure):
            _fields_ = [
                ("Description", wintypes.WCHAR * 128),
                ("VendorId", wintypes.UINT),
                ("DeviceId", wintypes.UINT),
                ("SubSysId", wintypes.UINT),
                ("Revision", wintypes.UINT),
                ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", LUID),
                ("Flags", wintypes.UINT),
            ]

        class DXGI_RATIONAL(ctypes.Structure):
            _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]

        class DXGI_MODE_DESC(ctypes.Structure):
            _fields_ = [
                ("Width", wintypes.UINT),
                ("Height", wintypes.UINT),
                ("RefreshRate", DXGI_RATIONAL),
                ("Format", wintypes.UINT),
                ("ScanlineOrdering", wintypes.UINT),
                ("Scaling", wintypes.UINT),
            ]

        class DXGI_SAMPLE_DESC(ctypes.Structure):
            _fields_ = [("Count", wintypes.UINT), ("Quality", wintypes.UINT)]

        class DXGI_SWAP_CHAIN_DESC(ctypes.Structure):
            _fields_ = [
                ("BufferDesc", DXGI_MODE_DESC),
                ("SampleDesc", DXGI_SAMPLE_DESC),
                ("BufferUsage", wintypes.UINT),
                ("BufferCount", wintypes.UINT),
                ("OutputWindow", wintypes.HWND),
                ("Windowed", wintypes.BOOL),
                ("SwapEffect", wintypes.UINT),
                ("Flags", wintypes.UINT),
            ]

        iid_factory1 = GUID(0x770AAE78, 0xF26F, 0x4DBA, (0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
        iid_tex2d = GUID(0x6F15AAF2, 0xD208, 0x4E89, (0x9A, 0xB4, 0x48, 0x95, 0x35, 0xD3, 0x4F, 0x9C))

        factory = ctypes.c_void_p()
        if dxgi.CreateDXGIFactory1(ctypes.byref(iid_factory1), ctypes.byref(factory)) != 0 or not factory.value:
            return

        fvt = ctypes.cast(ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        enum_adapters = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)
        )(fvt[12])

        best_adapter = ctypes.c_void_p()
        best_vram = -1
        idx = 0
        while True:
            ad = ctypes.c_void_p()
            if enum_adapters(factory, idx, ctypes.byref(ad)) != 0 or not ad.value:
                break
            avt = ctypes.cast(ctypes.cast(ad, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            get_desc1 = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(DXGI_ADAPTER_DESC1)
            )(avt[10])
            desc = DXGI_ADAPTER_DESC1()
            if get_desc1(ad, ctypes.byref(desc)) == 0:
                # Skip software renderer (DXGI_ADAPTER_FLAG_SOFTWARE = 2) and pick largest DedicatedVideoMemory
                if (desc.Flags & 2) == 0 and int(desc.DedicatedVideoMemory) > best_vram:
                    if best_adapter.value:
                        self._com_release(best_adapter)
                    best_vram = int(desc.DedicatedVideoMemory)
                    best_adapter = ad
                else:
                    self._com_release(ad)
            else:
                self._com_release(ad)
            idx += 1

        self._com_release(factory)

        scd = DXGI_SWAP_CHAIN_DESC()
        scd.BufferDesc.Width = self.width
        scd.BufferDesc.Height = self.height
        scd.BufferDesc.RefreshRate = DXGI_RATIONAL(60, 1)
        scd.BufferDesc.Format = 87  # DXGI_FORMAT_B8G8R8A8_UNORM (matches QImage Format_ARGB32 on little-endian)
        scd.SampleDesc.Count = 1
        scd.SampleDesc.Quality = 0
        scd.BufferUsage = 0x20  # DXGI_USAGE_RENDER_TARGET_OUTPUT
        scd.BufferCount = 1
        scd.OutputWindow = self.hwnd
        scd.Windowed = True
        scd.SwapEffect = 0  # DXGI_SWAP_EFFECT_DISCARD

        feature_level = wintypes.UINT()
        driver_type = 0 if best_adapter.value else 1  # UNKNOWN when adapter specified, else HARDWARE
        hr = d3d11.D3D11CreateDeviceAndSwapChain(
            best_adapter if best_adapter.value else None,
            driver_type,
            None,
            0,
            None,
            0,
            7,  # D3D11_SDK_VERSION
            ctypes.byref(scd),
            ctypes.byref(self.swapchain),
            ctypes.byref(self.device),
            ctypes.byref(feature_level),
            ctypes.byref(self.context),
        )
        if best_adapter.value:
            self._com_release(best_adapter)

        if hr != 0 or not self.swapchain.value or not self.context.value:
            self.release()
            return

        sc_vt = ctypes.cast(
            ctypes.cast(self.swapchain, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p)
        )
        get_buffer = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
        )(sc_vt[9])
        self._present_fn = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.UINT, wintypes.UINT
        )(sc_vt[8])

        if get_buffer(self.swapchain, 0, ctypes.byref(iid_tex2d), ctypes.byref(self.backbuf)) != 0:
            self.release()
            return

        ctx_vt = ctypes.cast(
            ctypes.cast(self.context, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p)
        )
        self._update_subresource_fn = ctypes.WINFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.UINT,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.UINT,
            wintypes.UINT,
        )(ctx_vt[48])

    @staticmethod
    def _com_release(ptr: ctypes.c_void_p) -> None:
        if ptr and ptr.value:
            vt = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            release_fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
            release_fn(ptr)
            ptr.value = None

    @property
    def is_valid(self) -> bool:
        return bool(self.swapchain.value and self.backbuf.value and self._present_fn and self._update_subresource_fn)

    def present_qimage(self, img: QImage) -> None:
        if not self.is_valid:
            return
        raw = img.constBits().tobytes()
        buf = (ctypes.c_char * len(raw)).from_buffer_copy(raw)
        self._update_subresource_fn(
            self.context,
            self.backbuf,
            0,
            None,
            ctypes.byref(buf),
            img.bytesPerLine(),
            0,
        )
        self._present_fn(self.swapchain, 0, 0)

    def release(self) -> None:
        self._com_release(self.backbuf)
        self._com_release(self.context)
        self._com_release(self.device)
        self._com_release(self.swapchain)
        self._present_fn = None
        self._update_subresource_fn = None


class GameCaptureTargetWindow(QWindow):
    """Top-level native D3D11 window bound to the discrete GPU so OBS Game Capture hooks without multi-adapter mode."""

    def __init__(self, canvas: SyncCanvas, on_toggle_play: Callable[[], None]):
        super().__init__()
        self._canvas = canvas
        self._on_toggle_play = on_toggle_play
        self.setTitle(t("verifier_game_capture_title"))
        self.resize(800, 360)
        self.setMinimumSize(QSize(480, 220))
        self._d3d: Optional[_D3D11Presenter] = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._render_frame)
        self._timer.start()

    def stop_timer(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if self._d3d is not None:
            self._d3d.release()
            self._d3d = None

    def _pixel_size(self) -> tuple[int, int]:
        dpr = max(1.0, float(self.devicePixelRatio()))
        return max(64, int(round(self.width() * dpr))), max(64, int(round(self.height() * dpr)))

    def _ensure_d3d(self) -> Optional[_D3D11Presenter]:
        if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return None
        pw, ph = self._pixel_size()
        if self._d3d is not None and (self._d3d.width != pw or self._d3d.height != ph or not self._d3d.is_valid):
            self._d3d.release()
            self._d3d = None
        if self._d3d is None:
            try:
                self._d3d = _D3D11Presenter(int(self.winId()), pw, ph)
            except Exception:
                self._d3d = None
        return self._d3d if (self._d3d and self._d3d.is_valid) else None

    def _render_frame(self) -> None:
        if not self.isVisible():
            return
        d3d = self._ensure_d3d()
        if d3d is None:
            return
        img = QImage(d3d.width, d3d.height, QImage.Format.Format_ARGB32)
        self._canvas.render_scene(img, d3d.width, d3d.height)
        d3d.present_qimage(img)

    def exposeEvent(self, event: QExposeEvent) -> None:
        super().exposeEvent(event)
        if self.isExposed():
            self._render_frame()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._d3d is not None:
            self._d3d.release()
            self._d3d = None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._on_toggle_play()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)


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
            QFrame#obs_hint_banner QLabel,
            QFrame#ctrl_panel QLabel, QFrame#ctrl_panel QRadioButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QFrame#obs_trim_frame {
                background: transparent;
                border: none;
                border-top: 1px solid #28283a;
                padding-top: 6px;
            }
            QPushButton#trim_btn {
                padding: 5px 6px;
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
                border-radius: 7px;
                border: 2px solid #666680;
                background-color: #181824;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #00e5ff;
                background-color: #00e5ff;
            }
            QMessageBox QPushButton {
                min-width: 72px;
                padding: 6px 14px;
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
        if not self.obs_client.is_connected:
            self.label_obs_info.setText(t("verifier_obs_not_connected"))
            self.obs_trim_frame.setEnabled(False)
            return

        # Prefer video source (render delay) when available so audio-to-mic sync is preserved
        if self.current_obs_video_source:
            self.obs_trim_frame.setEnabled(True)
            try:
                cur_delay = self.obs_client.get_render_delay(self.current_obs_video_source)
                self.label_obs_info.setText(
                    f"{t('verifier_target_source', name=self.current_obs_video_source)} | {t('verifier_obs_current', offset=cur_delay)}"
                )
            except Exception:
                self.label_obs_info.setText(t("verifier_obs_not_connected"))
            return

        if not self.current_obs_source:
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
                new_vid = max(0, min(500, raw_target))
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
                new_val = max(0, min(500, int(round(cur + delta_ms))))
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
