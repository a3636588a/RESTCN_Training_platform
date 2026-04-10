# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# List of all essential scripts for logical analysis
scripts = [
    'ui_v6.py',
    'train_gesture_cnn_v1.py',
    'export_weights_v2.py',
    'gen_cnn_lib.py',
    'gen_cnn_model_header.py',
    'gen_dynamic_model_header.py',
    'detect_gesture_universal_manual_holdavg_v5.py'
]

a = Analysis(
    scripts,
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'sklearn.utils._typedefs',
        'sklearn.neighbors.typedefs',
        'sklearn.utils._heap',
        'sklearn.utils._sorting',
        'sklearn.utils._vector_sentinel'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
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
