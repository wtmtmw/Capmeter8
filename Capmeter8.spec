# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Regular\\Documents\\TMW_Documents\\Git_repository\\Capmeter8\\src\\Capmeter8\\Capmeter8.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Regular\\Documents\\TMW_Documents\\Git_repository\\Capmeter8\\src\\Capmeter8\\caplib.dll', '.'), ('C:\\Users\\Regular\\Documents\\TMW_Documents\\Git_repository\\Capmeter8\\src\\Capmeter8\\ui_Cap8MainWindow.ui', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Capmeter8',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
