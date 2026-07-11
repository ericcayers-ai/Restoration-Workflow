"""Human-editable ``.txt`` workflow files.

A workflow is a versioned pipeline spec (``executor.PipelineSpec``) — the exact
same JSON the API, presets and the Advanced pipeline builder already speak —
written to a plain ``.txt`` file with a short comment header a person can read
before opening it in an editor. Reusing the pipeline JSON verbatim means the
``.txt`` format inherits every validation rule and every future pipeline
feature (multi-input DAGs, pinning, params) for free; this module adds nothing
but a header and a strip-comments pass, not a second schema to keep in sync.

Lines beginning with ``#`` before the JSON body are a header and are discarded
on import — the body is otherwise exactly what ``PipelineSpec.to_dict()``
already produces.
"""

from __future__ import annotations

import json

from .errors import PipelineValidationError
from .executor import PipelineSpec, parse_pipeline
from .registry import NodeRegistry

_HEADER_PREFIX = "#"


def serialize_workflow(
    spec: PipelineSpec, *, name: str = "", description: str = ""
) -> str:
    """Render a pipeline as a commented, human-readable .txt document."""
    lines = ["# Restoration Workflow — saved workflow"]
    if name:
        lines.append(f"# name: {name}")
    if description:
        lines.append(f"# description: {description}")
    lines.append(
        "# This file is JSON with a comment header. Edit the body with care: "
        "each node needs a unique id and a type this app recognises."
    )
    body = json.dumps(spec.to_dict(), indent=2)
    return "\n".join(lines) + "\n" + body + "\n"


def parse_workflow(text: str, registry: NodeRegistry) -> PipelineSpec:
    """Parse and validate a .txt workflow, stripping its comment header."""
    body_lines = [
        line for line in text.splitlines() if not line.lstrip().startswith(_HEADER_PREFIX)
    ]
    body = "\n".join(body_lines).strip()
    if not body:
        raise PipelineValidationError("workflow file has no pipeline body")
    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PipelineValidationError(f"workflow file is not valid JSON: {exc}") from exc
    return parse_pipeline(document, registry)
