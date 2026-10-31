# Gauntlet stop

Commands use paths relative to the installed Gauntlet skill directory. Prefer an already registered `local-gauntlet` MCP server to preserve its existing project profiles and history. For a new CLI installation, read [bridge setup](bridge.md).

Use the `local-gauntlet` MCP tools. Resolve an explicit job ID, the active job for this conversation, or the sole active job returned by `gauntlet_status`. If a sole active run belongs to a different project than the user's stated target, clarify rather than cancel the wrong project.

Call `gauntlet_cancel` once. A `cancellation_requested` response is not proof the worker has stopped. Poll `gauntlet_status` until the worker acknowledges cancellation or returns another terminal state, then report that actual state and the retained workspace. Do not delete job files, revert source files, kill unrelated processes, or cancel non-Gauntlet chats.

CLI fallback: Python with `scripts/bridge/bridge.py cancel job-id`, followed by `status job-id`.
