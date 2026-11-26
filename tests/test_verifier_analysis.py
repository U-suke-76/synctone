"""GUI tests for the recording analysis and auto-record flow in the AV Sync Checker window."""

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("SYNCTONE_TEST_DUMMY_AUDIO", "1")
pytest.importorskip("av")

from synctone.core.av_analysis import AvOffsetResult
from synctone.gui.verifier_window import SyncVerifierWindow
from synctone.i18n import I18nManager
from synctone.obs.client import ObsClient
from test_recording import write_recording


def _make_window():
    return SyncVerifierWindow(obs_client=ObsClient(), dummy_mode=True)


def _result(offset_ms: float) -> AvOffsetResult:
    return AvOffsetResult(
        offset_ms=offset_ms, uncertainty_ms=0.4, period_ms=545.5,
        audio_rms_ms=0.1, video_rms_ms=0.2, n_beeps=14, n_frames=480,
    )


def test_measure_buttons_visible_and_obs_state(qapp):
    win = _make_window()
    try:
        assert not win.btn_analyze.isHidden()
        assert not win.btn_auto_measure.isHidden()
        # OBS disconnected -> auto-measure disabled, file analyze enabled
        assert not win.btn_auto_measure.isEnabled()
        assert win.btn_analyze.isEnabled()
    finally:
        win.close()


def test_analysis_summary_direction(qapp):
    mgr = I18nManager.get_instance()
    prev = mgr.current_lang
    mgr.current_lang = "ja"
    try:
        s_minor = SyncVerifierWindow.format_analysis_summary(_result(22.3))
        assert "映像が音声より 22.3 ms 遅れて" in s_minor
        assert "わずかにズレています" in s_minor

        s_ok = SyncVerifierWindow.format_analysis_summary(_result(-12.2))
        assert "音声が映像より 12.2 ms 遅れて" in s_ok
        assert "ほぼズレなし" in s_ok

        s_large = SyncVerifierWindow.format_analysis_summary(_result(-44.2))
        assert "大きくズレています" in s_large

        assert "ほぼ一致" in SyncVerifierWindow.format_analysis_summary(_result(0.4))
    finally:
        mgr.current_lang = prev


def test_recording_analysis_end_to_end(qapp, tmp_path):
    path = tmp_path / "rec.mp4"
    write_recording(path, video_phase0=0.130, audio_phase0=0.100)  # video 30 ms later (wrap_phase=0.0)

    win = _make_window()
    try:
        win.start_recording_analysis(str(path), wrap_phase=0.0)
        worker = win._analysis_worker
        assert worker is not None and not win.btn_analyze.isEnabled()
        assert worker.wait(60000)
        for _ in range(50):
            qapp.processEvents()
            if win.last_analysis_result is not None:
                break
        assert win.last_analysis_result is not None
        assert win.last_analysis_result.offset_ms == pytest.approx(30.0, abs=3.0)
        assert win.btn_analyze.isEnabled()
        assert "30." in win.label_result_main.text() or "29." in win.label_result_main.text()
    finally:
        win.close()


def test_recording_analysis_error(qapp, tmp_path):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"garbage")

    win = _make_window()
    try:
        win.start_recording_analysis(str(bad))
        assert win._analysis_worker.wait(30000)
        for _ in range(50):
            qapp.processEvents()
            if win._analysis_worker is None:
                break
        assert win._analysis_worker is None
        assert win.last_analysis_result is None
        assert win.btn_analyze.isEnabled()
    finally:
        win.close()


def test_analysis_adjusts_video_render_delay_and_preserves_audio_offset(qapp):
    """When a video source is present, clicking Apply must adjust video render delay, NOT audio offset."""
    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_sync_offset.return_value = 126
    mock_obs.get_render_delay.return_value = 126
    mock_obs.set_render_delay.side_effect = lambda name, ms: ms

    vid_changes = []
    aud_changes = []
    win = SyncVerifierWindow(
        obs_client=mock_obs,
        current_obs_source="音声出力キャプチャ",
        current_obs_video_source="ウィンドウキャプチャ",
        on_offset_changed_cb=aud_changes.append,
        on_video_delay_changed_cb=vid_changes.append,
        dummy_mode=True,
    )
    try:
        # Case: audio is 44.2 ms later than video (offset_ms = -44.2) -> video render delay 126 -> 170 ms
        win._on_analysis_finished(_result(-44.2))
        assert not win.btn_apply_result.isHidden()
        assert win.btn_apply_result.isEnabled()
        assert "126 → 170 ms" in win.btn_apply_result.text()

        win.btn_apply_result.click()
        mock_obs.set_render_delay.assert_called_once_with("ウィンドウキャプチャ", 170)
        mock_obs.set_sync_offset.assert_not_called()
        assert vid_changes == [170]
        assert aud_changes == []
        assert not win.btn_apply_result.isEnabled()
    finally:
        win.close()


def test_auto_measure_blocks_when_already_recording(qapp):
    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_record_status.return_value = True
    mock_obs.get_sync_offset.return_value = 0

    win = SyncVerifierWindow(obs_client=mock_obs, current_obs_source="Audio", dummy_mode=True)
    try:
        win.start_auto_measure()
        mock_obs.start_record.assert_not_called()
        assert not win._auto_recording
    finally:
        win.close()


def test_auto_measure_records_and_restores_state(qapp):
    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_record_status.return_value = False
    mock_obs.get_input_kind.return_value = "window_capture"
    mock_obs.prepare_measurement_scene.return_value = ("Main Scene", "window_capture")
    mock_obs.stop_record.return_value = ""
    mock_obs.get_sync_offset.return_value = 0

    win = SyncVerifierWindow(obs_client=mock_obs, current_obs_source="Audio", dummy_mode=True)
    try:
        assert win.spin_bpm.value() == 120
        win.start_auto_measure()
        mock_obs.prepare_measurement_scene.assert_called_once()
        mock_obs.start_record.assert_called_once()
        assert win._auto_recording
        assert win.spin_bpm.value() == SyncVerifierWindow.ANALYSIS_BPM
        assert win.player.is_running

        win._finish_auto_record()
        mock_obs.stop_record.assert_called_once()
        mock_obs.set_current_scene.assert_called_once_with("Main Scene")
        mock_obs.cleanup_measurement_scene.assert_called_once()
        assert not win._auto_recording
        assert win.spin_bpm.value() == 120
        assert not win.player.is_running
    finally:
        win.close()


def test_auto_scene_consent_prompt_and_revoke(qapp, monkeypatch):
    """First auto-measure asks for consent, remembers it, and supports revoking via UI."""
    from PySide6.QtWidgets import QMessageBox

    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_record_status.return_value = False
    mock_obs.get_input_kind.return_value = "window_capture"
    mock_obs.prepare_measurement_scene.return_value = ("Main Scene", "window_capture")
    mock_obs.stop_record.return_value = ""
    mock_obs.get_sync_offset.return_value = 0

    win = SyncVerifierWindow(obs_client=mock_obs, current_obs_source="Audio", dummy_mode=True)
    try:
        win._set_auto_scene_consent(False)
        assert win.btn_revoke_consent.isHidden()

        # Decline -> does not start
        prompts = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: (prompts.append(a[1]), QMessageBox.StandardButton.No)[1],
        )
        win.start_auto_measure(skip_consent=False)
        assert len(prompts) == 1
        mock_obs.prepare_measurement_scene.assert_not_called()
        assert not win._has_auto_scene_consent()

        # Accept -> saves consent and starts
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: (prompts.append(a[1]), QMessageBox.StandardButton.Yes)[1],
        )
        win.start_auto_measure(skip_consent=False)
        assert len(prompts) == 2
        assert win._has_auto_scene_consent()
        assert not win.btn_revoke_consent.isHidden()
        win._finish_auto_record()

        # Second run -> no prompt
        win.start_auto_measure(skip_consent=False)
        assert len(prompts) == 2
        win._finish_auto_record()

        # Revoke button resets consent
        win.btn_revoke_consent.click()
        assert not win._has_auto_scene_consent()
        assert win.btn_revoke_consent.isHidden()
    finally:
        win._set_auto_scene_consent(False)
        win.close()


def test_auto_measure_game_capture_reuses_window_across_runs(qapp):
    """Repeated Game Capture auto-measurements must reuse the same HWND/window (hide, not destroy)."""
    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_record_status.return_value = False
    mock_obs.get_input_kind.return_value = "game_capture"
    mock_obs.prepare_measurement_scene.return_value = ("Main Scene", "game_capture")
    mock_obs.stop_record.return_value = ""
    mock_obs.get_render_delay.return_value = 175

    win = SyncVerifierWindow(
        obs_client=mock_obs,
        current_obs_source="Audio",
        current_obs_video_source="ゲームキャプチャ",
        dummy_mode=True,
    )
    try:
        # Run 1
        win.start_auto_measure()
        gc1 = win.game_capture_window
        assert gc1 is not None and gc1.isVisible()
        win._finish_auto_record()
        # Hidden from user, but instance kept alive for instant re-capture
        assert win.game_capture_window is gc1
        assert not gc1.isVisible()

        # Run 2 reuses the exact same GameCaptureTargetWindow instance
        win.start_auto_measure()
        assert win.game_capture_window is gc1
        assert gc1.isVisible()
        win._finish_auto_record()
        assert not gc1.isVisible()
    finally:
        win.close()


def test_png_has_visible_content():
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    def _to_png(img: QImage) -> bytes:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return bytes(buf.data())

    black = QImage(64, 36, QImage.Format.Format_RGB32)
    black.fill(QColor(0, 0, 0))
    assert not SyncVerifierWindow._png_has_visible_content(_to_png(black))

    lit = QImage(64, 36, QImage.Format.Format_RGB32)
    lit.fill(QColor(16, 16, 22))
    lit.setPixelColor(32, 18, QColor(255, 255, 255))
    assert SyncVerifierWindow._png_has_visible_content(_to_png(lit))
