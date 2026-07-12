"""Build the Windows desktop distributable: RestorationWorkflow.exe + its
dependencies in one folder, run via PyInstaller.

This is `--onedir`, not `--onefile`: the app bundles torch, spandrel and
opencv, so a onefile build would re-extract several hundred megabytes into a
temp directory on every single launch. A folder a user extracts once and
launches is the standard shape for a torch-based desktop app for exactly this
reason (it's what ComfyUI's and Automatic1111's own "portable" Windows
builds do).

Usage (from the `backend/` directory, with the `frontend/dist` build
already produced by `npm run build`):

    python packaging/build_exe.py

Output lands in `backend/dist/RestorationWorkflow/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
RULE_TABLE_DATA = BACKEND_DIR / "src" / "restoration" / "core" / "data"
LAUNCHER = BACKEND_DIR / "src" / "restoration" / "launcher.py"

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
