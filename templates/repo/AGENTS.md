<!-- OPENSPEC-AUTO:START -->
# OpenSpec First Workflow

This repository uses OpenSpec as the default workflow for any request that changes code or runtime behavior.

Use OpenSpec automatically for:
- New features
- Bug fixes
- Refactors that change behavior or interfaces
- API, DTO, database, migration, or frontend behavior changes
- Config changes that alter runtime behavior

Do not require the user to manually type OpenSpec commands or slash commands.

Default flow:
1. Check active changes first with `openspec list --json`.
2. If the user names a change, use it.
3. If exactly one active change clearly matches, continue it.
4. If multiple active changes could match, ask the user which one to use.
5. If no active change exists, create and prepare one before writing application code.
6. Before editing application code, make sure the change is apply-ready from `openspec status --change "<name>" --json`.
7. Use `openspec instructions <artifact> --change "<name>" --json` to create missing artifacts in dependency order.
8. Implement against the change tasks and keep the task checklist current.
9. Before claiming completion, run `openspec validate <change-name> --type change --strict --json --no-interactive` and the repository's normal tests.
10. Once every task is checked off and validation passes, finish the change by running `openspec archive "<change-name>" -y` so the spec delta merges into `openspec/specs/`. Use `--skip-specs` for tooling, infrastructure, or docs-only changes. Archiving is part of completing the work, not a separate chore. Do not trust the exit code alone: when a spec delta does not match the current baseline, `openspec archive` prints `Aborted. No files were changed.` and still exits 0 — read the output and confirm the change actually moved into `openspec/changes/archive/`.

Bypass rules:
- Read-only explanation, analysis, and review tasks do not need OpenSpec.
- Docs-only edits do not need OpenSpec unless the docs are OpenSpec artifacts.
- The user may explicitly ask to skip OpenSpec. If they do, honor that request and state that the workflow is being bypassed.

Guardrails:
- Do not silently choose among multiple plausible active changes.
- Do not start application edits before the change is apply-ready unless the user explicitly skips OpenSpec.
- Treat OpenSpec CLI output as the source of truth for change state.
- Do not leave a change with all tasks complete sitting in `openspec/changes/`. Unarchived completed changes make `openspec/specs/` stale and pollute the active-change list that step 1 reads.

## Project Layout Defaults

These defaults apply only when bootstrapping a brand-new fullstack application. If the repository
already has an established layout, follow that existing layout instead — do not restructure it to
match these defaults.

When bootstrapping a new fullstack application, prefer:

- backend application code under `backend/`
- frontend application code under `frontend/`

In that case, avoid introducing new conventions such as `api/` or `web/` unless the user explicitly requests them.
<!-- OPENSPEC-AUTO:END -->
