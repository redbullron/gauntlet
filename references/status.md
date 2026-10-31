# Gauntlet status

Commands use paths relative to the installed Gauntlet skill directory. Prefer an already registered `local-gauntlet` MCP server to preserve its existing project profiles and history. For a new CLI installation, read [bridge setup](bridge.md).

Call `gauntlet_status` on the `local-gauntlet` MCP server. Use a supplied job ID or the relevant ID in this conversation. Without an ID, list recent jobs and identify the active run or the latest run for the current project. Do not assume the most recent job belongs to the current task if multiple projects are present.

For an active job, show project, round, phase, and ID. For a completed job, call `gauntlet_result` and summarize actual verdict, test outcomes, unresolved findings, and report/patch paths. An `approved` state applies only to the recorded workspace revision and configured checks. Mention `source_unchanged=false` before anyone considers applying its patch.

`source_unchanged` was recorded when the job finished, not checked at the moment you read status. Do not claim a patch will apply cleanly from that flag; a later apply requires a fresh source check and `git apply --check`.

This command only reads status/results. Do not start or rerun jobs. If the user explicitly asks to watch, follow progress with short waits and bounded status calls; do not silently schedule an automation.

CLI fallback: run Python with `scripts/bridge/bridge.py status [job-id]`, then `result job-id` for details.
