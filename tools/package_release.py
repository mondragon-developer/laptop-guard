"""Package only the application and public guide; smoke-test an isolated copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guard_runtime.version import VERSION

TARGETS = {
    "windows-x64": ("win32", "AMD64", "LaptopGuard.exe", "windows"),
    "macos-apple-silicon": ("darwin", "arm64", "LaptopGuard.app", "macos"),
    "macos-intel": ("darwin", "x86_64", "LaptopGuard.app", "macos"),
}
PRIVATE_NAMES = {"guard_config.json", "auto_guard.json", "logs", "videos", "__pycache__"}


def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if any(part in PRIVATE_NAMES for part in Path(name).parts):
                raise ValueError(f"Private runtime file in archive: {name}")
        if archive.testzip() is not None:
            raise ValueError("Corrupt release ZIP")


def build_package(target, dist, output):
    expected_os, expected_arch, app_name, guide = TARGETS[target]
    if sys.platform != expected_os or platform.machine().lower() != expected_arch.lower():
        raise RuntimeError(f"Build {target} on its native OS and architecture")
    app = dist / app_name
    if not app.exists():
        raise FileNotFoundError(app)
    output.mkdir(parents=True, exist_ok=True)
    name = f"LaptopGuard-{VERSION}-{target}"
    archive = output / f"{name}.zip"
    with tempfile.TemporaryDirectory(prefix="laptop-guard-package-") as temporary:
        stage = Path(temporary) / name
        stage.mkdir()
        staged_app = stage / app_name
        if app.is_dir():
            shutil.copytree(app, staged_app, symlinks=True)
        else:
            shutil.copy2(app, staged_app)
        shutil.copy2(ROOT / "release" / f"READ-ME-FIRST-{guide}.txt", stage / "READ-ME-FIRST.txt")
        executable = staged_app if guide == "windows" else staged_app / "Contents/MacOS/LaptopGuard"
        report = Path(temporary) / "check.json"
        environment = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        subprocess.run([str(executable), "--check", "--check-output", str(report)],
                       cwd=stage, env=environment, check=True, timeout=60)
        result = json.loads(report.read_text(encoding="utf-8"))
        if result.get("status") != "ok" or result.get("version") != VERSION:
            raise RuntimeError(f"Executable check failed: {result}")
        if guide == "macos":
            # Preserve app symlinks, executable bits and the ad-hoc signature.
            subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                            str(stage), str(archive.resolve())], check=True)
        else:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                for source in sorted(stage.rglob("*")):
                    if source.is_file():
                        bundle.write(source, source.relative_to(stage.parent))
    validate_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Ready: {archive.name} ({archive.stat().st_size:,} bytes)")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--output", type=Path, default=ROOT / "release-artifacts")
    args = parser.parse_args()
    build_package(args.target, args.dist.resolve(), args.output.resolve())
