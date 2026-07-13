"""Restoration Workflow backend.

Local-first photo restoration engine. See docs/ARCHITECTURE.md in the repo root
for the design this package implements.
"""

__version__ = "0.5.0"

# REST/WebSocket contract version — stabilized at 1.0.0 for third-party plugins
# and automation scripts (ROADMAP.md Phase 6). Breaking API changes require a
# major bump; additive endpoints are minor bumps.
API_VERSION = "1.0.0"
