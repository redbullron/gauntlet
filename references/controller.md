# Controller

Requires Python 3.11+, Git, and the installed native Claude CLI with an existing login. Use absolute paths. Use your installed Python executable. Windows is locally validated; macOS/Linux process-group support is implemented but has not been validated in this release.

```text
python scripts/spawn.py doctor
python scripts/spawn.py preflight --manifest C:/work/batch.json
python scripts/spawn.py start --manifest C:/work/batch.json
python scripts/spawn.py status --id BATCH_ID
python scripts/spawn.py result --id BATCH_ID
python scripts/spawn.py cancel --id BATCH_ID
python scripts/test_spawn.py
```

Commands are relative to this skill's directory. `start` returns immediately with the ID and artifact directory. Omitting `--id` uses the most recent batch. A controller lock allows one active batch; workers within it run concurrently. An interrupted coordinator is reported as interrupted, not adopted or restarted.

## Manifest

```json
{
  "name": "Implement requested feature",
  "context": "Relevant decisions, repository instructions, interfaces and restrictions.",
  "concurrency": 3,
  "max_minutes": 60,
  "worker_minutes": 15,
  "tasks": [
    {
      "id": "policy",
      "source": "C:/work/sanitized-candidate",
      "mode": "edit",
      "task": "Implement the policy in src/policy.py and its focused tests. Explain the change and remaining uncertainty.",
      "write_paths": ["src/policy.py", "tests/test_policy.py"],
      "exclude": [],
      "checks": [
        {
          "name": "policy tests",
          "command": ["python", "-m", "unittest", "tests.test_policy"],
          "cwd": ".",
          "timeout_seconds": 120
        }
      ]
    }
  ]
}
```

`mode` is `edit` or `read`. Read tasks must have empty write_paths and checks. Write paths are exact relative files or directory prefixes ending in `/`; no globs, traversal, absolute paths, `.git`, or skill/settings locations. Concurrent edit tasks from the same source must not overlap. Review tasks may read the same source. Checks use command arrays, never `shell=True`; choose trusted executables and arguments. Checks run in the isolated copy. Supply dependencies in a sanitized source or use existing runtimes; the controller does not install dependencies. Checks can execute arbitrary code, so do not run untrusted commands or tests with secrets available. Changes to deliverable files during checks fail validation.

Limits: 1–8 concurrent workers, 1–32 tasks, batch 1–240 minutes, worker 1–120 minutes, each check 1–3600 seconds. Worker and checks share the worker deadline; all work also shares the batch deadline. No retries, deadline extensions, continuation sessions, or automatic merging.

By default snapshots exclude `.git`, common dependency/build/cache directories, environment/credential/private-key filenames, and Git-ignored files. Additional `exclude` entries use relative glob matching. Source reparse points and symlinks are excluded; file links are never followed. Large snapshots fail preflight (20,000 files / 512 MiB / 32 MiB per file). Excluded files are recorded by path. Sanitize ordinary source files yourself if they contain credentials. Do not use the user's home/profile directory as a source. Input is snapshotted at launch; later source drift is detected in results.

Claude runs with safe/restricted mode, an empty MCP config, no session persistence, no browser, no plugins/skills/hooks, and only file tools. The controller supplies the prompt on stdin and restricts allowed edits after execution through a Git diff. Tool confinement and file-scope checks are not an OS security sandbox; use trusted projects. Model prompts cannot start shell commands or nested agents through the enabled tools.

Native executable discovery: explicit `claude_executable` in the manifest, `~/.local/bin/claude` (`claude.exe` on Windows), native npm installation path, then PATH. PowerShell/CMD wrappers are rejected. `doctor` checks required CLI options without inference. Authentication failures stop the worker; provider API key environment variables are not forwarded. The existing Claude login is used. No model fallback or API key setup is performed.

## Artifacts and states

State is under `~/.codex/gauntlet-spawn` (override with `GAUNTLET_SPAWN_HOME` for tests). Each batch has a manifest, status, coordinator log, and per-worker source copy, original fingerprint, report/CLI output, patch, scope verdict, and check outputs. Local copies have a separate Git baseline; the original source is never edited by the controller. Artifacts are retained; there is no automatic cleanup.

Worker states: queued, preparing, running, checking, needs_review, needs_validation, failed, cancelled, limit_reached. Batch states add completed and interrupted. `completed` means the coordinator finished; inspect worker results for failure. Requested model is `opus`; returned model identifiers, when available, are recorded separately. Costs are recorded only if returned by Claude, not estimated as billing guarantees.

Windows workers launch suspended into kill-on-close Job Objects before execution. The coordinator retains native process/job handles; cancellation and time limits close only those owned jobs. On other platforms owned process groups are terminated. No stale PID adoption or global process-name kills. Cancel requests are marker files; if the controller is already gone, status becomes interrupted and cannot be resumed.

Local tests exercise fake workers and trusted commands only. They do not call Claude inference. A successful `doctor` is CLI capability detection, not proof of login, quota, or end-to-end model execution.
