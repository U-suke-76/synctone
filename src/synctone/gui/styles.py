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

APPLY_MEASURED_BTN_QSS = """
    QPushButton {
        background-color: #1565c0;
        color: #ffffff;
        font-weight: bold;
        padding: 5px 8px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #1976d2;
    }
    QPushButton:disabled {
        background-color: #262635;
        color: #555566;
        border: 1px solid #333344;
    }
"""

APPLY_OBS_BTN_QSS = """
    QPushButton {
        background-color: #28283c;
        color: #bbbbdd;
        padding: 4px 6px;
        font-size: 11px;
        border: 1px solid #3d3d56;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #383854;
        color: #ffffff;
    }
    QPushButton:disabled {
        background-color: #1f1f2a;
        color: #555566;
        border: 1px solid #2a2a38;
    }
"""

TRIM_DELTA_BTN_QSS = """
    QPushButton {
        padding: 4px 0px;
        font-size: 11px;
        font-weight: 500;
        background-color: #232334;
        border: 1px solid #3d3d52;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #313148;
        border-color: #5c5c7a;
    }
"""

VERIFIER_DIALOG_QSS = """
    QDialog {
        background-color: #121218;
        color: #e0e0e0;
        font-family: 'Segoe UI', 'Meiryo', sans-serif;
    }
    QFrame#obs_hint_banner {
        background-color: #151e34;
        border: 1px solid #1e3a6a;
        border-radius: 6px;
        padding: 6px 10px;
    }
    QFrame#ctrl_panel {
        background-color: #181824;
        border: 1px solid #2a2a38;
        border-radius: 8px;
        padding: 10px;
    }
    QFrame#obs_hint_banner QLabel,
    QFrame#ctrl_panel QLabel, QFrame#ctrl_panel QRadioButton {
        background: transparent;
        border: none;
        padding: 0px;
    }
    QFrame#obs_trim_frame {
        background: transparent;
        border: none;
        border-top: 1px solid #28283a;
        padding-top: 6px;
    }
    QPushButton#trim_btn {
        padding: 5px 6px;
    }
    QPushButton {
        background-color: #232334;
        border: 1px solid #3d3d52;
        border-radius: 5px;
        padding: 6px 12px;
        color: #ffffff;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #313148;
        border-color: #5c5c7a;
    }
    QPushButton#play_btn {
        background-color: #00897b;
        border: 1px solid #26a69a;
        font-weight: bold;
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 6px;
    }
    QPushButton#play_btn:hover {
        background-color: #009688;
    }
    QPushButton#stop_btn {
        background-color: #c62828;
        border: 1px solid #e53935;
        font-weight: bold;
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 6px;
    }
    QPushButton#stop_btn:hover {
        background-color: #d32f2f;
    }
    QPushButton#auto_measure_btn {
        background-color: #1565c0;
        border: 1px solid #42a5f5;
        font-weight: bold;
        font-size: 12px;
        padding: 7px 14px;
        border-radius: 6px;
    }
    QPushButton#auto_measure_btn:hover {
        background-color: #1976d2;
    }
    QPushButton#auto_measure_btn:disabled {
        background-color: #242434;
        border: 1px solid #323246;
        color: #66667a;
    }
    QPushButton#apply_result_btn {
        background-color: #2e7d32;
        border: 1px solid #66bb6a;
        font-weight: bold;
        padding: 6px 14px;
        border-radius: 5px;
    }
    QPushButton#apply_result_btn:hover {
        background-color: #388e3c;
    }
    QPushButton#apply_result_btn:disabled {
        background-color: #242434;
        border: 1px solid #323246;
        color: #66667a;
    }
    QFrame#result_frame {
        background-color: #14141f;
        border: 1px solid #2b2b40;
        border-radius: 6px;
        padding: 6px 10px;
    }
    QSpinBox#obs_delay_spin {
        background-color: #14141f;
        border: 1px solid #3d3d52;
        border-radius: 4px;
        padding: 3px 6px;
        color: #ffffff;
        font-weight: bold;
    }
    QRadioButton {
        color: #ccccdd;
        font-size: 12px;
        font-weight: bold;
        spacing: 6px;
    }
    QRadioButton::indicator {
        width: 14px;
        height: 14px;
        border-radius: 7px;
        border: 2px solid #666680;
        background-color: #181824;
    }
    QRadioButton::indicator:checked {
        border: 2px solid #00e5ff;
        background-color: #00e5ff;
    }
    QMessageBox QPushButton {
        min-width: 72px;
        padding: 6px 14px;
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
        width: 14px;
        margin-top: -4px;
        margin-bottom: -4px;
        border-radius: 7px;
    }
"""


def level_bar_style(color: str) -> str:
    """Stylesheet for the live input level meter with the given chunk color."""
    return (
        "QProgressBar { border: 1px solid #2a2a38; border-radius: 5px; background-color: #161620; min-height: 14px; }"
        f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}"
    )
