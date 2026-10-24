"""Shared pytest configuration and safe Qt/PySide6 exit handling on Windows offscreen CI."""

import os
import pytest
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SYNCTONE_TEST_DUMMY_AUDIO", "1")
pg.setConfigOptions(antialias=False, exitCleanup=False)


@pytest.fixture(scope="session")
def qapp():
    """Single session-wide QApplication instance kept alive throughout all GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.closeAllWindows()
    app.processEvents()
    qInstallMessageHandler(None)
