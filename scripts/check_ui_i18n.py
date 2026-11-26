r"""Render MainWindow and SyncVerifierWindow across all 5 languages with real Windows fonts.

Usage:
    .\.venv\Scripts\python.exe scripts/check_ui_i18n.py [output_dir]
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

os.environ["SYNCTONE_TEST_DUMMY_AUDIO"] = "1"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from synctone.core.av_analysis import AvOffsetResult
from synctone.gui.main_window import MainWindow
from synctone.gui.verifier_window import SyncVerifierWindow
from synctone.i18n import I18nManager
from synctone.obs.client import ObsClient, ObsVideoSource

LANGUAGES = ("ja", "en", "ko", "zh_TW", "zh_CN")


def _find_clipped_buttons(win) -> list[str]:
    clipped = []
    for btn in win.findChildren(QPushButton):
        if btn.isVisible() and btn.width() < btn.sizeHint().width() - 2:
            label = btn.objectName() or btn.text()[:24]
            clipped.append(f"{label} (w={btn.width()} < hint={btn.sizeHint().width()})")
    return clipped


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tmp_ui_check")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication([])

    mock_obs = MagicMock(spec=ObsClient)
    mock_obs.is_connected = True
    mock_obs.get_video_sources.return_value = [
        ObsVideoSource(name="ゲームキャプチャ", kind="game_capture", render_delay_ms=175)
    ]
    mock_obs.get_render_delay.return_value = 175
    mock_obs.get_sync_offset.return_value = 112

    sample_result = AvOffsetResult(
        offset_ms=-36.4,
        uncertainty_ms=0.5,
        period_ms=545.5,
        audio_rms_ms=0.1,
        video_rms_ms=0.2,
        n_beeps=7,
        n_frames=240,
    )

    mwin = MainWindow()
    mwin.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    mwin.show()

    any_clipped = False
    for lang in LANGUAGES:
        I18nManager.get_instance().current_lang = lang
        mwin.retranslate_ui()
        app.processEvents()
        m_clipped = _find_clipped_buttons(mwin)
        mwin.grab().save(str(out_dir / f"main_{lang}.png"))

        vwin = SyncVerifierWindow(obs_client=mock_obs, current_obs_source="Audio", dummy_mode=True)
        vwin.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        vwin._set_auto_scene_consent(True)
        vwin._on_analysis_finished(sample_result)
        vwin.show()
        app.processEvents()
        v_clipped = _find_clipped_buttons(vwin)
        vwin.grab().save(str(out_dir / f"verifier_{lang}.png"))
        vwin.close()

        if m_clipped or v_clipped:
            any_clipped = True
        print(f"[{lang}] main_clipped={m_clipped} verifier_clipped={v_clipped}")

    I18nManager.get_instance().current_lang = "ja"
    mwin.close()
    print(f"Saved screenshots to: {out_dir.resolve()}")
    return 1 if any_clipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
