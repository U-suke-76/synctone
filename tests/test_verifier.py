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


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
    """Verify click and beep tone generators produce valid normalized signals."""
    from synctone.core.verifier_audio import generate_click_sound, generate_beep_sound

    click = generate_click_sound(sample_rate=48000, duration=0.035, freq=1200.0, amplitude=0.6)
    assert isinstance(click, np.ndarray)
    assert len(click) == int(48000 * 0.035)
    assert not np.isnan(click).any()
    assert np.max(np.abs(click)) <= 0.6 + 1e-4

    beep = generate_beep_sound(sample_rate=48000, duration=0.04, freq=1760.0, amplitude=0.5)
    assert isinstance(beep, np.ndarray)
    assert len(beep) == int(48000 * 0.04)
    assert not np.isnan(beep).any()
    assert np.max(np.abs(beep)) <= 0.5 + 1e-4


def test_sync_audio_player_logic():
    """Verify SyncAudioPlayer parameter adjustments, callback streaming, and phase tracking."""
    from synctone.core.verifier_audio import SyncAudioPlayer

    # Use dummy_mode=True to bypass hardware PortAudio in test suite
    player = SyncAudioPlayer(sample_rate=48000, bpm=120.0, amplitude=0.5, mode="beep", dummy_mode=True)
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

    # Mode update
    player.set_mode("click")
    assert player.mode == "click"
    player.set_mode("beep")
    assert player.mode == "beep"

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

    # Active render in beep mode (forces paintEvent with drawPolygon)
    from PySide6.QtGui import QPaintEvent
    from PySide6.QtCore import QRect
    player.start()
    event = QPaintEvent(QRect(0, 0, 600, 300))
    canvas.paintEvent(event)

    # Active render in click mode
    player.set_mode("click")
    canvas.paintEvent(event)

    player.stop()
    canvas.stop_timer()
    canvas.close()


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

    # Mode switch
    window.radio_click.setChecked(True)
    assert window.player.mode == "click"

    window.radio_flash.setChecked(True)
    assert window.player.mode == "beep"

    # Tempo spinbox change
    window.spin_bpm.setValue(100)
    assert window.player.bpm == 100.0

    # Volume slider change
    window.slider_volume.setValue(70)
    assert abs(window.player.amplitude - 0.7) < 1e-4

    # OBS trim buttons (+1ms, -5ms, etc.)
    window._adjust_obs_offset(1.0)
    mock_obs.set_sync_offset.assert_called_with("BGM Source", 141)
    assert offset_changed_records[-1] == 141.0

    window._adjust_obs_offset(-5.0)
    mock_obs.set_sync_offset.assert_called_with("BGM Source", 135)
    assert offset_changed_records[-1] == 135.0

    # Multilingual retranslate test
    from synctone.i18n import I18nManager
    I18nManager.get_instance().current_lang = "en"
    window.retranslate_ui()
    assert "AV Sync" in window.windowTitle()

    window.close()
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
