# Gauntlet project

Commands use paths relative to the installed Gauntlet skill directory. Prefer an already registered `local-gauntlet` MCP server to preserve its existing project profiles and history. For a new CLI installation, read [bridge setup](bridge.md).

Use `gauntlet_projects` first. Without arguments, list registered project names, folders, and validation coverage. To add/update a project, resolve the supplied name and folder or the current project folder. Preserve existing checks, context, and kind unless the user asks to change them.

Call `gauntlet_register_project` with a meaningful name, absolute folder path, shared context, and suitable check definitions. Each check has `name`, a `command` argument array, optional relative `cwd`, and a 1-1800 second `timeout`. Check commands run in an isolated source copy; dependencies and ignored build directories are not copied. Use explicit executable/script arguments on Windows, such as `node.exe` plus npm's `npm-cli.js`, instead of shell interpolation. Never configure a deployment or live operational command as a test.

Use kind `code` for software: both reviewer approval and passing configured checks are required. With no checks, code runs return `needs_validation` rather than pass. Kind `document` is for prose/design handoff review where code execution is not an acceptance requirement; do not relabel code to bypass checks.

Shared context should capture relevant project decisions, constraints, and validation limits. Read handoff material the user identifies and save a concise factual summary, excluding credentials. Both reviewers receive this context on later runs. Registering a profile does not start a job.

CLI fallback: Python with `scripts/bridge/bridge.py projects`, or `register name path --profile profile.json` where profile.json contains checks, context, and kind.
