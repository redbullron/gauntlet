# Review bridge setup

The bundled `scripts/bridge/bridge.py` provides review/fix, project profiles, status/results, cancellation, and an optional MCP stdio server. Python 3.11+, Git, and compatible native Codex and Claude CLIs with existing logins are required. Worker runs consume CLI usage.

If `local-gauntlet` is already registered, keep using it and its existing project/history database. Do not replace its configuration or migrate its state as part of a skill update.

For a new installation, copy `scripts/bridge/config.example.json` to `scripts/bridge/config.json` and set the two absolute native executable paths. Do not put credentials in this file. Optional per-agent `model` and `effort` fields select settings supported by that CLI. The sample leaves Codex's model at its CLI default and selects the `opus` alias for Claude.

From the installed skill directory:

```sh
python scripts/bridge/bridge.py doctor
python scripts/bridge/bridge.py --help
python scripts/bridge/test_bridge.py
```

`doctor` reports executable existence, Git, and local profiles; it does not test authentication, quota, or CLI flag compatibility. Tests use mocks and local processes without paid inference. Inspect CLI help if a worker reports unsupported flags; do not remove confinement options as a workaround.

The bridge is usable directly through its CLI. For MCP integration, register a stdio server named `local-gauntlet` in your client's MCP settings with your absolute Python executable as `command` and `["/absolute/path/to/gauntlet/scripts/bridge/bridge.py", "mcp"]` as `args`. Preserve existing server entries; do not add a second server with that name. Both clients can point at the same bridge installation to share history.

New bridge state defaults to `scripts/bridge/state/`. Set `GAUNTLET_STATE_DIR` to an absolute private directory to keep it elsewhere; use the same setting in every caller that should share history. Spawn uses separate state and IDs. State, transcripts, local config, and project profiles must stay out of version control.

The bridge creates isolated source copies and unapplied patches. Configured checks can execute code: use trusted projects and local tests, never deployment commands. Snapshot exclusions do not guarantee secret removal. Windows process ownership has local test coverage; cross-platform behavior is not claimed as validated by this release.
