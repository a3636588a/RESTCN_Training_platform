# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all

def get_rich_unicode_modules():
    try:
        import rich._unicode_data
        path = os.path.dirname(rich._unicode_data.__file__)
        return [f"rich._unicode_data.{f[:-3]}" for f in os.listdir(path) if f.endswith(".py") and not f.startswith("__")]
    except Exception:
        return []

block_cipher = None

scripts = [
    'gesture_tool_ui.py',
    'training_cnn.py',
    'training_ds_tcn.py',
    'export_weights_v2.py',
    'gen_cnn_lib.py',
    'tool_operations.py',
    'gen_cnn_model_header.py',
    'gen_dynamic_model_header.py',
    'detection_model.py'
]

# Proactively collect all submodules for the main ML and UI libraries
hidden_imports = [
    'sklearn.utils._typedefs',
    'sklearn.neighbors.typedefs',
    'sklearn.utils._heap',
    'sklearn.utils._sorting',
    'sklearn.utils._vector_sentinel',
    'sklearn.utils._cython_blas',
    'sklearn.neighbors._partition_nodes',
    'sklearn.neighbors._quad_tree',
    'sklearn.tree._utils',
    'serial',
    'joblib',
    'numpy',
    'rich',
    'rich.console',
    'rich.logging',
    'rich.table',
    'rich.progress',
]

# Manually add all unicode versions for 'rich' to avoid runtime errors
hidden_imports += get_rich_unicode_modules()

# Add major ML library submodules
hidden_imports += collect_submodules('sklearn')
hidden_imports += collect_submodules('pandas')
hidden_imports += collect_submodules('scipy')
hidden_imports += collect_submodules('joblib')

# Collect data files for rich separately
rich_datas = collect_data_files('rich')

# PySide6 6.10 ships with a newer MSVC runtime than the Python installation.
# Keep one matching runtime set at the bundle root; otherwise Windows can load
# Python's older DLLs first and QtCore fails with WinError 127.
import PySide6
qt_runtime_dir = os.path.dirname(PySide6.__file__)
qt_runtime_names = {
    'concrt140.dll',
    'msvcp140.dll',
    'msvcp140_1.dll',
    'msvcp140_2.dll',
    'msvcp140_codecvt_ids.dll',
    'vcruntime140.dll',
    'vcruntime140_1.dll',
}
# The Codex shell PATH contains Poppler's ICU 78. Qt6Core on Windows links to
# the system ICU API instead, so bundling Poppler's same-named DLL causes a
# procedure-not-found failure before the UI can start.
incompatible_icu_names = {'icuuc.dll', 'icudt78.dll'}

a = Analysis(
    scripts,
    pathex=[],
    binaries=[],
    datas=rich_datas,
    hiddenimports=list(set(hidden_imports)), # De-duplicate
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Analysis also discovers runtime copies from Python and ML packages. Replace
# every plain-name copy with PySide6's coherent set to avoid mixed versions.
a.binaries = [
    entry for entry in a.binaries
    if os.path.basename(entry[0]).lower() not in qt_runtime_names | incompatible_icu_names
]
a.binaries += [
    (name, os.path.join(qt_runtime_dir, name), 'BINARY')
    for name in sorted(qt_runtime_names)
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ML_Station',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
