---
mode: ask
description: Archive completed task work into permanent docs
---

Archive the current task session using this workflow:

1. Summarize the work completed in this session.
2. Create a permanent record in docs/internal/features/YYMMDD-topic/ or docs/internal/architecture/YYMMDD-topic/.
3. Update docs/CONTEXT.md to link findings to raw logs in docs/_AI_/YYMMDD-topic/.
4. Update CHANGELOG.md with a short description of the recent changes.

Path convention:

- Canonical workflow location is .agents/workflows/archive-task.md.
- The Copilot command entrypoint is this file: .github/prompts/archive-task.prompt.md.
