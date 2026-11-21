import logging
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Tuple
import obsws_python as obs

# Silence verbose obsws_python exception tracebacks on expected non-audio queries
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
logging.getLogger("obsws_python.reqs").setLevel(logging.CRITICAL)

DEFAULT_RENDER_DELAY_FILTER_NAME = "SyncTone 映像遅延"
MAX_RENDER_DELAY_MS = 500

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

    def _ensure_connected(self) -> obs.ReqClient:
        """Verify OBS connection and return the active ReqClient instance."""
        if not self.is_connected or self._client is None:
            raise ConnectionError("Not connected to OBS Studio.")
        return self._client

    @staticmethod
    def _extract_filter_field(filter_entry: Any, dict_key: str, attr_name: str, default: Any = "") -> Any:
        if isinstance(filter_entry, dict):
            return filter_entry.get(dict_key, default)
        return getattr(filter_entry, attr_name, default)

    def _iter_gpu_delay_filters(self, source_name: str) -> Iterator[Tuple[str, int]]:
        """Yield (filter_name, delay_ms) for each gpu_delay filter attached to source_name."""
        assert self._client is not None
        filters_res = self._client.get_source_filter_list(source_name)
        filters = getattr(filters_res, "filters", [])
        for f in filters:
            f_kind = self._extract_filter_field(f, "filterKind", "filter_kind", "")
            if f_kind != "gpu_delay":
                continue
            f_name = str(self._extract_filter_field(f, "filterName", "filter_name", ""))
            f_settings = self._extract_filter_field(f, "filterSettings", "filter_settings", {})
            delay_ms = int(f_settings.get("delay_ms", 0)) if isinstance(f_settings, dict) else 0
            yield f_name, delay_ms

    def get_audio_sources(self) -> List[ObsAudioSource]:
        """Fetch list of audio-capable sources from OBS with their current sync offset."""
        client = self._ensure_connected()

        inputs_response = client.get_input_list()
        audio_sources: List[ObsAudioSource] = []

        for item in inputs_response.inputs:
            name = item.get("inputName")
            kind = item.get("inputKind", "")

            if kind in NON_AUDIO_KINDS:
                continue

            # Query sync offset; if successful, source supports audio
            try:
                res = client.get_input_audio_sync_offset(name)
                offset_ms = int(getattr(res, "input_audio_sync_offset", 0))
                audio_sources.append(ObsAudioSource(name=name, kind=kind, sync_offset_ms=offset_ms))
            except Exception:
                # Source does not support audio in OBS (e.g. video capture device without audio routing)
                pass

        return audio_sources

    def get_sync_offset(self, source_name: str) -> int:
        """Get current sync offset in milliseconds for a specific input source."""
        client = self._ensure_connected()

        try:
            res = client.get_input_audio_sync_offset(source_name)
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
        client = self._ensure_connected()

        target_int = int(round(max(0.0, float(offset_ms))))
        try:
            client.set_input_audio_sync_offset(source_name, target_int)
            return target_int
        except Exception as e:
            raise RuntimeError(f"Failed to set sync offset for '{source_name}': {e}") from e

    def get_video_sources(self) -> List[ObsVideoSource]:
        """Fetch list of video-capable input sources from OBS along with their render delay."""
        client = self._ensure_connected()

        inputs_response = client.get_input_list()
        video_sources: List[ObsVideoSource] = []

        for item in inputs_response.inputs:
            name = item.get("inputName")
            kind = item.get("inputKind", "")

            if kind in AUDIO_ONLY_KINDS:
                continue

            delay_ms = 0
            found_filter_name: Optional[str] = None
            try:
                first_filter = next(self._iter_gpu_delay_filters(name), None)
                if first_filter is not None:
                    found_filter_name, delay_ms = first_filter
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
        self._ensure_connected()

        try:
            first_filter = next(self._iter_gpu_delay_filters(source_name), None)
            return first_filter[1] if first_filter is not None else 0
        except Exception as e:
            raise RuntimeError(f"Failed to get render delay for '{source_name}': {e}") from e

    def set_render_delay(
        self,
        source_name: str,
        delay_ms: float,
        filter_name: str = DEFAULT_RENDER_DELAY_FILTER_NAME,
    ) -> int:
        """Set or update render delay (gpu_delay) filter on an OBS video source.

        Args:
            source_name: Name of the video source in OBS.
            delay_ms: Delay in milliseconds (clamped to 0..500 ms per OBS gpu_delay specification).
            filter_name: Name of the filter to create or update.

        Returns:
            The applied delay in milliseconds (clamped integer, 0..500).
        """
        client = self._ensure_connected()

        # OBS gpu_delay filter supports up to 500ms
        clamped_ms = max(0, min(MAX_RENDER_DELAY_MS, int(round(delay_ms))))

        existing_filter_name: Optional[str] = None
        try:
            for f_name, _ in self._iter_gpu_delay_filters(source_name):
                if f_name == filter_name or "synctone" in f_name.lower():
                    existing_filter_name = f_name
                    break
                if existing_filter_name is None:
                    existing_filter_name = f_name
        except Exception:
            pass

        if existing_filter_name:
            try:
                client.set_source_filter_settings(
                    source_name,
                    existing_filter_name,
                    {"delay_ms": clamped_ms},
                    overlay=True,
                )
                client.set_source_filter_enabled(
                    source_name,
                    existing_filter_name,
                    True,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to update render delay filter on '{source_name}': {e}"
                ) from e
        else:
            try:
                client.create_source_filter(
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
        filter_name: str = DEFAULT_RENDER_DELAY_FILTER_NAME,
    ) -> None:
        """Remove or reset render delay filter on a video source."""
        client = self._ensure_connected()

        try:
            for f_name, _ in list(self._iter_gpu_delay_filters(source_name)):
                if f_name == filter_name or "synctone" in f_name.lower():
                    client.remove_source_filter(source_name, f_name)
        except Exception as e:
            raise RuntimeError(f"Failed to remove render delay filter from '{source_name}': {e}") from e

