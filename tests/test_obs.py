"""Tests for OBS WebSocket client integration."""

from unittest.mock import MagicMock, patch
import pytest
from synctone.obs.client import ObsClient


def test_obs_client_connect_failure():
    """Verify that connection failure raises ConnectionError cleanly."""
    client = ObsClient(host="127.0.0.1", port=1)
    with pytest.raises(ConnectionError):
        client.connect()
    assert not client.is_connected


def test_obs_client_get_sources_mocked():
    """Verify source parsing and offset retrieval with mocked obsws_python."""
    client = ObsClient()
    mock_req = MagicMock()
    mock_req.get_version.return_value = MagicMock()
    mock_req.get_input_list.return_value = MagicMock(inputs=[
        {"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"},
        {"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"},
        {"inputName": "Webcam", "inputKind": "dshow_input"},
    ])

    def mock_offset(name):
        res = MagicMock()
        if name == "Mic/Aux":
            res.input_audio_sync_offset = 50
        elif name == "Desktop Audio":
            res.input_audio_sync_offset = 0
        else:
            raise RuntimeError("Not audio")
        return res

    mock_req.get_input_audio_sync_offset.side_effect = mock_offset
    client._client = mock_req

    sources = client.get_audio_sources()
    assert len(sources) == 2
    assert sources[0].name == "Mic/Aux"
    assert sources[0].sync_offset_ms == 50
    assert sources[1].name == "Desktop Audio"
    assert sources[1].sync_offset_ms == 0


def test_obs_client_set_offset_clamping():
    """Verify offset is clamped to >= 0 when setting."""
    client = ObsClient()
    mock_req = MagicMock()
    mock_req.get_version.return_value = MagicMock()
    client._client = mock_req

    client.set_sync_offset("Desktop Audio", -30)
    # Should clamp to 0
    mock_req.set_input_audio_sync_offset.assert_called_with("Desktop Audio", 0)

    client.set_sync_offset("Desktop Audio", 125.7)
    # Should round 125.7 to 126 for integer OBS sync offset requirement
    mock_req.set_input_audio_sync_offset.assert_called_with("Desktop Audio", 126)


def test_obs_client_get_video_sources_mocked():
    """Verify video source parsing and render delay retrieval."""
    client = ObsClient()
    mock_req = MagicMock()
    mock_req.get_version.return_value = MagicMock()
    mock_req.get_input_list.return_value = MagicMock(inputs=[
        {"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"},
        {"inputName": "Game Capture HD", "inputKind": "game_capture"},
        {"inputName": "Webcam", "inputKind": "dshow_input"},
    ])

    def mock_filter_list(name):
        res = MagicMock()
        if name == "Game Capture HD":
            res.filters = [
                {
                    "filterKind": "gpu_delay",
                    "filterName": "SyncTone 映像遅延",
                    "filterSettings": {"delay_ms": 150},
                }
            ]
        else:
            res.filters = []
        return res

    mock_req.get_source_filter_list.side_effect = mock_filter_list
    client._client = mock_req

    video_sources = client.get_video_sources()
    # Desktop Audio is audio-only, so only 2 video sources
    assert len(video_sources) == 2
    assert video_sources[0].name == "Game Capture HD"
    assert video_sources[0].render_delay_ms == 150
    assert video_sources[1].name == "Webcam"
    assert video_sources[1].render_delay_ms == 0


def test_obs_client_set_render_delay_create_and_clamp():
    """Verify set_render_delay creates new filter and clamps to 0..500 ms."""
    client = ObsClient()
    mock_req = MagicMock()
    mock_req.get_version.return_value = MagicMock()
    mock_req.get_source_filter_list.return_value = MagicMock(filters=[])
    client._client = mock_req

    # 1. New filter creation
    res = client.set_render_delay("Game Capture HD", 180)
    assert res == 180
    mock_req.create_source_filter.assert_called_with(
        "Game Capture HD", "SyncTone 映像遅延", "gpu_delay", {"delay_ms": 180}
    )

    # 2. Clamping over 500 ms
    res_clamped = client.set_render_delay("Game Capture HD", 650)
    assert res_clamped == 500
    mock_req.create_source_filter.assert_called_with(
        "Game Capture HD", "SyncTone 映像遅延", "gpu_delay", {"delay_ms": 500}
    )

    # 3. Existing filter update
    mock_req.get_source_filter_list.return_value = MagicMock(filters=[
        {"filterKind": "gpu_delay", "filterName": "SyncTone 映像遅延", "filterSettings": {"delay_ms": 180}}
    ])
    res_update = client.set_render_delay("Game Capture HD", 220)
    assert res_update == 220
    mock_req.set_source_filter_settings.assert_called_with(
        "Game Capture HD", "SyncTone 映像遅延", {"delay_ms": 220}, overlay=True
    )
    mock_req.set_source_filter_enabled.assert_called_with(
        "Game Capture HD", "SyncTone 映像遅延", True
    )

