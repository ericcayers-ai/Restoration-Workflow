"""Shared PyInstaller onedir bundling for desktop installers.

Produces ``backend/dist/RestorationWorkflow/`` (Windows: ``.exe`` beside
``_internal/``; macOS/Linux: binary of the same name). Platform-specific
installer scripts wrap this folder into Setup.exe / .dmg / .AppImage.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

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

# Packages whose non-.py assets PyInstaller's analysis won't discover alone.
COLLECT_ALL = [
    "torch",
    "spandrel",
    "cv2",
    "safetensors",
    "huggingface_hub",
    "transformers",
    "tokenizers",
    "uvicorn",
]

LICENSE_BUNDLE = (
    REPO_ROOT / "LICENSE",
    REPO_ROOT / "NOTICE",
    REPO_ROOT / "THIRD_PARTY_NOTICES.md",
)

APP_DISPLAY_NAME = "Restoration Workflow"
APP_VERSION = "0.6.1"
APP_IDENTIFIER = "ai.ericcayers.restoration-workflow"


def binary_name() -> str:
    return "RestorationWorkflow.exe" if platform.system() == "Windows" else "RestorationWorkflow"


def data_sep() -> str:
    """PyInstaller ``--add-data`` uses ``;`` on Windows and ``:`` elsewhere."""
    return ";" if platform.system() == "Windows" else ":"


def stage_user_files(app_dir: Path) -> None:
    """Copy launcher helpers, short readme, and licence notices into the onedir."""
    if platform.system() == "Windows":
        if not RUN_BAT.is_file():
            raise FileNotFoundError(f"missing launcher: {RUN_BAT}")
        shutil.copy2(RUN_BAT, app_dir / "Run.bat")
        if README_TXT.is_file():
            shutil.copy2(README_TXT, app_dir / "README.txt")
    else:
        readme = PACKAGING_DIR / "README-DESKTOP.txt"
        if readme.is_file():
            shutil.copy2(readme, app_dir / "README.txt")
    missing = [p.name for p in LICENSE_BUNDLE if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"missing licence bundle files: {', '.join(missing)}")
    for src in LICENSE_BUNDLE:
        shutil.copy2(src, app_dir / src.name)


def run_pyinstaller() -> None:
    import PyInstaller.__main__

    if not (FRONTEND_DIST / "index.html").exists():
        raise FileNotFoundError(
            f"no frontend build at {FRONTEND_DIST}\n"
            "Run 'npm run build' in frontend/ first."
        )

    sep = data_sep()
    args = [
        "--name",
        "RestorationWorkflow",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--paths",
        str(BACKEND_DIR / "src"),
        "--add-data",
        f"{RULE_TABLE_DATA}{sep}restoration/core/data",
        "--add-data",
        f"{FRONTEND_DIST}{sep}frontend_dist",
        "--hidden-import",
        "websockets",
        "--hidden-import",
        "httptools",
        "--hidden-import",
        "multipart",
    ]
    for pkg in COLLECT_ALL:
        args += ["--collect-all", pkg]
    args.append(str(LAUNCHER))

    print("Running PyInstaller:\n  " + " ".join(args))
    # Ensure dist/build clean for reproducible CI folders.
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    PyInstaller.__main__.run(args)

    exe = APP_DIR / binary_name()
    if not exe.is_file():
        raise FileNotFoundError(f"expected binary missing at {exe}")

    stage_user_files(APP_DIR)
    print(f"Onedir bundle ready: {APP_DIR} ({_dir_mb(APP_DIR)} MB)")


def _dir_mb(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total // (1024 * 1024)


def ensure_icon_png(dest: Path, size: int = 256) -> Path:
    """Write a simple solid-colour PNG (no external deps) for .desktop / DMG."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return dest
    # Deep teal matching the product feel; not a purple AI cliché.
    r, g, b = 0x1A, 0x5C, 0x4E
    raw = b""
    for _y in range(size):
        raw += b"\x00"  # filter none
        for _x in range(size):
            raw += bytes((r, g, b, 255))
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    dest.write_bytes(png)
    return dest


def main() -> int:
    try:
        run_pyinstaller()
    except Exception as exc:  # noqa: BLE001 — CLI entry
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
