# Cache Refresh Stability and Single-DB Consolidation

**Date:** 2026-04-01

**Status:** In progress (major fixes implemented, runtime retest pending)

## Goal

Stabilize Domains cache refresh behavior after introducing:

1. `last_published_session`-based skip logic.
2. Single SQLite database mode (`DATABASE_URL` only).
3. Better progress visibility for long-running cache refreshes.

## What Was Implemented

### 1. Single Database Consolidation

- Session storage was switched to use the same SQLite file resolved from `DATABASE_URL`.
- Separate `SESSIONS_DB_PATH` usage was removed from runtime flow.
- Startup and runtime now align with `.env` as source of truth for DB path.

**Key files:**

- `src/fa/config.py`
- `src/fa/session.py`
- `.env`

### 2. Schema Compatibility and Safety

- Added startup schema check and auto-recreate path for legacy cache layout.
- Added explicit CRITICAL logging when schema mismatch is detected (`no such column`), with recommendation to delete `_tmp/cache.db` and restart.

**Key files:**

- `src/fa/app.py`
- `src/fa/cache_service.py`

### 3. Domain Refresh Change Detection

- Added `last_published_session` to cached domain model.
- Domain refresh now compares publish-session values to avoid unnecessary recaching.
- Logging now distinguishes:
  - `Caching domain: ...`
  - `Skipping domain: ... (no changes)`

**Key files:**

- `src/fa/models.py`
- `src/fa/cache_service.py`

### 4. Core Refresh Read Consistency

- Added wait-on-core-refresh behavior before reading domains/packages endpoints.
- Prevents partial read states while core refresh is in progress.

**Key files:**

- `src/fa/cache_service.py`
- `src/fa/routes/domains.py`
- `src/fa/routes/packages.py`

### 5. Frontend Progress UX

- Added explicit progress UI for initial load and manual refresh.
- Added domain name in progress label (example: `Domain 1/3: CPCodeOps`).
- Added local refresh state and faster polling while refresh is active.

**Key files:**

- `webui/src/pages/Domains.tsx`
- `webui/src/types/index.ts`

### 6. Async/Locking Stabilization

- Fixed `MissingGreenlet` by avoiding ORM entity reuse after commit in async flow.
- Added one-time repair mode when inconsistent cache is detected (domains present, packages missing).
- Moved API `show-packages` call before domain write operations to reduce write lock hold time.
- Added callback logging for login-triggered background refresh task failures.

**Key files:**

- `src/fa/cache_service.py`
- `src/fa/routes/auth.py`

## Validation Executed

Required validation command was run repeatedly after each logical change:

- `uv run ruff check --fix src/; uv run mypy src/`

Result at latest pass:

- Ruff: all checks passed.
- Mypy: success, no issues in 22 source files.

Frontend build also passed during this session:

- `npm run build` in `webui`.

## Observed Regressions and Fixes

1. **Regression:** Packages disappeared after introducing skip logic.
   - Cause: package cache was globally cleared before unchanged domains were skipped.
   - Fix: clear/replace only for changed domains; keep unchanged domain packages.

2. **Regression:** `MissingGreenlet` on relogin background refresh.
   - Cause: async ORM attribute access after commit.
   - Fix: switched to scalar snapshots + explicit SQL updates/deletes.

3. **Runtime issue under test:** UI appeared stuck at `Domain 1/3` with `Packages: 0/0`.
   - Mitigations implemented: full repair mode + shorter DB write sections + improved task error logging.
   - Final runtime confirmation still required after last patch set.

## Recommended Next Verification

Run this exact flow in one process without restart between relogin steps:

1. Start app.
2. Login.
3. Wait for domains/packages to appear.
4. Logout.
5. Login again.
6. Confirm logs progress through all domains and `Domains and packages cache refresh completed`.
7. Confirm package dropdowns load without repeated recache loops.

If lock errors still appear, inspect remaining contention around `distributed_locks` writes during core refresh.
