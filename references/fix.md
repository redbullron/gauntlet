# Gauntlet fix

Commands use paths relative to the installed Gauntlet skill directory. Prefer an already registered `local-gauntlet` MCP server to preserve its existing project profiles and history. For a new CLI installation, read [bridge setup](bridge.md).

Use the `local-gauntlet` MCP tools. This is an installed local bridge, not a request to recreate it or launch conversation subagents.

Interpret the invocation as `[project] [task]`, optionally `writer=claude` or `writer=codex`, rounds, and minutes. Use the current conversation's task and decisions when the user says "this". If the target project or requested outcome is genuinely unknown, ask only for the missing information.

1. Call `gauntlet_projects`. Resolve the supplied project name or match the current project folder. A profile is a folder plus validation commands and shared context; If needed, register the user-selected folder with `gauntlet_register_project`. Preserve existing profile fields. Choose actual project checks, not a dummy command that always passes.
2. Prepare a self-contained task containing the objective, acceptance criteria, scope, relevant decisions, and any unresolved issues from this chat. Background reviewers do not inherit chat history. Include necessary handoff text rather than inaccessible file paths; omit credentials. Say when evidence is missing.
3. Call `gauntlet_start` with mode `fix`. Respect the requested writer; default to Codex. Defaults are five rounds and 60 minutes. The invocation authorizes this review/repair job and the existing CLI usage it consumes. One bridge job may run at a time; if busy, show it instead of cancelling it or spawning a duplicate.
4. Save the returned job ID in the conversation. Poll `gauntlet_status` about every 20-30 seconds using short interruptible waits, and keep the user informed of meaningful phase changes. If the user wants to leave, report the ID; the worker continues locally while the client is closed. No unsolicited scheduled automation is needed.
5. When terminal, call `gauntlet_result`. Report actual status, rounds, validation, unresolved findings, workspace, and patch. Only `approved` means both agreed and configured validation requirements were met. `review_complete`, `needs_validation`, `needs_input`, limits, errors and cancellation are not approval.

Changes stay in an isolated copy. Applying a patch to the source, merging, deploying, and publishing are separate actions; do them only when requested. Do not recursively launch this skill from a Gauntlet worker.

If MCP is unavailable, use the installed CLI at `scripts/bridge/bridge.py` through Python. Run `--help` for arguments. Write long task text to a local task file and use `--task-file`; do not interpolate chat text into shell commands. Otherwise ask the user to reload the client so the registered MCP server is discovered.
