import logging
from dataclasses import dataclass
from typing import List, Optional
import obsws_python as obs

# Silence verbose obsws_python exception tracebacks on expected non-audio queries
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
logging.getLogger("obsws_python.reqs").setLevel(logging.CRITICAL)

# Input kinds that never have audio tracks in OBS
NON_AUDIO_KINDS = {
    "image_source",
    "color_source",
    "color_source_v3",
    "text_gdiplus",
    "text_gdiplus_v2",
    "text_ft2_source",
    "text_ft2_source_v2",
    "monitor_capture",
    "display_capture",
    "window_capture",
    "game_capture",
    "slideshow",
    "scene",
    "group",
}

# Input kinds that are audio-only (no video rendering)
AUDIO_ONLY_KINDS = {
    "wasapi_input_capture",
    "wasapi_output_capture",
    "wasapi_process_output_capture",
    "pulse_input_capture",
    "pulse_output_capture",
    "alsa_input_capture",
    "coreaudio_input_capture",
    "coreaudio_output_capture",
}


@dataclass
class ObsAudioSource:
    """Information about an OBS audio input source."""
    name: str
    kind: str
    sync_offset_ms: int = 0


@dataclass
class ObsVideoSource:
    """Information about an OBS video input source and its render delay."""
    name: str
    kind: str
    render_delay_ms: int = 0
    filter_name: Optional[str] = None


class ObsClient:
    """Manages connection and audio synchronization offset with OBS Studio (WebSocket v5)."""

    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._client: Optional[obs.ReqClient] = None

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected to OBS."""
        if self._client is None:
            return False
        try:
            # Lightweight check: get version
            self._client.get_version()
            return True
        except Exception:
            self._client = None
            return False

    def connect(self) -> bool:
        """Attempt connection to OBS WebSocket server.

        Returns:
            True if connected successfully, False otherwise.
        """
        try:
            self._client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=3,
            )
            # Verify connection
            self._client.get_version()
            return True
        except Exception as e:
            self._client = None
            raise ConnectionError(f"Failed to connect to OBS Studio WebSocket: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from OBS."""
        self._client = None

    def get_audio_sources(self) -> List[ObsAudioSource]:
        """Fetch list of audio-capable sources from OBS with their current sync offset."""
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        # Query all inputs
        inputs_response = self._client.get_input_list()
        audio_sources: List[ObsAudioSource] = []

        for item in inputs_response.inputs:
            name = item.get("inputName")
            kind = item.get("inputKind", "")

            # Skip explicitly non-audio source kinds
            if kind in NON_AUDIO_KINDS:
                continue

            # Query sync offset; if successful, source supports audio
            try:
                res = self._client.get_input_audio_sync_offset(name)
                offset_ms = int(getattr(res, "input_audio_sync_offset", 0))
                audio_sources.append(ObsAudioSource(name=name, kind=kind, sync_offset_ms=offset_ms))
            except Exception:
                # Source does not support audio in OBS (e.g. video capture device without audio routing)
                pass

        return audio_sources

    def get_sync_offset(self, source_name: str) -> int:
        """Get current sync offset in milliseconds for a specific input source."""
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        try:
            res = self._client.get_input_audio_sync_offset(source_name)
            return int(getattr(res, "input_audio_sync_offset", 0))
        except Exception as e:
            raise RuntimeError(f"Failed to get sync offset for '{source_name}': {e}") from e

    def set_sync_offset(self, source_name: str, offset_ms: float) -> int:
        """Set sync offset in milliseconds for a specific input source.

        Note: OBS Studio strictly requires integer milliseconds for audio sync offset.
        Any floating point input is rounded to the nearest integer.

        Args:
            source_name: Name of the input source in OBS.
            offset_ms: Delay in milliseconds (must be >= 0 in OBS).

        Returns:
            The rounded integer offset applied in OBS.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        target_int = int(round(max(0.0, float(offset_ms))))
        try:
            self._client.set_input_audio_sync_offset(source_name, target_int)
            return target_int
        except Exception as e:
            raise RuntimeError(f"Failed to set sync offset for '{source_name}': {e}") from e

    def get_video_sources(self) -> List[ObsVideoSource]:
        """Fetch list of video-capable input sources from OBS along with their render delay."""
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        inputs_response = self._client.get_input_list()
        video_sources: List[ObsVideoSource] = []

        for item in inputs_response.inputs:
            name = item.get("inputName")
            kind = item.get("inputKind", "")

            # Skip audio-only source kinds
            if kind in AUDIO_ONLY_KINDS:
                continue

            # Query existing filters on this source to see if gpu_delay exists
            delay_ms = 0
            found_filter_name: Optional[str] = None
            try:
                filters_res = self._client.get_source_filter_list(name)
                filters = getattr(filters_res, "filters", [])
                for f in filters:
                    f_kind = f.get("filterKind") if isinstance(f, dict) else getattr(f, "filter_kind", "")
                    if f_kind == "gpu_delay":
                        found_filter_name = f.get("filterName") if isinstance(f, dict) else getattr(f, "filter_name", "")
                        f_settings = f.get("filterSettings", {}) if isinstance(f, dict) else getattr(f, "filter_settings", {})
                        if isinstance(f_settings, dict):
                            delay_ms = int(f_settings.get("delay_ms", 0))
                        break
            except Exception:
                pass

            video_sources.append(
                ObsVideoSource(
                    name=name,
                    kind=kind,
                    render_delay_ms=delay_ms,
                    filter_name=found_filter_name,
                )
            )

        return video_sources

    def get_render_delay(self, source_name: str) -> int:
        """Get current render delay (gpu_delay) in milliseconds for a video source."""
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        try:
            filters_res = self._client.get_source_filter_list(source_name)
            filters = getattr(filters_res, "filters", [])
            for f in filters:
                f_kind = f.get("filterKind") if isinstance(f, dict) else getattr(f, "filter_kind", "")
                if f_kind == "gpu_delay":
                    f_settings = f.get("filterSettings", {}) if isinstance(f, dict) else getattr(f, "filter_settings", {})
                    if isinstance(f_settings, dict):
                        return int(f_settings.get("delay_ms", 0))
            return 0
        except Exception as e:
            raise RuntimeError(f"Failed to get render delay for '{source_name}': {e}") from e

    def set_render_delay(
        self,
        source_name: str,
        delay_ms: float,
        filter_name: str = "SyncTone 映像遅延",
    ) -> int:
        """Set or update render delay (gpu_delay) filter on an OBS video source.

        Args:
            source_name: Name of the video source in OBS.
            delay_ms: Delay in milliseconds (clamped to 0..500 ms per OBS gpu_delay specification).
            filter_name: Name of the filter to create or update.

        Returns:
            The applied delay in milliseconds (clamped integer, 0..500).
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        # OBS gpu_delay filter supports up to 500ms
        clamped_ms = max(0, min(500, int(round(delay_ms))))

        # Check existing filters on the source
        existing_filter_name: Optional[str] = None
        try:
            filters_res = self._client.get_source_filter_list(source_name)
            filters = getattr(filters_res, "filters", [])
            for f in filters:
                f_kind = f.get("filterKind") if isinstance(f, dict) else getattr(f, "filter_kind", "")
                f_name = f.get("filterName") if isinstance(f, dict) else getattr(f, "filter_name", "")
                if f_kind == "gpu_delay":
                    if f_name == filter_name or "synctone" in str(f_name).lower():
                        existing_filter_name = f_name
                        break
                    elif existing_filter_name is None:
                        existing_filter_name = f_name
        except Exception:
            pass

        if existing_filter_name:
            # Update settings on existing filter and ensure it is enabled
            try:
                self._client.set_source_filter_settings(
                    source_name,
                    existing_filter_name,
                    {"delay_ms": clamped_ms},
                    overlay=True,
                )
                self._client.set_source_filter_enabled(
                    source_name,
                    existing_filter_name,
                    True,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to update render delay filter on '{source_name}': {e}"
                ) from e
        else:
            # Create new gpu_delay filter
            try:
                self._client.create_source_filter(
                    source_name,
                    filter_name,
                    "gpu_delay",
                    {"delay_ms": clamped_ms},
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create render delay filter on '{source_name}': {e}"
                ) from e

        return clamped_ms

    def remove_render_delay(
        self,
        source_name: str,
        filter_name: str = "SyncTone 映像遅延",
    ) -> None:
        """Remove or reset render delay filter on a video source."""
        if not self.is_connected:
            raise ConnectionError("Not connected to OBS Studio.")

        try:
            filters_res = self._client.get_source_filter_list(source_name)
            filters = getattr(filters_res, "filters", [])
            for f in filters:
                f_kind = f.get("filterKind") if isinstance(f, dict) else getattr(f, "filter_kind", "")
                f_name = f.get("filterName") if isinstance(f, dict) else getattr(f, "filter_name", "")
                if f_kind == "gpu_delay" and (f_name == filter_name or "synctone" in str(f_name).lower()):
                    self._client.remove_source_filter(source_name, f_name)
        except Exception as e:
            raise RuntimeError(f"Failed to remove render delay filter from '{source_name}': {e}") from e

