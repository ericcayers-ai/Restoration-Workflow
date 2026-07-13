"""Router override telemetry (ROADMAP.md Phase 5).

Records when Studio/Simple Mode users change the auto-picked pipeline before
running — the signal a learned router would need. Stored as JSON lines under
the data directory.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .weights import default_data_dir


def log_routing_override(
    *,
    original_chain: list[str],
    final_chain: list[str],
    source: str = "studio",
) -> None:
    if original_chain == final_chain:
        return
    path = default_data_dir() / "telemetry" / "routing_overrides.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "ts": time.time(),
        "source": source,
        "original": original_chain,
        "final": final_chain,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
