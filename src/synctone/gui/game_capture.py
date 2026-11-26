"""Native Direct3D 11 SwapChain target window for OBS Game Capture."""

import ctypes
import os
import sys
from typing import Callable, Optional, Protocol

import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QExposeEvent, QImage, QKeyEvent, QResizeEvent, QWindow

from synctone.i18n import t


class SceneRenderer(Protocol):
    """Protocol for a canvas capable of rendering a frame onto a QPaintDevice."""

    def render_scene(self, paint_device, w: int, h: int) -> None: ...


if sys.platform == "win32":
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class _DXGI_ADAPTER_DESC1(ctypes.Structure):
        _fields_ = [
            ("Description", wintypes.WCHAR * 128),
            ("VendorId", wintypes.UINT),
            ("DeviceId", wintypes.UINT),
            ("SubSysId", wintypes.UINT),
            ("Revision", wintypes.UINT),
            ("DedicatedVideoMemory", ctypes.c_size_t),
            ("DedicatedSystemMemory", ctypes.c_size_t),
            ("SharedSystemMemory", ctypes.c_size_t),
            ("AdapterLuid", _LUID),
            ("Flags", wintypes.UINT),
        ]

    class _DXGI_RATIONAL(ctypes.Structure):
        _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]

    class _DXGI_MODE_DESC(ctypes.Structure):
        _fields_ = [
            ("Width", wintypes.UINT),
            ("Height", wintypes.UINT),
            ("RefreshRate", _DXGI_RATIONAL),
            ("Format", wintypes.UINT),
            ("ScanlineOrdering", wintypes.UINT),
            ("Scaling", wintypes.UINT),
        ]

    class _DXGI_SAMPLE_DESC(ctypes.Structure):
        _fields_ = [("Count", wintypes.UINT), ("Quality", wintypes.UINT)]

    class _DXGI_SWAP_CHAIN_DESC(ctypes.Structure):
        _fields_ = [
            ("BufferDesc", _DXGI_MODE_DESC),
            ("SampleDesc", _DXGI_SAMPLE_DESC),
            ("BufferUsage", wintypes.UINT),
            ("BufferCount", wintypes.UINT),
            ("OutputWindow", wintypes.HWND),
            ("Windowed", wintypes.BOOL),
            ("SwapEffect", wintypes.UINT),
            ("Flags", wintypes.UINT),
        ]

    _IID_IDXGIFactory1 = _GUID(0x770AAE78, 0xF26F, 0x4DBA, (0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    _IID_ID3D11Texture2D = _GUID(0x6F15AAF2, 0xD208, 0x4E89, (0x9A, 0xB4, 0x48, 0x95, 0x35, 0xD3, 0x4F, 0x9C))


class _D3D11Presenter:
    """Direct3D 11 SwapChain presenter bound explicitly to the highest-VRAM discrete GPU adapter."""

    def __init__(self, hwnd: int, width: int, height: int):
        self.width = max(64, int(width))
        self.height = max(64, int(height))
        self.hwnd = int(hwnd)
        self.swapchain = ctypes.c_void_p()
        self.device = ctypes.c_void_p()
        self.context = ctypes.c_void_p()
        self.backbuf = ctypes.c_void_p()
        self._present_fn = None
        self._get_buffer_fn = None
        self._resize_buffers_fn = None
        self._update_subresource_fn = None

        if sys.platform != "win32":
            return

        dxgi = ctypes.windll.dxgi
        d3d11 = ctypes.windll.d3d11

        factory = ctypes.c_void_p()
        if dxgi.CreateDXGIFactory1(ctypes.byref(_IID_IDXGIFactory1), ctypes.byref(factory)) != 0 or not factory.value:
            return

        best_adapter = self._select_best_adapter(factory)
        self._com_release(factory)

        scd = _DXGI_SWAP_CHAIN_DESC()
        scd.BufferDesc.Width = self.width
        scd.BufferDesc.Height = self.height
        scd.BufferDesc.RefreshRate = _DXGI_RATIONAL(60, 1)
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
        self._present_fn = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.UINT, wintypes.UINT
        )(sc_vt[8])
        self._get_buffer_fn = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)
        )(sc_vt[9])
        self._resize_buffers_fn = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        )(sc_vt[13])

        if self._get_buffer_fn(self.swapchain, 0, ctypes.byref(_IID_ID3D11Texture2D), ctypes.byref(self.backbuf)) != 0:
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

    @classmethod
    def _select_best_adapter(cls, factory: ctypes.c_void_p) -> ctypes.c_void_p:
        """Pick the hardware adapter with the largest dedicated VRAM."""
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
                ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_DXGI_ADAPTER_DESC1)
            )(avt[10])
            desc = _DXGI_ADAPTER_DESC1()
            if get_desc1(ad, ctypes.byref(desc)) == 0:
                # Skip software renderer (DXGI_ADAPTER_FLAG_SOFTWARE = 2) and pick largest DedicatedVideoMemory
                if (desc.Flags & 2) == 0 and int(desc.DedicatedVideoMemory) > best_vram:
                    if best_adapter.value:
                        cls._com_release(best_adapter)
                    best_vram = int(desc.DedicatedVideoMemory)
                    best_adapter = ad
                else:
                    cls._com_release(ad)
            else:
                cls._com_release(ad)
            idx += 1
        return best_adapter

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

    def resize(self, width: int, height: int) -> bool:
        """Resize the SwapChain backbuffer in-place without recreating the D3D11 device."""
        if not self.swapchain.value or not self._resize_buffers_fn or not self._get_buffer_fn:
            return False
        new_w = max(64, int(width))
        new_h = max(64, int(height))
        if new_w == self.width and new_h == self.height and self.backbuf.value:
            return True

        self._com_release(self.backbuf)
        hr = self._resize_buffers_fn(self.swapchain, 0, new_w, new_h, 0, 0)
        if hr != 0:
            return False
        if self._get_buffer_fn(self.swapchain, 0, ctypes.byref(_IID_ID3D11Texture2D), ctypes.byref(self.backbuf)) != 0:
            return False
        self.width = new_w
        self.height = new_h
        return True

    def present_buffer(self, data_ptr: int, row_pitch: int) -> None:
        """Upload a contiguous BGRA pixel buffer directly to the D3D11 backbuffer (zero-copy) and present."""
        if not self.is_valid:
            return
        self._update_subresource_fn(
            self.context,
            self.backbuf,
            0,
            None,
            ctypes.c_void_p(data_ptr),
            row_pitch,
            0,
        )
        self._present_fn(self.swapchain, 0, 0)

    def present_qimage(self, img: QImage) -> None:
        """Present a QImage without intermediate Python bytes copies."""
        if not self.is_valid:
            return
        mv = img.constBits()
        buf = (ctypes.c_char * len(mv)).from_buffer(mv)
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
        self._get_buffer_fn = None
        self._resize_buffers_fn = None
        self._update_subresource_fn = None


class GameCaptureTargetWindow(QWindow):
    """Top-level native D3D11 window bound to the discrete GPU so OBS Game Capture hooks without multi-adapter mode."""

    def __init__(self, canvas: SceneRenderer, on_toggle_play: Callable[[], None]):
        super().__init__()
        self._canvas = canvas
        self._on_toggle_play = on_toggle_play
        self.setTitle(t("verifier_game_capture_title"))
        self.resize(800, 360)
        self.setMinimumSize(QSize(480, 220))
        self._d3d: Optional[_D3D11Presenter] = None
        self._frame_array: Optional[np.ndarray] = None
        self._frame_image: Optional[QImage] = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._render_frame)
        self._timer.start()

    def pause_timer(self) -> None:
        """Pause rendering while keeping the HWND and D3D11 SwapChain alive for instant OBS re-capture."""
        if self._timer.isActive():
            self._timer.stop()

    def resume_timer(self) -> None:
        """Resume 60fps rendering on the existing HWND / D3D11 SwapChain."""
        if not self._timer.isActive():
            self._timer.start()
        if self.isVisible():
            self._render_frame()

    def stop_timer(self) -> None:
        """Fully stop rendering and release all D3D11 resources (called when parent verifier closes)."""
        if self._timer.isActive():
            self._timer.stop()
        if self._d3d is not None:
            self._d3d.release()
            self._d3d = None
        self._frame_image = None
        self._frame_array = None

    def _pixel_size(self) -> tuple[int, int]:
        dpr = max(1.0, float(self.devicePixelRatio()))
        return max(64, int(round(self.width() * dpr))), max(64, int(round(self.height() * dpr)))

    def _ensure_frame_buffer(self, pw: int, ph: int) -> None:
        """Ensure the persistent zero-copy NumPy + QImage shared buffer matches (pw, ph)."""
        if self._frame_array is None or self._frame_array.shape[:2] != (ph, pw):
            self._frame_array = np.zeros((ph, pw, 4), dtype=np.uint8)
            self._frame_image = QImage(
                self._frame_array.data,
                pw,
                ph,
                pw * 4,
                QImage.Format.Format_ARGB32,
            )

    def _ensure_d3d(self) -> Optional[_D3D11Presenter]:
        if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return None
        pw, ph = self._pixel_size()
        if self._d3d is not None:
            if not self._d3d.is_valid:
                self._d3d.release()
                self._d3d = None
            elif self._d3d.width != pw or self._d3d.height != ph:
                if not self._d3d.resize(pw, ph):
                    self._d3d.release()
                    self._d3d = None
        if self._d3d is None:
            try:
                self._d3d = _D3D11Presenter(int(self.winId()), pw, ph)
            except Exception:
                self._d3d = None
        if self._d3d and self._d3d.is_valid:
            self._ensure_frame_buffer(self._d3d.width, self._d3d.height)
            return self._d3d
        return None

    def _render_frame(self) -> None:
        if not self.isVisible():
            return
        d3d = self._ensure_d3d()
        if d3d is None or self._frame_image is None or self._frame_array is None:
            return
        self._canvas.render_scene(self._frame_image, d3d.width, d3d.height)
        d3d.present_buffer(self._frame_array.ctypes.data, d3d.width * 4)

    def exposeEvent(self, event: QExposeEvent) -> None:
        super().exposeEvent(event)
        if self.isExposed():
            self._render_frame()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self._render_frame()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._on_toggle_play()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.pause_timer()
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)
