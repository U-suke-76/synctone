"""Tests for GUI initialization and basic behavior using offscreen platform."""

import os
import pytest
from PySide6.QtWidgets import QApplication

# Set offscreen platform for headless test
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def reset_language():
    """Ensure each test runs with a clean Japanese language baseline."""
    from PySide6.QtCore import QSettings
    from synctone.i18n import I18nManager
    settings = QSettings("SyncTone", "SyncTone")
    settings.setValue("app/language", "ja")
    I18nManager.get_instance().current_lang = "ja"
    yield
    settings.setValue("app/language", "ja")
    I18nManager.get_instance().current_lang = "ja"


def test_main_window_init(qapp):
    """Verify MainWindow initializes cleanly without raising exceptions."""
    from synctone.gui.main_window import MainWindow

    window = MainWindow()
    assert window.windowTitle().startswith("SyncTone")
    assert window.obs_client is not None
    assert window.analyzer is not None
    assert window.plot_widget is not None

    # Test slider and spinbox sync (0.1ms resolution)
    window.spin_offset.setValue(75.5)
    assert window.slider_offset.value() == 755

    window.slider_offset.setValue(1200)
    assert window.spin_offset.value() == 120.0

    # Test volume slider affects analyzer amplitude
    window.vol_slider.setValue(80)
    assert window.analyzer.amplitude == 0.8
    assert window.vol_label.text() == "80%"

    # Test measurement mode combo (3 modes: 3-run, 1-run, 5-run)
    assert window.combo_measure_mode.count() == 3
    assert window.combo_measure_mode.itemData(0) == 3  # 3-run mode (default)
    assert window.combo_measure_mode.itemData(1) == 1  # 1-run mode
    assert window.combo_measure_mode.itemData(2) == 5  # 5-run mode

    window.close()


def test_plot_widget_perf_and_offset(qapp):
    """Verify SyncPlotWidget handles large datasets with instant O(1) manual offset shifts."""
    import time
    import numpy as np
    from synctone.gui.plot_widget import SyncPlotWidget
    from synctone.core.chirp import DelayEstimateResult

    widget = SyncPlotWidget()

    # 1.5 seconds of audio at 48kHz = 72,000 samples
    sr = 48000
    n_samples = 72000
    ref_signal = np.random.randn(n_samples).astype(np.float32)
    rec_signal = np.random.randn(n_samples).astype(np.float32)

    dummy_result = DelayEstimateResult(
        delay_ms=111.3,
        delay_samples=5342.4,
        confidence=0.95,
        peak_correlation=0.95,
        correlation=np.array([0.1, 0.5, 0.95, 0.5, 0.1]),
        lags=np.array([5340, 5341, 5342, 5343, 5344]),
        is_inverted=False,
    )

    # Initial set_data (defaults to 0.0ms uncorrected state)
    widget.set_data(ref_signal, rec_signal, sr, dummy_result)
    x_data, _ = widget.curve_rec.getData()
    assert x_data[0] == pytest.approx(0.0, abs=1e-5)

    # Apply manual offset 111.3ms
    widget.update_manual_offset(111.3)
    x_data, _ = widget.curve_rec.getData()
    assert x_data[0] == pytest.approx(-0.1113, abs=1e-5)

    # Measure performance of 100 consecutive manual offset updates (simulating fast slider dragging)
    t0 = time.perf_counter()
    for offset in np.linspace(100.0, 150.0, 100):
        widget.update_manual_offset(float(offset))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 100 calls should take well under 100ms (typically ~18ms with cached setData)
    assert elapsed_ms < 100.0, f"Manual offset updating took too long: {elapsed_ms:.2f}ms"
    x_data, _ = widget.curve_rec.getData()
    assert x_data[0] == pytest.approx(-0.150, abs=1e-5)

    # Test alignment toggle
    widget.align_checkbox.setChecked(False)
    x_data, _ = widget.curve_rec.getData()
    assert x_data[0] == pytest.approx(0.0, abs=1e-5)
    widget.align_checkbox.setChecked(True)
    x_data, _ = widget.curve_rec.getData()
    assert x_data[0] == pytest.approx(-0.150, abs=1e-5)

    # Test invert toggle
    widget.invert_checkbox.setChecked(True)

    # Test view toggles
    widget.btn_full_view.click()
    assert not widget._is_zoomed_view
    widget.btn_zoom_view.click()
    assert widget._is_zoomed_view

    widget.close()


def test_plot_widget_compute_envelope():
    """Verify Min/Max envelope preserves signal envelope without moire attenuation."""
    import numpy as np
    from synctone.gui.plot_widget import SyncPlotWidget

    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # High frequency wave (1200Hz)
    sig = np.sin(2 * np.pi * 1200 * t)
    t_env, sig_env = SyncPlotWidget._compute_envelope(t, sig, target_bins=1500)

    assert len(t_env) == 3000
    assert len(sig_env) == 3000
    assert t_env[0] == 0.0
    assert np.all(np.diff(t_env) >= 0)  # monotonic
    # In min/max envelope, every bin retains full amplitude [-1, 1] without pinch
    assert sig_env.max() > 0.99
    assert sig_env.min() < -0.99



def test_main_window_apply_measured(qapp):
    """Verify MainWindow initializes at 0ms and applies measured delay via button."""
    import numpy as np
    from synctone.gui.main_window import MainWindow
    from synctone.core.chirp import MultiMeasureResult, DelayEstimateResult

    win = MainWindow()
    assert win.spin_offset.value() == 0.0
    assert not win.btn_apply_measured.isEnabled()

    dummy_single = DelayEstimateResult(
        delay_ms=111.4,
        delay_samples=5347.2,
        confidence=0.98,
        peak_correlation=0.98,
        correlation=np.array([0.1, 0.98, 0.1]),
        lags=np.array([5346, 5347, 5348]),
        is_inverted=False,
    )
    dummy_multi = MultiMeasureResult(
        individual_results=[dummy_single],
        median_delay_ms=111.4,
        mean_delay_ms=111.4,
        jitter_ms=0.0,
        overall_confidence=0.98,
        best_index=0,
        best_result=dummy_single,
    )

    # Simulate measurement finish
    dummy_recorded = np.zeros(72000, dtype=np.float32)
    win._on_measurement_finished(dummy_multi, dummy_recorded)

    # Manual offset should stay 0.0ms initially (raw delay view)
    assert win.spin_offset.value() == 0.0
    assert win.btn_apply_measured.isEnabled()
    assert "111.4" in win.btn_apply_measured.text()
    # View mode should remain as the user left it (default: full view)
    assert not win.plot_widget._is_zoomed_view

    # Click reflect button
    win.btn_apply_measured.click()
    assert win.spin_offset.value() == 111.4
    assert win.slider_offset.value() == 1114
    # View mode should STILL not change automatically!
    assert not win.plot_widget._is_zoomed_view

    # User manually switches to zoom view
    win.plot_widget.btn_zoom_view.click()
    assert win.plot_widget._is_zoomed_view

    # Click reset to 0ms button
    win.btn_reset_zero.click()
    assert win.spin_offset.value() == 0.0
    # User's choice of zoom view is preserved!
    assert win.plot_widget._is_zoomed_view

    # Click reflect button again so _has_applied_measured is True
    win.btn_apply_measured.click()
    assert win.spin_offset.value() == 111.4

    # Now simulate a second measurement (e.g., verifying delay after OBS or adjustment)
    dummy_second_single = DelayEstimateResult(
        delay_ms=111.3,
        delay_samples=5342.4,
        confidence=0.99,
        peak_correlation=0.99,
        correlation=np.array([0.1, 0.99, 0.1]),
        lags=np.array([5341, 5342, 5343]),
        is_inverted=False,
    )
    dummy_second_multi = MultiMeasureResult(
        individual_results=[dummy_second_single],
        median_delay_ms=111.3,
        mean_delay_ms=111.3,
        jitter_ms=0.0,
        overall_confidence=0.99,
        best_index=0,
        best_result=dummy_second_single,
    )
    win._on_measurement_finished(dummy_second_multi, dummy_recorded)

    # Since it was already applied, it MUST NOT reset to 0ms! It should auto-apply 111.3ms!
    assert win.spin_offset.value() == 111.3
    assert win.slider_offset.value() == 1113
    # And user's chosen view (zoom view) is preserved!
    assert win.plot_widget._is_zoomed_view
    assert "反映済み" in win.btn_apply_measured.text()

    win.close()


def test_obs_fetch_and_diff_flow(qapp, monkeypatch):
    """Verify OBS fetch button and real-time offset difference calculation."""
    from unittest.mock import MagicMock
    from synctone.gui.main_window import MainWindow
    from synctone.obs.client import ObsAudioSource

    win = MainWindow()

    # Mock connected OBS client
    mock_source = ObsAudioSource(name="デスクトップ音声", kind="wasapi_output_capture", sync_offset_ms=50)
    win.obs_client._client = MagicMock()
    monkeypatch.setattr(win.obs_client, "get_audio_sources", lambda: [mock_source])
    monkeypatch.setattr(win.obs_client, "get_sync_offset", lambda name: mock_source.sync_offset_ms)

    # Reload sources
    win._reload_obs_sources()
    assert win.btn_fetch_obs.isEnabled()
    assert win.apply_btn.isEnabled()
    assert "50 ms" in win.current_offset_label.text()

    # Simulate manual adjustment set to 111.4ms (measured delay)
    win._last_measured_delay_ms = 111.4
    win.spin_offset.setValue(111.4)
    assert "+61.4 ms" in win.diff_offset_label.text()

    # Simulate OBS source updated to 60ms externally, then user clicks fetch button
    mock_source.sync_offset_ms = 60
    win.btn_fetch_obs.click()
    assert "60 ms" in win.current_offset_label.text()
    # Fetching from OBS now immediately applies to manual trim spinbox for visual alignment preview
    assert win.spin_offset.value() == 60.0
    assert win.btn_apply_obs.isEnabled()
    assert "60 ms" in win.btn_apply_obs.text()
    assert "完全一致中" in win.diff_offset_label.text()

    # Simulate user changing spinbox to test delay (111.4ms)
    win.spin_offset.setValue(111.4)
    assert "+51.4 ms" in win.diff_offset_label.text()

    # User clicks btn_apply_obs to quickly switch back to OBS value
    win.btn_apply_obs.click()
    assert win.spin_offset.value() == 60.0
    assert "完全一致中" in win.diff_offset_label.text()

    # User clicks btn_reset_zero to quickly switch to uncorrected raw delay
    win.btn_reset_zero.click()
    assert win.spin_offset.value() == 0.0

    win.close()


def test_multilingual_switching(qapp):
    """Verify dynamic language switching between Japanese, English, Korean, Traditional Chinese, and Simplified Chinese."""
    from synctone.gui.main_window import MainWindow
    from synctone.i18n import I18nManager

    win = MainWindow()

    # Initial check: 5 languages in specified order
    assert win.combo_language.count() == 5
    assert win.combo_language.itemText(0) == "日本語"
    assert win.combo_language.itemText(1) == "English"
    assert win.combo_language.itemText(2) == "한국어"
    assert win.combo_language.itemText(3) == "繁體中文"
    assert win.combo_language.itemText(4) == "简体中文"

    # Switch to English (index 1)
    win.combo_language.setCurrentIndex(1)
    assert I18nManager.get_instance().current_lang == "en"
    assert win.windowTitle() == "SyncTone - OBS Audio Sync Assistant"
    assert win.obs_connect_btn.text() == "Connect to OBS"
    assert win.measure_btn.text().startswith("Start Measurement")
    assert win.label_manual_trim.text() == "Offset Trim:"
    assert win.btn_reset_zero.text() == "0ms (Raw)"
    assert win.btn_apply_obs.text() == "📥 OBS Value (--)"
    assert win.plot_widget.align_checkbox.text() == "Alignment Preview (Shifted)"
    assert win.plot_widget.btn_zoom_view.text() == "🔍 Zoom View (Peak Alignment)"
    assert win.combo_measure_mode.itemText(0).startswith("3 Measurements")

    # Switch to Korean (index 2)
    win.combo_language.setCurrentIndex(2)
    assert I18nManager.get_instance().current_lang == "ko"
    assert win.windowTitle() == "SyncTone - OBS 오디오 싱크 어시스턴트"
    assert win.obs_connect_btn.text() == "OBS에 연결"
    assert win.measure_btn.text().startswith("측정 시작")
    assert win.label_manual_trim.text() == "오프셋 미세조정:"
    assert win.btn_reset_zero.text() == "0ms (생지연)"
    assert win.btn_apply_obs.text() == "📥 OBS 설정값 (--)"
    assert win.plot_widget.align_checkbox.text() == "보정 미리보기 (겹치기)"
    assert win.plot_widget.btn_zoom_view.text() == "🔍 확대 보기 (피크 확인)"
    assert win.combo_measure_mode.itemText(0).startswith("3회 측정")

    # Switch to Traditional Chinese (index 3)
    win.combo_language.setCurrentIndex(3)
    assert I18nManager.get_instance().current_lang == "zh_TW"
    assert win.windowTitle() == "SyncTone - OBS 音訊同步小助手"
    assert win.obs_connect_btn.text() == "連線至 OBS"
    assert win.measure_btn.text().startswith("開始測量")
    assert win.label_manual_trim.text() == "位移微調:"
    assert win.btn_reset_zero.text() == "0ms (原始延遲)"
    assert win.btn_apply_obs.text() == "📥 OBS 設定值 (--)"
    assert win.plot_widget.align_checkbox.text() == "修正預覽 (重疊波形)"
    assert win.plot_widget.btn_zoom_view.text() == "🔍 放大檢視 (確認波峰波谷)"
    assert win.combo_measure_mode.itemText(0).startswith("3次測量")

    # Switch to Simplified Chinese (index 4)
    win.combo_language.setCurrentIndex(4)
    assert I18nManager.get_instance().current_lang == "zh_CN"
    assert win.windowTitle() == "SyncTone - OBS 音频同步助手"
    assert win.obs_connect_btn.text() == "连接 OBS"
    assert win.measure_btn.text().startswith("开始测量")
    assert win.label_manual_trim.text() == "偏移微调:"
    assert win.btn_reset_zero.text() == "0ms (原始延迟)"
    assert win.btn_apply_obs.text() == "📥 OBS 设置值 (--)"
    assert win.plot_widget.align_checkbox.text() == "修正预览 (重叠波形)"
    assert win.plot_widget.btn_zoom_view.text() == "🔍 放大视图 (确认波峰对齐)"
    assert win.combo_measure_mode.itemText(0).startswith("3次测量")

    # Switch back to Japanese (index 0)
    win.combo_language.setCurrentIndex(0)
    assert I18nManager.get_instance().current_lang == "ja"
    assert win.windowTitle() == "SyncTone - OBS音声同期アシスタント"
    assert win.obs_connect_btn.text() == "OBSに接続"
    assert win.measure_btn.text().startswith("測定開始")
    assert win.label_manual_trim.text() == "オフセット微調整:"
    assert win.btn_reset_zero.text() == "0ms (生遅延)"
    assert win.btn_apply_obs.text() == "📥 OBS現在値 (--)"
    assert win.plot_widget.align_checkbox.text() == "補正プレビュー (重ね合わせ)"
    assert win.plot_widget.btn_zoom_view.text() == "🔍 拡大表示 (山谷確認)"

    win.close()


def test_video_sync_gui_flow(qapp):
    """Verify video sync checkbox toggles visibility and apply flow updates both audio and video."""
    from unittest.mock import MagicMock, patch
    from synctone.gui.main_window import MainWindow
    from synctone.obs.client import ObsAudioSource, ObsVideoSource
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow()

    # Initial state
    assert not win.check_sync_video.isChecked()
    assert win.video_container.isHidden()

    # Toggle checkbox
    win.check_sync_video.setChecked(True)
    assert not win.video_container.isHidden()

    win.check_sync_video.setChecked(False)
    assert win.video_container.isHidden()

    # Setup mocked OBS sources
    win.obs_client._client = MagicMock()
    win.obs_sources = [
        ObsAudioSource(name="Desktop Audio", kind="wasapi_output_capture", sync_offset_ms=0)
    ]
    win.obs_video_sources = [
        ObsVideoSource(name="Game Capture HD", kind="game_capture", render_delay_ms=0)
    ]

    win.combo_obs_source.clear()
    win.combo_obs_source.addItem("Desktop Audio [0 ms]", win.obs_sources[0])
    win.combo_obs_source.setEnabled(True)

    win.combo_obs_video_source.clear()
    win.combo_obs_video_source.addItem("Game Capture HD [0 ms]", win.obs_video_sources[0])
    win.combo_obs_video_source.setEnabled(True)

    win.spin_offset.setValue(180.0)
    win.check_sync_video.setChecked(True)

    with patch.object(win.obs_client, "set_sync_offset") as mock_set_audio, \
         patch.object(win.obs_client, "set_render_delay", return_value=180) as mock_set_video, \
         patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "information"):

        win._apply_offset_to_obs()

        mock_set_audio.assert_called_with("Desktop Audio", 180)
        mock_set_video.assert_called_with("Game Capture HD", 180)
        assert win.obs_video_sources[0].render_delay_ms == 180
        assert "180" in win.combo_obs_video_source.currentText()

    win.close()



