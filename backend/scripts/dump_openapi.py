"""Dump the OpenAPI schema as JSON to stdout for the frontend codegen script."""
import json
import sys

from restoration.api.app import create_app

app = create_app()
schema = app.openapi()
json.dump(schema, sys.stdout, indent=2)
