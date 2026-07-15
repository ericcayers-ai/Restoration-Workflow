"""Smoke-test a built RestorationWorkflow-windows.zip (release workflow).

Checks for the exe, Run.bat, licence bundle, and packaged JSON data without
launching a GUI browser session.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REQUIRED_NAMES = {
    "RestorationWorkflow/RestorationWorkflow.exe",
    "RestorationWorkflow/Run.bat",
    "RestorationWorkflow/LICENSE",
    "RestorationWorkflow/NOTICE",
    "RestorationWorkflow/THIRD_PARTY_NOTICES.md",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "zip_path",
        nargs="?",
        default=str(
            Path(__file__).resolve().parents[1]
            / "dist"
            / "RestorationWorkflow-windows.zip"
        ),
    )
    args = parser.parse_args()
    zip_path = Path(args.zip_path)
    if not zip_path.is_file():
        print(f"error: zip not found: {zip_path}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        missing = sorted(n for n in REQUIRED_NAMES if n not in names)
        if missing:
            print("error: zip missing entries:", file=sys.stderr)
            for m in missing:
                print(f"  - {m}", file=sys.stderr)
            return 1

        # Data may live under _internal/ depending on PyInstaller layout.
        data_hits = [
            n
            for n in names
            if n.endswith("restoration/core/data/instructir_prompts.json")
            or n.endswith("restoration/core/data/rule_table.json")
        ]
        if len(data_hits) < 2:
            print(
                "error: packaged JSON data not found inside zip "
                f"(found {data_hits})",
                file=sys.stderr,
            )
            return 1

        # InstructIR deps should appear somewhere in the onedir tree.
        has_transformers = any("transformers" in n.lower() for n in names)
        if not has_transformers:
            print(
                "warning: no 'transformers' path in zip — verify COLLECT_ALL",
                file=sys.stderr,
            )

    print(f"windows zip smoke OK: {zip_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
