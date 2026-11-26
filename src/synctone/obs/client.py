import base64
import logging
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Tuple
import obsws_python as obs

# Silence verbose obsws_python exception tracebacks on expected non-audio queries
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
logging.getLogger("obsws_python.reqs").setLevel(logging.CRITICAL)

DEFAULT_RENDER_DELAY_FILTER_NAME = "SyncTone 映像遅延"
MAX_RENDER_DELAY_MS = 500
MEASUREMENT_SCENE_NAME = "SyncTone 測定用"
MEASUREMENT_WINDOW_SOURCE_NAME = "SyncTone キャプチャ (Window)"
MEASUREMENT_GAME_SOURCE_NAME = "SyncTone キャプチャ (Game)"
MEASUREMENT_AUDIO_SOURCE_NAME = "SyncTone 音声出力キャプチャ"

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

    def get_record_status(self) -> bool:
        """Return True if OBS Studio is currently recording."""
        client = self._ensure_connected()
        try:
            res = client.get_record_status()
            return bool(getattr(res, "output_active", False))
        except Exception as e:
            raise RuntimeError(f"Failed to get OBS record status: {e}") from e

    def start_record(self) -> None:
        """Start recording in OBS Studio."""
        client = self._ensure_connected()
        try:
            client.start_record()
        except Exception as e:
            raise RuntimeError(f"Failed to start OBS recording: {e}") from e

    def stop_record(self) -> str:
        """Stop recording in OBS Studio and return the saved file path."""
        client = self._ensure_connected()
        try:
            res = client.stop_record()
            return str(getattr(res, "output_path", "") or "")
        except Exception as e:
            raise RuntimeError(f"Failed to stop OBS recording: {e}") from e

    def get_current_scene(self) -> str:
        """Return the name of the current OBS program scene."""
        client = self._ensure_connected()
        try:
            res = client.get_current_program_scene()
            return str(getattr(res, "scene_name", "") or getattr(res, "current_program_scene_name", "") or "")
        except Exception as e:
            raise RuntimeError(f"Failed to get current OBS scene: {e}") from e

    def set_current_scene(self, scene_name: str) -> None:
        """Switch OBS program scene to scene_name."""
        client = self._ensure_connected()
        try:
            client.set_current_program_scene(scene_name)
        except Exception as e:
            raise RuntimeError(f"Failed to switch OBS scene to '{scene_name}': {e}") from e

    def get_input_kind(self, source_name: str) -> str:
        """Return the OBS inputKind for source_name, or empty string if not found."""
        client = self._ensure_connected()
        try:
            inputs_res = client.get_input_list()
            for item in getattr(inputs_res, "inputs", []):
                if item.get("inputName") == source_name:
                    return str(item.get("inputKind", ""))
        except Exception:
            pass
        return ""

    def _ensure_scene_item(self, scene_name: str, source_name: str, visible: bool = True) -> None:
        """Ensure source_name exists as a scene item in scene_name and set its visibility."""
        client = self._ensure_connected()
        items_res = client.get_scene_item_list(scene_name)
        item_id = None
        for item in getattr(items_res, "scene_items", []):
            if item.get("sourceName") == source_name:
                item_id = item.get("sceneItemId")
                break
        if item_id is None:
            res = client.create_scene_item(scene_name, source_name, visible)
            item_id = getattr(res, "scene_item_id", None)
        elif item_id is not None:
            client.set_scene_item_enabled(scene_name, item_id, visible)

    def prepare_measurement_scene(
        self,
        template_video_source: Optional[str],
        window_title: str,
        exe_name: str = "SyncTone.exe",
        audio_source: Optional[str] = None,
        window_class: str = "QtWindow",
        output_device_name: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Prepare and switch to the dedicated SyncTone measurement scene.

        Creates (or updates) a cloned capture source matching the template video source's
        capture kind (game_capture vs window_capture) and current render delay without
        modifying the user's original scenes or sources. Also creates a dedicated audio
        output capture source (default device) with the selected audio source's sync offset
        so beeps are guaranteed to be recorded.

        Returns:
            (original_scene_name, capture_kind)
        """
        client = self._ensure_connected()
        original_scene = self.get_current_scene()

        # Determine capture kind & current render delay from the user's selected video source
        template_kind = self.get_input_kind(template_video_source) if template_video_source else ""
        capture_kind = "game_capture" if template_kind == "game_capture" else "window_capture"
        cur_delay = 0
        if template_video_source:
            try:
                cur_delay = self.get_render_delay(template_video_source)
            except Exception:
                cur_delay = 0

        # Ensure measurement scene exists
        scenes_res = client.get_scene_list()
        scene_names = {s.get("sceneName") for s in getattr(scenes_res, "scenes", [])}
        if MEASUREMENT_SCENE_NAME not in scene_names:
            client.create_scene(MEASUREMENT_SCENE_NAME)

        # Use distinct source names for window_capture vs game_capture to avoid 601 name conflicts
        active_name = (
            MEASUREMENT_GAME_SOURCE_NAME if capture_kind == "game_capture" else MEASUREMENT_WINDOW_SOURCE_NAME
        )
        other_name = (
            MEASUREMENT_WINDOW_SOURCE_NAME if capture_kind == "game_capture" else MEASUREMENT_GAME_SOURCE_NAME
        )

        # Build OBS window selector string with exact Windows class name (priority 0 = match by title)
        win_spec = f"{window_title}:{window_class}:{exe_name}"
        if capture_kind == "game_capture":
            settings: dict[str, Any] = {
                "capture_mode": "window",
                "window": win_spec,
                "priority": 0,
            }
        else:
            settings = {
                "window": win_spec,
                "priority": 0,
                "method": 2,  # Windows 10/11 Graphics Capture (WGC)
            }

        # Reuse existing input or create a new one, then ensure it is visible in the measurement scene.
        # Avoid calling set_input_settings when settings already match so OBS game_capture doesn't drop its hook.
        if self.get_input_kind(active_name):
            needs_update = True
            try:
                cur_res = client.get_input_settings(active_name)
                cur_settings = getattr(cur_res, "input_settings", {}) or {}
                if all(cur_settings.get(k) == v for k, v in settings.items()):
                    needs_update = False
            except Exception:
                needs_update = True
            if needs_update:
                client.set_input_settings(active_name, settings, overlay=True)
            self._ensure_scene_item(MEASUREMENT_SCENE_NAME, active_name, visible=True)
        else:
            client.create_input(
                MEASUREMENT_SCENE_NAME,
                active_name,
                capture_kind,
                settings,
                True,
            )

        # Hide the other capture source if it exists in the measurement scene
        if self.get_input_kind(other_name):
            try:
                self._ensure_scene_item(MEASUREMENT_SCENE_NAME, other_name, visible=False)
            except Exception:
                pass

        # Create/update a dedicated standard WASAPI output capture (hardware-clock stable; avoids
        # wasapi_process_output_capture's random timestamp offset) and match SyncTone's playback device.
        audio_offset_ms = 0
        if audio_source:
            try:
                audio_offset_ms = self.get_sync_offset(audio_source)
            except Exception:
                audio_offset_ms = 0

        try:
            if not self.get_input_kind(MEASUREMENT_AUDIO_SOURCE_NAME):
                client.create_input(
                    MEASUREMENT_SCENE_NAME,
                    MEASUREMENT_AUDIO_SOURCE_NAME,
                    "wasapi_output_capture",
                    {"device_id": "default"},
                    True,
                )
            else:
                self._ensure_scene_item(MEASUREMENT_SCENE_NAME, MEASUREMENT_AUDIO_SOURCE_NAME, visible=True)

            matched_device_id = "default"
            if output_device_name:
                try:
                    props_res = client.get_input_properties_list_property_items(
                        MEASUREMENT_AUDIO_SOURCE_NAME, "device_id"
                    )
                    items = getattr(props_res, "property_items", []) or []
                    needle = output_device_name.lower()
                    for item in items:
                        item_name = str(item.get("itemName", ""))
                        item_val = str(item.get("itemValue", ""))
                        if not item_val or item_val == "default":
                            continue
                        if needle == item_name.lower() or needle in item_name.lower() or item_name.lower() in needle:
                            matched_device_id = item_val
                            break
                except Exception:
                    matched_device_id = "default"

            client.set_input_settings(
                MEASUREMENT_AUDIO_SOURCE_NAME,
                {"device_id": matched_device_id},
                overlay=True,
            )
            self.set_sync_offset(MEASUREMENT_AUDIO_SOURCE_NAME, audio_offset_ms)
        except Exception:
            pass

        # Sync render delay filter to match the template video source
        if cur_delay > 0:
            self.set_render_delay(active_name, cur_delay)
        else:
            try:
                self.remove_render_delay(active_name)
            except Exception:
                pass

        # Switch to the dedicated measurement scene
        self.set_current_scene(MEASUREMENT_SCENE_NAME)
        return original_scene, capture_kind

    def get_source_screenshot_png(self, source_name: str, width: int = 160, height: int = 90) -> Optional[bytes]:
        """Fetch a small PNG screenshot of source_name from OBS, or None on error."""
        client = self._ensure_connected()
        try:
            res = client.get_source_screenshot(source_name, "png", width, height, 50)
            image_data = str(getattr(res, "image_data", "") or "")
            if not image_data:
                return None
            b64_part = image_data.split(",", 1)[-1]
            return base64.b64decode(b64_part)
        except Exception:
            return None

    def refresh_measurement_capture_source(self, source_name: str) -> None:
        """Toggle visibility of a measurement capture source to nudge OBS game_capture to re-hook."""
        client = self._ensure_connected()
        try:
            self._ensure_scene_item(MEASUREMENT_SCENE_NAME, source_name, visible=False)
            self._ensure_scene_item(MEASUREMENT_SCENE_NAME, source_name, visible=True)
        except Exception:
            pass

    def cleanup_measurement_scene(self) -> None:
        """Remove the temporary SyncTone measurement scene and its dedicated capture sources."""
        client = self._ensure_connected()
        for src_name in (
            MEASUREMENT_WINDOW_SOURCE_NAME,
            MEASUREMENT_GAME_SOURCE_NAME,
            MEASUREMENT_AUDIO_SOURCE_NAME,
        ):
            try:
                if self.get_input_kind(src_name):
                    client.remove_input(src_name)
            except Exception:
                pass
        try:
            scenes_res = client.get_scene_list()
            scene_names = {s.get("sceneName") for s in getattr(scenes_res, "scenes", [])}
            if MEASUREMENT_SCENE_NAME in scene_names:
                client.remove_scene(MEASUREMENT_SCENE_NAME)
        except Exception:
            pass


