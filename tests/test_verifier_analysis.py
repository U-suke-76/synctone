"""GUI tests for the recording analysis in the AV Sync Checker window."""

import os

import pytest

os.environ.setdefault("SYNCTONE_TEST_DUMMY_AUDIO", "1")
pytest.importorskip("av")

from PySide6.QtWidgets import QMessageBox

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


def test_analyze_button_only_in_analysis_mode(qapp):
    win = _make_window()
    try:
        assert win.btn_analyze.isHidden()
        win.radio_analysis.setChecked(True)
        assert not win.btn_analyze.isHidden()
        win.radio_flash.setChecked(True)
        assert win.btn_analyze.isHidden()
    finally:
        win.close()


def test_analysis_summary_direction(qapp):
    mgr = I18nManager.get_instance()
    prev = mgr.current_lang
    mgr.current_lang = "ja"
    try:
        s_minor = SyncVerifierWindow.format_analysis_summary(_result(12.3))
        assert "映像が音声より 12.3 ms 遅れて" in s_minor
        assert "わずかにズレています" in s_minor

        s_ok = SyncVerifierWindow.format_analysis_summary(_result(-5.2))
        assert "音声が映像より 5.2 ms 遅れて" in s_ok
        assert "ほぼズレなし" in s_ok

        s_large = SyncVerifierWindow.format_analysis_summary(_result(-44.2))
        assert "大きくズレています" in s_large

        assert "ほぼ一致" in SyncVerifierWindow.format_analysis_summary(_result(0.4))
    finally:
        mgr.current_lang = prev


def test_recording_analysis_end_to_end(qapp, tmp_path, monkeypatch):
    path = tmp_path / "rec.mp4"
    write_recording(path, video_phase0=0.130, audio_phase0=0.100)  # video 30 ms later

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))

    win = _make_window()
    try:
        win.radio_analysis.setChecked(True)
        win.start_recording_analysis(str(path))
        worker = win._analysis_worker
        assert worker is not None and not win.btn_analyze.isEnabled()
        assert worker.wait(60000)
        for _ in range(50):
            qapp.processEvents()
            if shown:
                break
        assert win.last_analysis_result is not None
        assert win.last_analysis_result.offset_ms == pytest.approx(30.0, abs=3.0)
        assert win.btn_analyze.isEnabled()
        assert len(shown) == 1
    finally:
        win.close()


def test_recording_analysis_error(qapp, tmp_path, monkeypatch):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"garbage")
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[1]))

    win = _make_window()
    try:
        win.start_recording_analysis(str(bad))
        assert win._analysis_worker.wait(30000)
        for _ in range(50):
            qapp.processEvents()
            if shown:
                break
        assert shown and win._analysis_worker is None
        assert win.last_analysis_result is None
    finally:
        win.close()


def test_analysis_adjusts_video_render_delay_and_preserves_audio_offset(qapp, monkeypatch):
    """When a video source is present, recording analysis must adjust video render delay, NOT audio offset."""
    from unittest.mock import MagicMock

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
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.Yes)[1],
        )
        win._on_analysis_finished(_result(-44.2))
        assert len(asked) == 1
        assert "ウィンドウキャプチャ" in asked[0]
        assert "126 ms → 170 ms" in asked[0]
        mock_obs.set_render_delay.assert_called_once_with("ウィンドウキャプチャ", 170)
        mock_obs.set_sync_offset.assert_not_called()
        assert vid_changes == [170]
        assert aud_changes == []
    finally:
        win.close()

