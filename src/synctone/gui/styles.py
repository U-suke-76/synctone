"""Shared Qt stylesheet definitions for the SyncTone GUI."""

DARK_THEME_QSS = """
    QMainWindow, QWidget {
        background-color: #121218;
        color: #e0e0e0;
        font-family: 'Segoe UI', 'Meiryo', sans-serif;
        font-size: 10pt;
    }
    QGroupBox {
        border: 1px solid #2a2a38;
        border-radius: 8px;
        margin-top: 8px;
        padding-top: 12px;
        font-weight: bold;
        color: #82aaff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
    }

    QPushButton {
        background-color: #1e1e2c;
        border: 1px solid #3d3d52;
        border-radius: 6px;
        padding: 6px 14px;
        color: #ffffff;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #2b2b3f;
        border-color: #5c5c7a;
    }
    QPushButton:pressed {
        background-color: #161622;
    }
    QPushButton:checked {
        background-color: #283593;
        border-color: #5c6bc0;
        color: #ffffff;
        font-weight: bold;
    }
    QPushButton:disabled {
        background-color: #14141c;
        color: #555566;
        border-color: #22222e;
    }
    QPushButton#measure_btn {
        background-color: #00897b;
        border: 1px solid #26a69a;
        font-size: 14px;
        font-weight: bold;
        padding: 8px 12px;
        border-radius: 8px;
    }
    QPushButton#measure_btn:hover {
        background-color: #009688;
        border-color: #4db6ac;
    }
    QPushButton#apply_btn {
        background-color: #1976d2;
        border: 1px solid #42a5f5;
        font-size: 14px;
        font-weight: bold;
        padding: 8px 18px;
        border-radius: 6px;
    }
    QPushButton#apply_btn:hover {
        background-color: #2196f3;
        border-color: #64b5f6;
    }
    QPushButton#verifier_btn {
        background-color: #3949ab;
        border: 1px solid #5c6bc0;
        font-size: 13px;
        font-weight: bold;
        padding: 10px 16px;
        border-radius: 8px;
    }
    QPushButton#verifier_btn:hover {
        background-color: #3f51b5;
        border-color: #7986cb;
    }
    QComboBox, QLineEdit {
        background-color: #1a1a24;
        border: 1px solid #333344;
        border-radius: 5px;
        padding: 5px 8px;
        color: #ffffff;
    }
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #82aaff;
    }
    QSpinBox, QDoubleSpinBox {
        background-color: #1a1a24;
        border: 1px solid #333344;
        border-radius: 5px;
        padding: 4px 22px 4px 8px;
        color: #ffffff;
        font-weight: bold;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 18px;
        background-color: #2b2b3f;
        border-left: 1px solid #333344;
        border-bottom: 1px solid #333344;
        border-top-right-radius: 4px;
    }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
        background-color: #3d3d5a;
    }
    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {
        background-color: #1a1a24;
    }
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 18px;
        background-color: #2b2b3f;
        border-left: 1px solid #333344;
        border-bottom-right-radius: 4px;
    }
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
        background-color: #3d3d5a;
    }
    QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
        background-color: #1a1a24;
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QProgressBar {
        border: 1px solid #2a2a38;
        border-radius: 6px;
        text-align: center;
        background-color: #161620;
        min-height: 28px;
        font-weight: bold;
        color: #ffffff;
        font-size: 11px;
    }
    QProgressBar::chunk {
        background-color: #00b0ff;
        border-radius: 5px;
    }
    QSlider::groove:horizontal {
        border: 1px solid #2a2a38;
        height: 6px;
        background: #1a1a24;
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal {
        background: #82aaff;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #ffffff;
        border: 1px solid #82aaff;
        width: 16px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 8px;
    }
    QStatusBar {
        background-color: #0d0d12;
        color: #888899;
    }
"""

# Rounded background used by the result / adjustment / apply panels
PANEL_FRAME_QSS = "background-color: #1a1a26; border-radius: 6px; padding: 4px;"


def level_bar_style(color: str) -> str:
    """Stylesheet for the live input level meter with the given chunk color."""
    return (
        "QProgressBar { border: 1px solid #2a2a38; border-radius: 5px; background-color: #161620; min-height: 14px; }"
        f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}"
    )
