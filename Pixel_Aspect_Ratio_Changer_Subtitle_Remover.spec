# -*- mode: python ; coding: utf-8 -*-
# Pixel Aspect Ratio Changer + Subtitle Remover — PyInstaller build spec

import os, sys
try:
    spec_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # __file__ not set when PyInstaller exec()s the spec with --clean
    spec_dir = os.getcwd()

a = Analysis(
    ['Pixel_Aspect_Ratio_Changer_Subtitle_Remover.py'],
    pathex=[spec_dir],
    binaries=[
        ('mp4box.exe', '.'),
        ('msvcr90.dll', '.'),
        ('avcodec-58.dll', '.'),
        ('avdevice-58.dll', '.'),
        ('avfilter-7.dll', '.'),
        ('avformat-58.dll', '.'),
        ('avutil-56.dll', '.'),
        ('js.dll', '.'),
        ('libcryptoMD.dll', '.'),
        ('libeay32.dll', '.'),
        ('libgpac.dll', '.'),
        ('libsslMD.dll', '.'),
        ('libx264-142.dll', '.'),
        ('OpenSVCDecoder.dll', '.'),
        ('postproc-55.dll', '.'),
        ('ssleay32.dll', '.'),
        ('swresample-3.dll', '.'),
        ('swscale-5.dll', '.'),
    ],
    datas=[],
    hiddenimports=['win32gui', 'win32con'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.dnd'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Pixel Aspect Ratio Changer + Subtitle Remover',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_window=False,
    icon=None,
    uac_admin=False,
)
