# laptop_guard.spec - PyInstaller build for Windows and macOS.
# Produces LaptopGuard.exe (single file) on Windows and LaptopGuard.app
# (onedir bundle) on macOS from guard_app.py, which contains the whole
# first-run/settings/activation flow.
#
# Build with:  pyinstaller laptop_guard.spec --clean --noconfirm
import os
import sys

# Optional branding: bundled when present next to this spec.
datas = []
for icon in ("icon.ico", "icon.png"):
    if os.path.exists(icon):
        datas.append((icon, "."))

a = Analysis(
    ["guard_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # onedir: the .app starts without first unpacking ~150 MB to a temp
    # folder, and the input helper respawned from sys.executable is a
    # plain process instead of a second bootloader stage with its own
    # environment checks.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="LaptopGuard",
        debug=False,
        strip=False,
        upx=False,
        console=False,          # windowed app: no console window
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="LaptopGuard",
    )
    app = BUNDLE(
        coll,
        name="LaptopGuard.app",
        icon="icon.icns" if os.path.exists("icon.icns") else None,
        bundle_identifier="com.laptopguard.app",
        info_plist={
            # Without this string macOS kills the app on camera access.
            "NSCameraUsageDescription":
                "Laptop Guard records a short webcam clip when someone "
                "touches your laptop while the guard is active.",
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="LaptopGuard",
        debug=False,
        strip=False,
        upx=False,
        console=False,          # windowed app: no console window
        icon="icon.ico" if os.path.exists("icon.ico") else None,
    )
