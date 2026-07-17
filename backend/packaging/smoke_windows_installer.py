"""Smoke-test a built Windows Inno Setup installer (release workflow).

Checks the installer exists and is a PE executable of plausible size.
Optionally inspects the onedir folder that fed the installer.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

_PACKAGING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = _PACKAGING_DIR.parent
DIST_DIR = BACKEND_DIR / "dist"

REQUIRED_ONEDIR = {
    "RestorationWorkflow.exe",
    "Run.bat",
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
}


def _is_pe(path: Path) -> bool:
    with path.open("rb") as fh:
        if fh.read(2) != b"MZ":
            return False
        fh.seek(0x3C)
        pe_offset = struct.unpack("<I", fh.read(4))[0]
        fh.seek(pe_offset)
        return fh.read(4) == b"PE\0\0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "installer",
        nargs="?",
        default="",
        help="Path to Setup .exe (default: latest Matching dist/*.exe)",
    )
    args = parser.parse_args()

    if args.installer:
        installer = Path(args.installer)
    else:
        candidates = sorted(DIST_DIR.glob("RestorationWorkflow-Setup-*-windows-x64.exe"))
        if not candidates:
            print(f"error: no installer found under {DIST_DIR}", file=sys.stderr)
            return 1
        installer = candidates[-1]

    if not installer.is_file():
        print(f"error: installer not found: {installer}", file=sys.stderr)
        return 1

    size_mb = installer.stat().st_size / (1024 * 1024)
    if size_mb < 50:
        print(f"error: installer suspiciously small ({size_mb:.1f} MB)", file=sys.stderr)
        return 1
    if not _is_pe(installer):
        print(f"error: not a PE executable: {installer}", file=sys.stderr)
        return 1

    app_dir = DIST_DIR / "RestorationWorkflow"
    if app_dir.is_dir():
        missing = sorted(n for n in REQUIRED_ONEDIR if not (app_dir / n).is_file())
        if missing:
            print("error: onedir missing files:", file=sys.stderr)
            for m in missing:
                print(f"  - {m}", file=sys.stderr)
            return 1
        data_hits = list(app_dir.rglob("instructir_prompts.json")) + list(
            app_dir.rglob("rule_table.json")
        )
        if len(data_hits) < 2:
            print(f"error: packaged JSON data not found (found {data_hits})", file=sys.stderr)
            return 1

    print(f"windows installer smoke OK: {installer.name} ({size_mb:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
