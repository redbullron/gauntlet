# Gauntlet Spawn

Let Codex or Claude Code coordinate parallel Claude Opus workers, review their patches, and integrate the results. Each worker gets an isolated source copy, a bounded task, allowed file paths, and a deadline. The controller never merges results automatically.

This is a standalone skill and Python controller. It does not require the separate Gauntlet review bridge. It requires Python 3.11+, Git, and a native Claude Code executable with an existing login and access to Opus. Workers consume your Claude usage allowance. No API key is bundled or required by this controller.

## Install

Download or clone this repository. Copy the whole repository folder (excluding `.git`) to one of these locations, keeping `SKILL.md` at the top:

- Codex: `~/.codex/skills/gauntlet-spawn/`
- Claude Code: `~/.claude/skills/gauntlet-spawn/`

You can install a copy in both. Both use the same default local state directory, so only one batch runs at a time across the two coordinators.

In Codex, ask: `Use $gauntlet-spawn to implement this feature, then review and integrate the results.`

In Claude Code, ask: `/gauntlet-spawn implement this feature, then review and integrate the results.` See the [official Claude Code skills documentation](https://code.claude.com/docs/en/skills).

From the installed skill directory, check prerequisites without paid inference:

```sh
python scripts/spawn.py doctor
python scripts/test_spawn.py
```

Use your Python 3.11+ executable if it is named differently. `doctor` checks CLI capabilities, not authentication or quota. If it reports missing flags, use a compatible native Claude CLI; do not remove the controller's restrictions to bypass that failure. If discovery fails, supply `claude_executable` in your batch manifest.

## How it works

1. The coordinator divides authorized work into independent tasks with nonoverlapping edit paths.
2. It prepares a manifest and checks the source inventory with `preflight`.
3. `start` snapshots the source and launches up to three workers by default (maximum eight).
4. Workers produce reports, patches, scope verdicts, and optional validation outputs.
5. The coordinator reviews and integrates selected changes, then validates the combined result.

Read [the skill](SKILL.md) and [the manifest and command reference](references/controller.md) for details. Read-only workers can investigate the same source; dependent coding tasks require separate, reviewed waves. Requested model is the `opus` alias; actual returned model IDs are recorded when available.

## Boundaries and support

Windows is locally validated, including native kill-on-close Job Objects. macOS/Linux process-group handling is implemented but not validated in this release. The local suite uses fake workers and makes no model inference calls. Real Windows Opus coding batches have also completed, with human-facing coordinator review.

Source copies, worker transcripts, and patches remain locally under `~/.codex/gauntlet-spawn`; set `GAUNTLET_SPAWN_HOME` to choose another state directory. Do not publish that directory. Snapshot exclusions are not a secret scanner: sanitize source files before sending them to a model. File-tool restrictions and post-run scope checks are not an operating-system security sandbox. Trusted validation commands can execute code.

Cancelled, expired, or interrupted batches cannot resume themselves. There are no automatic retries, model fallbacks, merges, deployments, or deadline extensions. A completed batch can still contain failed workers; inspect each result. Claude-only orchestration is not an independent Codex review or a dual-model approval.
