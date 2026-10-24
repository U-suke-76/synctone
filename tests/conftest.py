"""Shared pytest configuration and safe Qt/PySide6 exit handling on Windows offscreen CI."""

import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SYNCTONE_TEST_DUMMY_AUDIO", "1")

_SESSION_EXIT_STATUS = 0


def pytest_sessionfinish(session, exitstatus):
    """Record the final pytest session exit status and flush Qt events."""
    global _SESSION_EXIT_STATUS
    _SESSION_EXIT_STATUS = int(exitstatus)
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(None)
        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()
            app.processEvents()
    except Exception:
        pass


def pytest_unconfigure(config):
    """Ensure clean process termination on Windows headless CI after pytest finishes reporting.

    On Windows headless CI (QT_QPA_PLATFORM=offscreen), PySide6 / pyqtgraph / PortAudio
    C++ destructors during Py_FinalizeEx can raise 0xC0000005 after pytest has already
    printed '31 passed' and finished all reporting.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_SESSION_EXIT_STATUS)
