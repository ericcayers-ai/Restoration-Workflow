"""Restoration Workflow backend.

Local-first photo restoration engine. See docs/ARCHITECTURE.md in the repo root
for the design this package implements.
"""

__version__ = "0.4.0"

# REST/WebSocket contract version (semver'd independently of the package once
# Phase 6 stabilizes it; pre-1.0 the API may change between releases). Still
# 0.1.0: this release only adds endpoints (auto-order, workflow export/import),
# it doesn't change any existing shape.
API_VERSION = "0.1.0"
