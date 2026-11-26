"""Unit and integration tests for AV Sync Verification (SyncAudioPlayer, SyncCanvas, SyncVerifierWindow)."""

import os
from unittest.mock import MagicMock
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QKeyEvent

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SYNCTONE_TEST_DUMMY_AUDIO"] = "1"


@pytest.fixture(autouse=True)
def reset_language():
    from synctone.i18n import I18nManager
    settings = QSettings("SyncTone", "SyncTone")
    settings.setValue("app/language", "ja")
    I18nManager.get_instance().current_lang = "ja"
    yield
    settings.setValue("app/language", "ja")
    I18nManager.get_instance().current_lang = "ja"


def test_audio_sound_generators():
    """Verify beep tone generator produces valid normalized signals."""
    from synctone.core.verifier_audio import generate_beep_sound

    beep = generate_beep_sound(sample_rate=48000, duration=0.04, freq=1760.0, amplitude=0.5)
    assert isinstance(beep, np.ndarray)
    assert len(beep) == int(48000 * 0.04)
    assert not np.isnan(beep).any()
    assert np.max(np.abs(beep)) <= 0.5 + 1e-4


def test_sync_audio_player_logic():
    """Verify SyncAudioPlayer parameter adjustments, callback streaming, and phase tracking."""
    from synctone.core.verifier_audio import SyncAudioPlayer

    # Use dummy_mode=True to bypass hardware PortAudio in test suite
    player = SyncAudioPlayer(sample_rate=48000, bpm=120.0, amplitude=0.5, dummy_mode=True)
    assert player.bpm == 120.0
    assert player.amplitude == 0.5
    assert not player.is_running

    # Tempo update & clamping
    player.set_bpm(150.0)
    assert player.bpm == 150.0
    player.set_bpm(10.0)  # should clamp to 40
    assert player.bpm == 40.0
    player.set_bpm(300.0)  # should clamp to 240
    assert player.bpm == 240.0

    # Volume update
    player.set_amplitude(0.8)
    assert player.amplitude == 0.8

    # Start playback (in dummy mode, uses wall-clock fallback)
    player.start()
    assert player.is_running

    phase = player.get_phase()
    assert -0.5 <= phase <= 0.5

    # Simulate audio callback buffer rendering directly
    outdata = np.zeros((512, 2), dtype=np.float32)
    player._audio_callback(outdata, 512, None, None)
    assert outdata.shape == (512, 2)
    assert not np.isnan(outdata).any()

    player.stop()
    assert not player.is_running


def test_sync_canvas_render(qapp):
    """Verify SyncCanvas rendering in both beep and click modes without exceptions."""
    from synctone.core.verifier_audio import SyncAudioPlayer
    from synctone.gui.verifier_window import SyncCanvas

    player = SyncAudioPlayer(sample_rate=48000, bpm=120.0, dummy_mode=True)
    canvas = SyncCanvas(player)
    canvas.resize(600, 300)

    # Idle render
    canvas.repaint()

    # Active render (forces paintEvent with drawPolygon)
    from PySide6.QtGui import QPaintEvent
    from PySide6.QtCore import QRect
    player.start()
    event = QPaintEvent(QRect(0, 0, 600, 300))
    canvas.paintEvent(event)

    player.stop()
    canvas.stop_timer()
    canvas.close()
    canvas.deleteLater()
    qapp.processEvents()


def test_sync_verifier_window_interactions(qapp):
    """Verify SyncVerifierWindow GUI controls, keyboard shortcut, and OBS trim buttons."""
    from synctone.gui.verifier_window import SyncVerifierWindow
    from synctone.obs.client import ObsClient

    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_sync_offset.return_value = 140

    offset_changed_records = []

    def on_offset_changed(val: float):
        offset_changed_records.append(val)

    window = SyncVerifierWindow(
        obs_client=mock_obs,
        output_device_idx=0,
        current_obs_source="BGM Source",
        on_offset_changed_cb=on_offset_changed,
        dummy_mode=True,
    )
    window.show()

    # Initial state
    assert window.windowTitle().startswith("SyncTone")
    assert not window.player.is_running

    # Play toggle via button
    window.btn_play.click()
    assert window.player.is_running

    # Space key toggle to stop
    space_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    window.keyPressEvent(space_event)
    assert not window.player.is_running

    # Tempo spinbox change
    window.spin_bpm.setValue(100)
    assert window.player.bpm == 100.0

    # Volume slider change
    window.slider_volume.setValue(70)
    assert abs(window.player.amplitude - 0.7) < 1e-4

    # OBS trim buttons (+1ms, -5ms, +20ms, etc.)
    window._adjust_obs_offset(1.0)
    mock_obs.set_sync_offset.assert_called_with("BGM Source", 141)
    assert offset_changed_records[-1] == 141.0

    window._adjust_obs_offset(-5.0)
    mock_obs.set_sync_offset.assert_called_with("BGM Source", 135)
    assert offset_changed_records[-1] == 135.0

    # Direct numeric input via OBS delay spinbox
    window.spin_obs_delay.setValue(180)
    window._on_obs_delay_spin_finished()
    mock_obs.set_sync_offset.assert_called_with("BGM Source", 180)
    assert offset_changed_records[-1] == 180.0

    # Multilingual retranslate test
    from synctone.i18n import I18nManager
    I18nManager.get_instance().current_lang = "en"
    window.retranslate_ui()
    assert "AV Sync" in window.windowTitle()

    window.close()
    window.deleteLater()
    qapp.processEvents()
    assert not window.player.is_running


def test_main_window_verifier_integration(qapp):
    """Verify MainWindow integrates AV Sync button and opens/synchronizes the verifier window."""
    from synctone.gui.main_window import MainWindow

    main_win = MainWindow()
    main_win.show()
    assert hasattr(main_win, "btn_open_verifier")
    assert main_win.btn_open_verifier.isVisible()

    # Click to open verifier window
    main_win.btn_open_verifier.click()
    assert main_win.verifier_window is not None
    assert main_win.verifier_window.isVisible()

    # Re-clicking should focus existing window rather than creating a duplicate
    old_inst = main_win.verifier_window
    main_win.btn_open_verifier.click()
    assert main_win.verifier_window is old_inst

    # Test callback updating MainWindow's manual trim spinbox and slider
    main_win._on_verifier_offset_changed(88.0)
    assert main_win.spin_offset.value() == 88.0
    assert main_win.slider_offset.value() == 880

    main_win.close()
    main_win.deleteLater()
    qapp.processEvents()


def test_clock_phase_follows_callback_history(monkeypatch):
    """get_clock_phase() labels 'now' with sub-ms accuracy even when callbacks are bursty."""
    from synctone.core import verifier_audio
    from synctone.core.verifier_audio import SyncAudioPlayer

    player = SyncAudioPlayer(sample_rate=48000, bpm=110.0, dummy_mode=True)
    player._is_running = True
    player._use_fallback = False
    cycle_sec = player._cycle_samples / 48000.0
    rate = 1.0 / cycle_sec

    # Callbacks every ~10.7 ms with +-3 ms scheduling jitter; counter advances in whole blocks
    rng = np.random.default_rng(0)
    base = 1000.0
    u0 = 0.37  # cycles
    block_sec = 512 / 48000.0
    for k in range(48):
        ideal = base + k * block_sec
        player._clock_hist.append((ideal + rng.uniform(-0.003, 0.003), u0 + rate * (k * block_sec + 0.05)))

    now = base + 47 * block_sec + 0.004
    monkeypatch.setattr(verifier_audio.time, "perf_counter", lambda: now)
    expected = (u0 + rate * (47 * block_sec + 0.004 + 0.05)) % 1.0
    got = player.get_clock_phase()
    err_ms = abs((got - expected + 0.5) % 1.0 - 0.5) * cycle_sec * 1000.0
    assert err_ms < 1.0


def test_clock_phase_idle_and_fallback(monkeypatch):
    from synctone.core import verifier_audio
    from synctone.core.verifier_audio import SyncAudioPlayer

    player = SyncAudioPlayer(sample_rate=48000, bpm=120.0, dummy_mode=True)
    assert player.get_clock_phase() == 0.0  # not running

    monkeypatch.setattr(verifier_audio.time, "perf_counter", lambda: 50.0)
    player.start()  # dummy mode: wall-clock fallback, started at t=50.0
    monkeypatch.setattr(verifier_audio.time, "perf_counter", lambda: 50.0 + 0.125)
    assert player.get_clock_phase() == pytest.approx(0.25, abs=1e-6)  # 120 BPM: 0.5 s cycle
    player.stop()


def test_callback_records_clock_history():
    from synctone.core.verifier_audio import SyncAudioPlayer

    player = SyncAudioPlayer(sample_rate=48000, bpm=120.0, dummy_mode=True)
    outdata = np.zeros((512, 2), dtype=np.float32)
    for _ in range(5):
        player._audio_callback(outdata, 512, None, None)
    hist = list(player._clock_hist)
    assert len(hist) == 5
    cycles = [u for _, u in hist]
    assert cycles == sorted(cycles)
    assert cycles[-1] == pytest.approx(5 * 512 / player._cycle_samples)


def test_unified_canvas_draws_bar_and_game_capture_window(qapp):
    """Unified canvas draws a high-contrast sweeping bar at center + phase * (w - 60) and supports GameCapture."""
    from synctone.gui.verifier_window import SyncVerifierWindow
    from synctone.obs.client import ObsClient

    win = SyncVerifierWindow(obs_client=ObsClient(), dummy_mode=True)
    try:
        win.show()
        win.player._is_running = True
        win.player.get_phase = lambda: 0.25
        img = win.canvas.grab().toImage()
        y = int(img.height() * 0.55)
        xs = np.arange(img.width(), dtype=np.float64)
        # Bright pink/white bar stands out strongly in the red channel
        red = np.array([img.pixelColor(int(x), y).red() for x in xs], dtype=np.float64)
        peak_x = float(xs[red == red.max()].mean())
        expected = img.width() / 2.0 + 0.25 * (img.width() - 60)
        assert abs(peak_x - expected) < 2.0

        # Verify opening GameCaptureTargetWindow works without error
        win.btn_game_capture.click()
        assert win.game_capture_window is not None
        assert win.game_capture_window.minimumSize().width() == 480
        assert win.game_capture_window.minimumSize().height() == 220

        # Verify zero-copy shared NumPy + QImage buffer in GameCaptureTargetWindow
        gc_win = win.game_capture_window
        gc_win._ensure_frame_buffer(320, 180)
        buf_ref = gc_win._frame_array
        img_ref = gc_win._frame_image
        assert buf_ref is not None and img_ref is not None
        assert buf_ref.shape == (180, 320, 4)

        # Calling _ensure_frame_buffer with the same dimensions reuses the exact same buffer
        gc_win._ensure_frame_buffer(320, 180)
        assert gc_win._frame_array is buf_ref
        assert gc_win._frame_image is img_ref

        # Rendering onto _frame_image mutates _frame_array directly in-place (zero-copy)
        win.canvas.render_scene(img_ref, 320, 180)
        assert int(buf_ref.sum()) > 0
    finally:
        win.player._is_running = False
        win.close()
