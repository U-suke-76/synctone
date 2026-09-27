"""Waveform and cross-correlation visualization using pyqtgraph with LOD and high-performance rendering."""

from typing import Optional
import numpy as np
import scipy.signal
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QPushButton, QButtonGroup
)
from PySide6.QtGui import QColor, QBrush, QPen
from PySide6.QtCore import Qt

from synctone.core.chirp import DelayEstimateResult
from synctone.i18n import t


class SyncPlotWidget(QWidget):
    """Widget providing waveform overlay and cross-correlation peak plots with LOD rendering."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Performance: Disable CPU-heavy antialiasing globally for pyqtgraph
        pg.setConfigOptions(antialias=False)

        self._ref_signal: Optional[np.ndarray] = None
        self._rec_signal: Optional[np.ndarray] = None
        self._sample_rate: int = 48000

        # Full resolution cached normalized signals
        self._t_ref: Optional[np.ndarray] = None
        self._norm_ref: Optional[np.ndarray] = None
        self._t_rec: Optional[np.ndarray] = None
        self._norm_rec: Optional[np.ndarray] = None

        # Level-of-Detail (LOD) subsampled signals for ultra-fast full view (~2400 points)
        self._t_ref_lod: Optional[np.ndarray] = None
        self._norm_ref_lod: Optional[np.ndarray] = None
        self._t_rec_lod: Optional[np.ndarray] = None
        self._norm_rec_lod: Optional[np.ndarray] = None

        self._delay_samples: float = 0.0
        self._current_manual_offset_ms: float = 0.0
        self._latest_delay_ms: float = 0.0
        self._has_corr_data: bool = False
        # Default to Full view; user can freely switch to Zoom view
        self._is_zoomed_view: bool = False

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(10)

        # Controls bar above plots
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(4, 0, 4, 0)
        ctrl_layout.setSpacing(12)

        self.align_checkbox = QCheckBox()
        self.align_checkbox.setChecked(True)
        self.align_checkbox.toggled.connect(self._on_align_toggled)
        ctrl_layout.addWidget(self.align_checkbox)

        self.invert_checkbox = QCheckBox()
        self.invert_checkbox.toggled.connect(self._on_invert_toggled)
        ctrl_layout.addWidget(self.invert_checkbox)

        # View mode buttons (User freely switches between Full and Zoom views)
        self.btn_full_view = QPushButton()
        self.btn_full_view.setCheckable(True)
        self.btn_full_view.setChecked(True)
        self.btn_full_view.clicked.connect(self._set_full_view)
        ctrl_layout.addWidget(self.btn_full_view)

        self.btn_zoom_view = QPushButton()
        self.btn_zoom_view.setCheckable(True)
        self.btn_zoom_view.clicked.connect(self._set_zoom_view)
        ctrl_layout.addWidget(self.btn_zoom_view)

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.addButton(self.btn_full_view)
        self.view_btn_group.addButton(self.btn_zoom_view)
        self.view_btn_group.setExclusive(True)

        ctrl_layout.addStretch()

        self.legend_label = QLabel()
        ctrl_layout.addWidget(self.legend_label)
        layout.addLayout(ctrl_layout)

        # 1. Waveform Plot
        self.waveform_plot = pg.PlotWidget()
        self.waveform_plot.setBackground("#1a1a24")
        self.waveform_plot.showGrid(x=True, y=True, alpha=0.25)
        self.waveform_plot.setYRange(-1.15, 1.15)
        self.waveform_plot.setMinimumHeight(140)
        self.waveform_plot.plotItem.hideButtons()
        self.waveform_plot.getAxis('left').setWidth(44)
        self.waveform_plot.getAxis('bottom').setHeight(38)

        # Waveform curves (Solid colors + segmentedLineMode='on' for ultra-fast GPU/C++ line rendering)
        ref_pen = pg.mkPen(color=QColor(0, 229, 255, 255), width=1.5)
        rec_pen = pg.mkPen(color=QColor(255, 64, 129, 255), width=1.5)

        self.curve_ref = self.waveform_plot.plot(pen=ref_pen, name="基準音")
        self.curve_rec = self.waveform_plot.plot(pen=rec_pen, name="マイク音")

        if hasattr(self.curve_ref, "curve") and self.curve_ref.curve is not None:
            self.curve_ref.curve.setSegmentedLineMode('on')
        if hasattr(self.curve_rec, "curve") and self.curve_rec.curve is not None:
            self.curve_rec.curve.setSegmentedLineMode('on')

        # Start marker line (where chirp sweep begins at 0.1s)
        self.start_line = pg.InfiniteLine(
            pos=0.1, angle=90, movable=False,
            pen=pg.mkPen(color=QColor(255, 255, 255, 100), width=1, style=Qt.PenStyle.DashLine)
        )
        self.waveform_plot.addItem(self.start_line)

        layout.addWidget(self.waveform_plot, stretch=3)

        # 2. Cross-Correlation Plot
        self.corr_plot = pg.PlotWidget()
        self.corr_plot.setBackground("#1a1a24")
        self.corr_plot.showGrid(x=True, y=True, alpha=0.25)
        self.corr_plot.setMinimumHeight(125)
        self.corr_plot.plotItem.hideButtons()
        self.corr_plot.getAxis('left').setWidth(44)
        self.corr_plot.getAxis('bottom').setHeight(38)
        self.corr_plot.getAxis('left').enableAutoSIPrefix(False)
        self.corr_plot.setXRange(-50, 350)
        self.corr_plot.setYRange(0, 1.0)

        corr_pen = pg.mkPen(color=QColor(255, 202, 40, 255), width=2)
        corr_brush = pg.mkBrush(QColor(255, 202, 40, 45))
        self.curve_corr = self.corr_plot.plot(pen=corr_pen, fillLevel=0.0, brush=corr_brush)
        if hasattr(self.curve_corr, "curve") and self.curve_corr.curve is not None:
            self.curve_corr.curve.setSegmentedLineMode('on')

        # Peak indicator line (vertical dashed line)
        self.peak_line = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(color="#00e676", width=2, style=Qt.PenStyle.DashLine)
        )
        self.corr_plot.addItem(self.peak_line)
        self.peak_line.setVisible(False)

        # Peak marker circle at peak summit
        self.peak_scatter = pg.ScatterPlotItem(
            size=10, pen=pg.mkPen('#ffffff', width=2), brush=pg.mkBrush('#00e676'), symbol='o'
        )
        self.corr_plot.addItem(self.peak_scatter)
        self.peak_scatter.setVisible(False)

        # Peak label above summit
        self.peak_text = pg.TextItem(color='#00e676', anchor=(0.5, 1.3))
        self.corr_plot.addItem(self.peak_text)
        self.peak_text.setVisible(False)

        layout.addWidget(self.corr_plot, stretch=2)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Update texts and labels to match current language."""
        self.align_checkbox.setText(t("plot_align"))
        self.align_checkbox.setToolTip(t("plot_align_tooltip"))
        self.invert_checkbox.setText(t("plot_invert"))
        self.invert_checkbox.setToolTip(t("plot_invert_tooltip"))
        self.btn_full_view.setText(t("plot_full_view"))
        self.btn_full_view.setToolTip(t("plot_full_tooltip"))
        self.btn_zoom_view.setText(t("plot_zoom_view"))
        self.btn_zoom_view.setToolTip(t("plot_zoom_tooltip"))

        self.legend_label.setText(
            f"<span style='color:#00e5ff; font-weight:bold;'>{t('plot_legend_ref')}</span> &nbsp;&nbsp; "
            f"<span style='color:#ff4081; font-weight:bold;'>{t('plot_legend_rec')}</span>"
        )

        self.waveform_plot.setTitle(t("plot_waveform_title"))
        self.waveform_plot.setLabel("bottom", t("plot_waveform_xlabel"), units="s")
        self.waveform_plot.setLabel("left", t("plot_waveform_ylabel"))

        self.corr_plot.setTitle(t("plot_corr_title"))
        self.corr_plot.setLabel("bottom", t("plot_corr_xlabel"), units="ms")
        self.corr_plot.setLabel("left", t("plot_corr_ylabel"))

    def set_data(
        self,
        ref_signal: np.ndarray,
        rec_signal: np.ndarray,
        sample_rate: int,
        result: DelayEstimateResult,
        initial_offset_ms: float = 0.0,
    ) -> None:
        """Update plots with new measurement data."""
        self._ref_signal = ref_signal
        self._rec_signal = rec_signal
        self._sample_rate = sample_rate
        self._delay_samples = (initial_offset_ms / 1000.0) * sample_rate
        self._current_manual_offset_ms = initial_offset_ms

        # Cache full resolution time vectors & normalized signals
        self._t_ref = np.arange(len(ref_signal)) / sample_rate
        self._t_rec = np.arange(len(rec_signal)) / sample_rate

        max_ref = np.max(np.abs(ref_signal)) or 1.0
        self._norm_ref = ref_signal / max_ref

        global_max = np.max(np.abs(rec_signal)) or 1.0
        norm_rec = rec_signal / global_max
        if result.is_inverted:
            norm_rec = -norm_rec
        self._norm_rec = norm_rec

        # Precompute LOD Min/Max envelope arrays (~3000 points) to eliminate moiré/aliasing artifacts
        self._t_ref_lod, self._norm_ref_lod = self._compute_envelope(self._t_ref, self._norm_ref, target_bins=1500)
        self._t_rec_lod, self._norm_rec_lod = self._compute_envelope(self._t_rec, self._norm_rec, target_bins=1500)

        # Update polarity invert checkbox state
        self.invert_checkbox.blockSignals(True)
        self.invert_checkbox.setChecked(result.is_inverted)
        self.invert_checkbox.blockSignals(False)

        # 1. Update Cross-Correlation plot with analytic envelope (Hilbert transform)
        # The cross-correlation of wideband chirp is an impulse-like peak (width ~0.3ms).
        # Computing the analytic envelope reveals an obvious, beautiful mountain peak
        # with summit marker and delay badge, instead of an invisible subpixel line!
        if len(result.correlation) > 0 and len(result.lags) > 0:
            self._has_corr_data = True
            self._latest_delay_ms = result.delay_ms

            lags_ms = (result.lags / sample_rate) * 1000.0
            raw_corr = np.abs(result.correlation) if result.is_inverted else result.correlation

            # Region of Interest: from -50ms up to max(350ms, result.delay_ms + 250ms)
            max_roi_lag = max(350.0, result.delay_ms + 250.0)
            roi_mask = (lags_ms >= -50.0) & (lags_ms <= max_roi_lag)

            if np.any(roi_mask):
                plot_lags = lags_ms[roi_mask]
                sub_corr = raw_corr[roi_mask]
            else:
                plot_lags = lags_ms
                sub_corr = raw_corr

            # Compute analytic envelope
            corr_env = np.abs(scipy.signal.hilbert(sub_corr))

            self.curve_corr.setData(plot_lags, corr_env)

            # Summit peak marker
            peak_idx = int(np.argmax(corr_env))
            peak_x = float(plot_lags[peak_idx])
            peak_y = float(corr_env[peak_idx])

            self.peak_line.setPos(result.delay_ms)
            self.peak_line.setVisible(True)

            self.peak_scatter.setData(x=[peak_x], y=[peak_y])
            self.peak_scatter.setVisible(True)

            self.peak_text.setText(f"{result.delay_ms:.1f} ms")
            self.peak_text.setPos(peak_x, peak_y)
            self.peak_text.setVisible(True)

            # Fit Y-axis to the detected peak so the mountain is clearly visible and never flat
            peak_val = max(0.1, peak_y)
            min_val = min(0.0, float(np.min(corr_env)))
            self.corr_plot.setYRange(min(-0.02, min_val * 1.1), peak_val * 1.25)
        else:
            self._has_corr_data = False
            self.curve_corr.clear()
            self.peak_line.setVisible(False)
            self.peak_scatter.setVisible(False)
            self.peak_text.setVisible(False)

        # 2. Update waveform curves and viewport
        self._update_waveform_curves()

        if self._is_zoomed_view:
            self._apply_zoom_range()
        else:
            self._apply_full_range()

    def update_manual_offset(self, offset_ms: float) -> None:
        """Update waveform preview with user manual offset (~0.05ms execution time)."""
        self._current_manual_offset_ms = offset_ms
        self._delay_samples = (offset_ms / 1000.0) * self._sample_rate
        self._update_rec_curve_only()

    def _update_waveform_curves(self) -> None:
        """Update both reference and recorded curves based on current view mode and LOD."""
        if self._t_ref is None or self._norm_ref is None or self._t_rec is None or self._norm_rec is None:
            return

        shift_sec = (self._current_manual_offset_ms / 1000.0) if self.align_checkbox.isChecked() else 0.0

        if self._is_zoomed_view:
            # Zoom View: Use 100% full 48kHz resolution raw data across the entire signal
            # User can pan and zoom freely anywhere along the timeline with zero data cutoffs
            self.curve_ref.setData(self._t_ref, self._norm_ref)
            self.curve_rec.setData(self._t_rec - shift_sec, self._norm_rec)
        else:
            # Full View: Use precomputed ~3000-point Min/Max envelope arrays for moire-free representation
            self.curve_ref.setData(self._t_ref_lod, self._norm_ref_lod)
            self.curve_rec.setData(self._t_rec_lod - shift_sec, self._norm_rec_lod)

    def _update_rec_curve_only(self) -> None:
        """High-speed update of recorded curve only during manual slider/spinbox adjustments."""
        if self._t_rec is None or self._norm_rec is None:
            return

        shift_sec = (self._current_manual_offset_ms / 1000.0) if self.align_checkbox.isChecked() else 0.0

        if self._is_zoomed_view:
            self.curve_rec.setData(self._t_rec - shift_sec, self._norm_rec)
        else:
            self.curve_rec.setData(self._t_rec_lod - shift_sec, self._norm_rec_lod)

    @staticmethod
    def _compute_envelope(t_arr: np.ndarray, sig_arr: np.ndarray, target_bins: int = 1500) -> tuple[np.ndarray, np.ndarray]:
        """Compute min/max envelope to represent waveform without aliasing or moiré artifacts."""
        n = len(sig_arr)
        bin_size = max(1, n // target_bins)
        n_bins = n // bin_size
        if n_bins < 2:
            return t_arr, sig_arr

        trimmed_sig = sig_arr[:n_bins * bin_size].reshape(n_bins, bin_size)
        trimmed_t = t_arr[:n_bins * bin_size].reshape(n_bins, bin_size)

        mins = trimmed_sig.min(axis=1)
        maxs = trimmed_sig.max(axis=1)

        t_env = np.empty(n_bins * 2, dtype=t_arr.dtype)
        t_env[0::2] = trimmed_t[:, 0]
        t_env[1::2] = trimmed_t[:, -1]

        sig_env = np.empty(n_bins * 2, dtype=sig_arr.dtype)
        sig_env[0::2] = mins
        sig_env[1::2] = maxs
        return t_env, sig_env

    def _on_invert_toggled(self) -> None:
        """Re-invert polarity of recorded signal."""
        if self._rec_signal is None or self._t_rec is None:
            return
        global_max = np.max(np.abs(self._rec_signal)) or 1.0
        norm_rec = self._rec_signal / global_max
        if self.invert_checkbox.isChecked():
            norm_rec = -norm_rec
        self._norm_rec = norm_rec
        self._t_rec_lod, self._norm_rec_lod = self._compute_envelope(self._t_rec, self._norm_rec, target_bins=1500)
        self._update_waveform_curves()

    def _on_align_toggled(self) -> None:
        self.update_manual_offset(self._current_manual_offset_ms)

    def show_full_view(self) -> None:
        """Switch to full waveform view and update UI button."""
        self.btn_full_view.setChecked(True)
        self._set_full_view()

    def show_zoom_view(self) -> None:
        """Switch to zoomed waveform view and update UI button."""
        self.btn_zoom_view.setChecked(True)
        self._set_zoom_view()

    def _set_full_view(self) -> None:
        self._is_zoomed_view = False
        self._update_waveform_curves()
        self._apply_full_range()

    def _set_zoom_view(self) -> None:
        self._is_zoomed_view = True
        self._update_waveform_curves()
        self._apply_zoom_range()

    def _apply_full_range(self) -> None:
        if self._ref_signal is not None:
            total_sec = len(self._ref_signal) / self._sample_rate
            self.waveform_plot.setXRange(-0.05, total_sec + 0.1)
            self.waveform_plot.setYRange(-1.15, 1.15)
        if self._has_corr_data:
            max_x = max(350.0, self._latest_delay_ms + 200.0)
            self.corr_plot.setXRange(-50.0, max_x)

    def _apply_zoom_range(self) -> None:
        """Zoom in on the waveform sweep and zoom in directly on the correlation peak mountain."""
        self.waveform_plot.setXRange(0.110, 0.135)
        self.waveform_plot.setYRange(-1.15, 1.15)
        if self._has_corr_data:
            self.corr_plot.setXRange(self._latest_delay_ms - 25.0, self._latest_delay_ms + 25.0)
