# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Mini AI Coding Agent.

Build:  python -m PyInstaller agent.spec --clean --noconfirm
Output: dist/agent.exe (one-file console app)

Runtime files NOT bundled (kept next to the exe on purpose):
- tokens.json : credentials; bundling secrets into the exe would expose them
- chats/      : persisted chat sessions
- logs/       : agent log output
"""

a = Analysis(
    ["agent.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "certifi",          # requests' default CA bundle
        "httpx",            # used by cohere.ClientV2
        "cohere",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "numpy", "pandas", "PIL",
        "pytest", "IPython", "notebook",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # interactive REPL needs a console
    icon=None,
)
