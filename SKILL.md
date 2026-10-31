---
name: gauntlet
description: Coordinate Gauntlet review and repair, read-only Codex/Claude reviews, parallel Claude Opus workers with Spawn, project profiles, status, and cancellation. Use when the user requests Gauntlet or Gauntlet Spawn.
---

# Gauntlet

Gauntlet is one skill with several modes. The coordinating Codex or Claude session selects the requested mode and owns communication and integration. Resolve commands relative to this skill's actual installed directory.

| User request | Workflow |
| --- | --- |
| `gauntlet spawn [task]` / parallel Opus workers | Read [Spawn](references/spawn.md), then its [controller reference](references/controller.md). Use `scripts/spawn.py`. |
| `gauntlet [project] [task]` or `gauntlet fix` | Read [review and repair](references/fix.md). Use the `local-gauntlet` MCP bridge, or `scripts/bridge/bridge.py`. |
| `gauntlet review [project] [scope]` | Read [read-only review](references/review.md). Do not silently enable repairs. |
| `gauntlet project` | Read [project profiles](references/project.md). Registering a profile does not start work. |
| `gauntlet status [id]` | For a Spawn batch, use `scripts/spawn.py status --id ID`, then `result --id ID`. For a bridge job, read [bridge status](references/status.md). |
| `gauntlet stop [id]` | For a Spawn batch, use `scripts/spawn.py cancel --id ID` and verify terminal status. For a bridge job, read [bridge cancellation](references/stop.md). |

Use the ID and workflow recorded in this conversation. If the mode is unknown, inspect both controllers' status without starting anything; clarify only when multiple jobs remain plausible. Never cancel an unrelated job or treat a cancellation request as proof of termination.

An explicit request to use Gauntlet for a task authorizes the necessary model workers within that task and the user's usage limits. Installation, project configuration, and status requests do not authorize inference. Provide workers the relevant chat decisions and repository instructions; they do not inherit this conversation.

Spawn and review/repair have separate controllers and histories. Spawn permits a bounded parallel batch; the review bridge runs one job at a time. Do not automatically run both workflows or launch a review loop after Spawn. Spawn completion means results need coordinator review; only a bridge `approved` verdict means both reviewers approved the recorded revision with the required checks.

Keep work in isolated copies. Never automatically merge, publish, deploy, or restart terminated work. Honor explicit user authorization for integration or publishing. Preserve reports, patches, and failed history. Do not launch Gauntlet recursively from a worker.

For a new machine, read [bridge setup](references/bridge.md) for review/fix and [Spawn controller](references/controller.md) for parallel workers. Existing bridge installations can keep their registered MCP server and state.
