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
    'ui_v6.py',
    'train_gesture_cnn_v1.py',
    'export_weights_v2.py',
    'gen_cnn_lib.py',
    'gen_cnn_model_header.py',
    'gen_dynamic_model_header.py',
    'detect_gesture_universal_manual_holdavg_v5.py'
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CNN_Station_Breathe',
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
