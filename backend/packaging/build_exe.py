"""Build the Windows desktop distributable and Inno Setup installer.

Builds the PyInstaller onedir via ``bundle_common``, then wraps it with
Inno Setup into ``RestorationWorkflow-Setup-<ver>-windows-x64.exe``.

Usage (from ``backend/``, after ``npm run build`` in ``frontend/``):

    python packaging/build_exe.py

Outputs:
  ``backend/dist/RestorationWorkflow/`` — onedir folder
  ``backend/dist/RestorationWorkflow-Setup-*-windows-x64.exe`` — installer
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

import bundle_common  # noqa: E402
from make_windows_installer import build_windows_installer  # noqa: E402

# Re-export for greppable docs / accidental imports.
COLLECT_ALL = bundle_common.COLLECT_ALL
LICENSE_BUNDLE = bundle_common.LICENSE_BUNDLE
APP_DIR = bundle_common.APP_DIR
DIST_DIR = bundle_common.DIST_DIR


def main() -> int:
    try:
        bundle_common.run_pyinstaller()
        installer = build_windows_installer(bundle_common.APP_DIR, bundle_common.DIST_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Windows installer: {installer} ({installer.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
