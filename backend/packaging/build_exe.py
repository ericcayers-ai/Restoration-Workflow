"""Build the Windows desktop distributable: RestorationWorkflow.exe + its
dependencies in one folder, run via PyInstaller, then zip it with an easy
``Run.bat`` launcher for GitHub Releases.

This is ``--onedir``, not ``--onefile``: the app bundles torch, spandrel and
opencv, so a onefile build would re-extract several hundred megabytes into a
temp directory on every single launch. A folder a user extracts once and
launches is the standard shape for a torch-based desktop app for exactly this
reason (it's what ComfyUI's and Automatic1111's own "portable" Windows
builds do).

Usage (from the ``backend/`` directory, with the ``frontend/dist`` build
already produced by ``npm run build``):

    python packaging/build_exe.py

Outputs:
  ``backend/dist/RestorationWorkflow/`` — onedir folder with ``Run.bat``
  ``backend/dist/RestorationWorkflow-windows.zip`` — release asset
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

import PyInstaller.__main__

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
RULE_TABLE_DATA = BACKEND_DIR / "src" / "restoration" / "core" / "data"
LAUNCHER = BACKEND_DIR / "src" / "restoration" / "launcher.py"
PACKAGING_DIR = Path(__file__).resolve().parent
RUN_BAT = PACKAGING_DIR / "Run.bat"
README_TXT = PACKAGING_DIR / "README-WINDOWS.txt"

DIST_DIR = BACKEND_DIR / "dist"
APP_DIR = DIST_DIR / "RestorationWorkflow"
ZIP_PATH = DIST_DIR / "RestorationWorkflow-windows.zip"

# Packages whose non-.py assets (compiled ops, arch metadata, cascade-adjacent
# resources) PyInstaller's import-following analysis won't discover on its own.
COLLECT_ALL = [
    "torch",
    "spandrel",
    "cv2",
    "safetensors",
    "huggingface_hub",
    "uvicorn",
]


def _stage_user_files(app_dir: Path) -> None:
    """Copy the double-click launcher and short readme next to the exe."""
    if not RUN_BAT.is_file():
        raise FileNotFoundError(f"missing launcher: {RUN_BAT}")
    shutil.copy2(RUN_BAT, app_dir / "Run.bat")
    if README_TXT.is_file():
        shutil.copy2(README_TXT, app_dir / "README.txt")


def _zip_app_dir(app_dir: Path, zip_path: Path) -> None:
    """Zip so extracting yields RestorationWorkflow/Run.bat at the top level."""
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(app_dir.parent).as_posix())


def main() -> int:
    if not (FRONTEND_DIST / "index.html").exists():
        print(
            f"error: no frontend build at {FRONTEND_DIST}\n"
            f"Run 'npm run build' in frontend/ first.",
            file=sys.stderr,
        )
        return 1

    args = [
        "--name", "RestorationWorkflow",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--paths", str(BACKEND_DIR / "src"),
        "--add-data", f"{RULE_TABLE_DATA};restoration/core/data",
        "--add-data", f"{FRONTEND_DIST};frontend_dist",
        "--hidden-import", "websockets",
        "--hidden-import", "httptools",
        "--hidden-import", "multipart",
    ]
    for pkg in COLLECT_ALL:
        args += ["--collect-all", pkg]
    args.append(str(LAUNCHER))

    print("Running PyInstaller:\n  " + " ".join(args))
    PyInstaller.__main__.run(args)

    if not (APP_DIR / "RestorationWorkflow.exe").is_file():
        print(f"error: expected exe missing at {APP_DIR}", file=sys.stderr)
        return 1

    _stage_user_files(APP_DIR)
    _zip_app_dir(APP_DIR, ZIP_PATH)
    print(f"Staged launcher: {APP_DIR / 'Run.bat'}")
    print(f"Release zip:     {ZIP_PATH} ({ZIP_PATH.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
