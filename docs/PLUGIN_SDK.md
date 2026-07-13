# Plugin SDK

Third-party restoration models ship as a directory under `plugins/<name>/` with no
core-repo changes (ARCHITECTURE.md §3, §7).

## Layout

```
plugins/
  my-restorer/
    manifest.json
    plugin.py
```

## manifest.json

```json
{
  "name": "my-restorer",
  "version": "1.0.0",
  "module": "plugin.py",
  "nodes": ["MyRestorerNode"]
}
```

## plugin.py

Subclass `BaseRestorationNode` from `restoration.core.types` (or `SpandrelNode`
from `restoration.nodes._torch` for spandrel-backed image→image models). See
`plugins/example/` for a working orchestration plugin.

## Discovery

On startup, `NodeRegistry.discover_plugins()` loads every `plugins/*/manifest.json`
under the data directory (`RESTORE_HOME/plugins` or the portable `data/plugins`
folder). Broken plugins are logged in `/api/health` → `plugin_errors` and skipped.

## CLI

```bash
restore plugin list
```

Lists in-box nodes vs third-party plugins.
