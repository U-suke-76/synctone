# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('sounddevice')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


excludes = [
    # Qt6 unused components (SyncTone only uses QtWidgets, QtGui, QtCore, and basic pyqtgraph dependencies)
    'PySide6.QtQuick',
    'PySide6.QtQuickWidgets',
    'PySide6.QtQml',
    'PySide6.QtQmlModels',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtVirtualKeyboard',
    'PySide6.QtDesigner',
    'PySide6.QtSql',
    'PySide6.QtTest',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtSpatialAudio',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
    'PySide6.QtHelp',
    'PySide6.QtPrintSupport',

    # SciPy unused subpackages (SyncTone only uses scipy.signal)
    'scipy.optimize',
    'scipy.sparse',
    'scipy.spatial',
    'scipy.stats',
    'scipy.integrate',
    'scipy.interpolate',
    'scipy.ndimage',
    'scipy.cluster',
    'scipy.io',
    'scipy.odr',

    # Python standard libraries unused in SyncTone
    # Note: Do NOT exclude standard library modules like 'email', 'unittest', 'pydoc', 'http', or 'xmlrpc'
    # because PyInstaller's pyi_rth_pkgres / pkg_resources / importlib.metadata and numpy/scipy
    # import them during startup on Python 3.11.
    'tkinter',
]

a = Analysis(
    ['run.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# Exclude unnecessary large binaries (e.g. software OpenGL ~20MB, QML/Quick, PDF, VirtualKeyboard)
excluded_binaries = {
    'opengl32sw.dll',
    'qt6quick.dll',
    'qt6qml.dll',
    'qt6qmlmodels.dll',
    'qt6qmlmeta.dll',
    'qt6qmlworkerscript.dll',
    'qt6pdf.dll',
    'qt6virtualkeyboard.dll',
    'qtvirtualkeyboardplugin.dll',
    'qpdf.dll',
}

import os
a.binaries = [x for x in a.binaries if os.path.basename(x[0]).lower() not in excluded_binaries]

# Exclude unused Qt translations (SyncTone uses its own lightweight i18n module)
a.datas = [
    x for x in a.datas
    if not (x[0].startswith('PySide6/translations') or x[0].startswith('PySide6\\translations'))
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SyncTone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
