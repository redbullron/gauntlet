# Gauntlet review

Commands use paths relative to the installed Gauntlet skill directory. Prefer an already registered `local-gauntlet` MCP server to preserve its existing project profiles and history. For a new CLI installation, read [bridge setup](bridge.md).

Use the `local-gauntlet` MCP tools. Interpret the invocation as `[project] [review scope]`. Resolve the profile with `gauntlet_projects`, using the current project when unambiguous. For an unregistered folder, register the user-selected folder with meaningful local checks and preserve known context.

Call `gauntlet_start` with `mode="review"`, `max_rounds=1`, and a self-contained task including the relevant chat decisions and review scope. Reviewers do not inherit chat history. Never silently turn review-only into automatic fixes. This run may execute the configured project checks in the isolated copy; avoid deployment or operational checks.

Poll `gauntlet_status` around every 20-30 seconds. Read `gauntlet_result` on completion. Return the findings from both reviewers, their disagreements, and check results. Report approval only if state is `approved`. `review_complete` means reviews finished, not that the code passed. Retain the job ID so either client can retrieve it. Do not apply or deploy changes.

If MCP tools are missing, the local CLI is `scripts/bridge/bridge.py`. Use Python and `start --mode review`; put long task text in a file passed with `--task-file`.
