"""Serving the built frontend from the same process (ARCHITECTURE.md sections
1 and 7): "restore serve starts just the FastAPI backend... the identical
frontend build also works headless." One codebase, two deployment shapes —
this module is what makes `restore serve` a complete app by itself, not just
an API a separately-run dev server has to sit in front of.

Locating the build checks three places, in order: an explicit
`RESTORE_FRONTEND_DIST` override; a PyInstaller-frozen bundle's extraction
directory (the packaged desktop build — packaging/build_exe.py stages
`frontend/dist` there under `frontend_dist`); and finally a sibling
`frontend/dist` found by walking up from this file, which is exactly right
for this repo's own dev layout (a `pip install -e` checkout next to
`frontend/`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def find_frontend_dist() -> Path | None:
    override = os.environ.get("RESTORE_FRONTEND_DIST")
    if override:
        path = Path(override)
        return path if (path / "index.html").exists() else None

    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        candidate = Path(frozen_base) / "frontend_dist"
        if (candidate / "index.html").exists():
            return candidate

    # backend/src/restoration/api/frontend.py -> repo root is four levels up.
    repo_root = Path(__file__).resolve().parents[4]
    candidate = repo_root / "frontend" / "dist"
    return candidate if (candidate / "index.html").exists() else None


def mount_frontend(app: FastAPI) -> bool:
    """Mount the built frontend at ``/`` if one is available.

    Registered after every ``/api/...`` route, so it only ever serves paths
    those routes didn't claim — Starlette matches routes in registration
    order, and a mount is a fallback here, not a shadow. Returns whether a
    build was found, purely so ``restore serve`` can log which mode it's in.
    """
    dist = find_frontend_dist()
    if dist is None:
        return False
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True
