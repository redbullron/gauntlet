# Gauntlet

One skill for Codex and Claude Code: review, repair, parallel Opus work with **Spawn**, project profiles, progress, and cancellation. Spawn is a mode of Gauntlet, bundled with the original Codex/Claude review bridge.

## Modes

| Request | What it does |
| --- | --- |
| `gauntlet spawn <task>` | Parallel Claude Opus workers in isolated source copies; the coordinating Codex or Claude reviews and integrates their patches. |
| `gauntlet fix <project> <task>` | Bounded review/repair loop with Codex and Claude. |
| `gauntlet review <project> <scope>` | Read-only reviews from both models, with configured local checks. |
| `gauntlet project` | List or configure project folders, checks, and shared context. |
| `gauntlet status <id>` | Inspect the relevant Spawn batch or review job. |
| `gauntlet stop <id>` | Cancel the identified batch/job and verify it stopped. |

Spawn completion is not dual-model approval. Only the review bridge's `approved` state means both reviewers approved the recorded revision with required checks. The controllers retain separate histories and concurrency limits; selecting one mode does not automatically run another.

## Install in Codex or Claude Code

Requirements: Python 3.11+, Git, and a compatible native Claude Code CLI with an existing login and access to Opus. Review/fix also requires the Codex CLI and its login. Workers consume your CLI usage allowance; this repository contains no API keys or subscriptions.

Clone directly into the appropriate skills directory (the target must not already exist):

```sh
# Codex
 git clone https://github.com/redbullron/gauntlet.git ~/.codex/skills/gauntlet
# Claude Code
 git clone https://github.com/redbullron/gauntlet.git ~/.claude/skills/gauntlet
```

Alternatively copy the repository contents, excluding `.git`, into that directory. Keep `SKILL.md` at its root. For an existing installation, back it up and merge the skill files; retain local config and state. Reload the client if needed to discover the updated skill. Claude Code skill locations are described in its [official documentation](https://code.claude.com/docs/en/skills).

In Codex: `Use $gauntlet spawn to implement this feature, then review and integrate the results.`

In Claude Code: `/gauntlet spawn implement this feature, then review and integrate the results.`

### Spawn

From the installed Gauntlet directory:

```sh
python scripts/spawn.py doctor
python scripts/test_spawn.py
```

Read [Spawn](references/spawn.md) and its [manifest/command reference](references/controller.md). Default concurrency is three, maximum eight. Workers have explicit file ownership and fixed deadlines; the controller never automatically merges. If executable discovery fails, set `claude_executable` in the manifest. `doctor` checks required CLI flags without inference, not login or quota. Do not remove restrictions to bypass an incompatible CLI.

### Review and repair

The full bridge is included in `scripts/bridge/`. If you already have `local-gauntlet` registered, the skill uses it and preserves its profiles and history. Otherwise follow [bridge setup](references/bridge.md): create your local executable-path config, then use the CLI or register its MCP stdio server. No separate Gauntlet repository is needed.

```sh
python scripts/bridge/bridge.py --help
python scripts/bridge/test_bridge.py
```

## Boundaries and validation

Windows is locally validated. Cross-platform process handling exists but is not claimed as validated in this release. Local suites use mocks/fake workers and trusted local processes, without paid inference. Real Windows Opus coding batches have also completed with coordinator review.

Spawn artifacts default to `~/.codex/gauntlet-spawn` (override: `GAUNTLET_SPAWN_HOME`). New bridge artifacts default to `scripts/bridge/state` (override: `GAUNTLET_STATE_DIR`). Both clients can share a controller's state by using the same directory and configuration. Do not publish state, local configs, transcripts, or private project source.

Source exclusions are not a secret scanner. Sanitize files before sending them to models. File-tool restrictions and post-run scope checks are not an operating-system sandbox. Validation commands execute code and must be trusted. Cancelled/expired Spawn batches cannot resume themselves. Neither workflow automatically applies patches, deploys, or publishes.

MIT licensed. This repository was originally named `gauntlet-spawn`; Spawn now ships inside Gauntlet.
