# RITM Workflow V2 – Design Spec

**Date:** 2026-05-05

**Feature branch:** `worktree-feat+ritm-workflow-v2`

**Status:** Approved, ready for implementation

---

## Overview

Four improvements to the RITM approval workflow:

1. **Multi-editor tracking** – any engineer who edits a RITM is permanently blocked from approving it; anyone who approves or rejects is permanently blocked from editing it.
2. **Approval publish completion** – the `POST /publish` endpoint currently mocks the Check Point API call; v2 implements enable-rules → verify → publish → evidence.
3. **Cumulative evidence history** – evidence is never overwritten; each Try & Verify and approval run appends to a history table, displayed as Domain → Package → Session.
4. **Domain-change transparency** – no special annotation needed; domain changes naturally appear as "rule created then deleted" in Domain A and "rule created" in Domain B across sessions.

---

## 1. Database Schema

**Clean break – `cache.db` will be deleted and recreated. No migration or backward compatibility required.**

### 1.1 Remove

- Columns from `ritm` table: `session_changes_evidence1`, `session_changes_evidence2`, `try_verify_session_uid`
- Table: `ritm_sessions` (replaced by `ritm_evidence_sessions`)

### 1.2 Add Columns to `ritm` Table

| Column | Type | Notes |
|--------|------|-------|
| `editor_locked_by` | TEXT nullable | Username holding the editor lock |
| `editor_locked_at` | DATETIME nullable | When the editor lock was acquired |

### 1.3 New Table: `ritm_editors`

```sql
CREATE TABLE ritm_editors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ritm_number TEXT NOT NULL REFERENCES ritm(ritm_number),
    username    TEXT NOT NULL,
    added_at    DATETIME NOT NULL,
    UNIQUE(ritm_number, username)
);
```

`username_created` is inserted here when the RITM is first created. Any subsequent engineer who saves a policy while holding the editor lock is also inserted (on conflict ignore).

### 1.4 New Table: `ritm_reviewers`

```sql
CREATE TABLE ritm_reviewers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ritm_number TEXT NOT NULL REFERENCES ritm(ritm_number),
    username    TEXT NOT NULL,
    action      TEXT NOT NULL,  -- "approved" | "rejected"
    acted_at    DATETIME NOT NULL
);
```

Not unique – the same person can review across multiple correction cycles. A reviewer who rejected in cycle 1 is still blocked from editing, but can reject again in cycle 2 (they never became an editor).

### 1.5 New Table: `ritm_evidence_sessions`

```sql
CREATE TABLE ritm_evidence_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ritm_number     TEXT NOT NULL REFERENCES ritm(ritm_number),
    attempt         INTEGER NOT NULL,   -- increments per Try & Verify run; shared across packages in same run
    domain_name     TEXT NOT NULL,
    domain_uid      TEXT NOT NULL,
    package_name    TEXT NOT NULL,
    package_uid     TEXT NOT NULL,
    session_uid     TEXT,
    sid             TEXT,
    session_type    TEXT NOT NULL,      -- "initial" | "correction" | "approval"
    session_changes TEXT,               -- JSON blob: raw show-changes API response for this session
    created_at      DATETIME NOT NULL
);
```

`attempt` is derived at runtime as `MAX(attempt) + 1` across all existing rows for the RITM (or 1 if none). All packages processed in a single Try & Verify run share the same `attempt` value. `session_type` is `"initial"` when `attempt == 1`, `"correction"` when `attempt > 1`, `"approval"` when written by the publish endpoint.

---

## 2. Business Rules

### 2.1 Editor Lock

Mirrors the existing approval lock pattern.

- `POST /ritm/{ritm_number}/editor-lock`
  - Fails with `400` if the user is in `ritm_reviewers` for this RITM (reviewers cannot become editors).
  - Fails with `400` if lock is held by another user and has not expired.
  - Expiry duration: `settings.approval_lock_minutes` (reuse existing setting).
  - On success: sets `editor_locked_by` and `editor_locked_at`.

- `POST /ritm/{ritm_number}/editor-unlock`
  - Only the lock holder can release.
  - Clears `editor_locked_by` and `editor_locked_at`.

### 2.2 Policy save (`POST /ritm/{ritm_number}/policy`)

After saving policies: if the requesting user currently holds the editor lock → insert into `ritm_editors` (ON CONFLICT IGNORE).

### 2.3 Submit for Approval (`PUT /ritm/{ritm_number}` → Status 1)

Old rule (creator only) is replaced: user must be in `ritm_editors` AND currently hold the editor lock.

Rationale: any co-editor who owns the lock is the current responsible party and can submit.

### 2.4 Approve (`PUT /ritm/{ritm_number}` → Status 2)

Additional check: user must **not** be in `ritm_editors` for this RITM.

On success:

- Set `date_approved`, `username_approved`, clear approval lock.
- Insert into `ritm_reviewers` with `action="approved"`.

### 2.5 Reject (`PUT /ritm/{ritm_number}` → Status 0 with feedback)

On success:

- Insert into `ritm_reviewers` with `action="rejected"`.
- Feedback remains mandatory.
- RITM returns to `WORK_IN_PROGRESS`; editor lock is cleared so a new editor can claim it.

### 2.6 Status Transition Table (updated)

| Transition | Who | Constraints |
|------------|-----|-------------|
| → `WORK_IN_PROGRESS` (create) | Any | – |
| → `READY_FOR_APPROVAL` | Any editor who holds editor lock | Must be in `ritm_editors` + hold editor lock |
| → `APPROVED` | Any non-editor | Must not be in `ritm_editors`; RITM must be `READY_FOR_APPROVAL` |
| → `WORK_IN_PROGRESS` (rejection) | Any non-editor | Feedback required; inserts into `ritm_reviewers` |
| → `COMPLETED` | Server | On successful publish |

---

## 3. Try & Verify Changes

`POST /ritm/{ritm_number}/try-verify` – `RITMWorkflowService.try_verify()`

**Attempt number:** computed once at the start of the run as `MAX(attempt) + 1` from `ritm_evidence_sessions` where `ritm_number = ?`, defaulting to 1.

**Session type:** `"initial"` if attempt == 1, `"correction"` otherwise.

**On each successful package** (after disable-rules step, evidence captured):

- Insert one row into `ritm_evidence_sessions` with the package's `domain_name`, `domain_uid`, `package_name`, `package_uid`, `session_uid`, `sid`, `session_changes` JSON, and `created_at = now()`.

**After all packages:**

- No longer stores evidence in `ritm.session_changes_evidence1`.
- No longer writes to `ritm_sessions`.
- Combined evidence for the response (`TryVerifyResponse`) is built by merging all rows inserted in this run – same logic as before, just sourced from the newly inserted rows rather than the in-memory list.

**Object creation on domain change** is already correct: `PackageWorkflowService` creates objects in the domain specified by each policy's `domain_uid`. No code change required. When an engineer moves a rule from Domain A to Domain B, the next Try & Verify creates objects in Domain B automatically. Evidence will show Domain A with "rule deleted" and Domain B with "rule created + objects created" – no special handling needed.

---

## 4. Approval Publish – Completing the TODO

`POST /ritm/{ritm_number}/publish` – currently mocked; v2 implements the full flow.

For each unique `(domain_uid, package_uid)` in saved policies:

1. **Enable disabled rules** – for each rule UID in `ritm_created_rules` where `ritm_number = ?` and `domain_uid = ?` and `package_uid = ?`: call `set-access-rule` with `{"enabled": true}`.
2. **Verify policy** – same as Try & Verify pre-check. On failure: re-disable all rules just enabled; return error; RITM stays `APPROVED`.
3. **Capture evidence** – call `show-changes` for this domain; store as `ritm_evidence_sessions` row with `session_type="approval"`. The `attempt` value for the entire publish run is computed once as `MAX(attempt) + 1` from `ritm_evidence_sessions` where `ritm_number = ?`, same as Try & Verify.
4. **Publish** – `publish` API call with session name `{RITM} {username} Published`.

On all packages succeeding: status → `COMPLETED`.

---

## 5. Evidence History API

### 5.1 New Endpoint: `GET /ritm/{ritm_number}/evidence-history`

Returns the full accumulated evidence grouped hierarchically:

```json
{
  "domains": [
    {
      "domain_name": "Domain_A",
      "domain_uid": "...",
      "packages": [
        {
          "package_name": "Package_X",
          "package_uid": "...",
          "sessions": [
            {
              "attempt": 1,
              "session_type": "initial",
              "session_uid": "...",
              "created_at": "2026-05-05T10:30:00Z",
              "session_changes": { }
            },
            {
              "attempt": 2,
              "session_type": "correction",
              "session_uid": "...",
              "created_at": "2026-05-06T14:15:00Z",
              "session_changes": { }
            }
          ]
        }
      ]
    }
  ]
}
```

Query: `SELECT * FROM ritm_evidence_sessions WHERE ritm_number = ? ORDER BY attempt ASC, domain_name ASC, package_name ASC`.

### 5.2 Updated: `GET /ritm/{ritm_number}/session-html` and `session-pdf`

- Add optional `attempt` query param (integer).
- Without `attempt`: renders all sessions in Domain → Package → Session hierarchy, ordered by attempt then created_at.
- With `attempt`: renders only sessions from that attempt number.

### 5.3 Updated: `POST /ritm/{ritm_number}/recreate-evidence`

Re-fetches `show-changes` for every row in `ritm_evidence_sessions` using the stored `session_uid`, and overwrites the `session_changes` column in place. Skips rows where `session_uid` is null or where `show-changes` returns empty (already published – keeps existing `session_changes`). Returns an `EvidenceResponse` with the combined HTML rendered from all rows (same grouping as `/evidence-history`: Domain → Package → Session ordered by attempt).

### 5.4 `GET /ritm/{ritm_number}` Response

Gains two new fields:

```json
{
  "editors": ["eng1", "eng3"],
  "reviewers": [
    {"username": "eng2", "action": "rejected", "acted_at": "2026-05-05T12:00:00Z"}
  ]
}
```

---

## 6. Unchanged

- `GET /ritm` list endpoint – no changes.
- `POST /ritm/{ritm_number}/plan-yaml` – no changes.
- `POST /ritm/{ritm_number}/match-objects` – no changes.
- `POST /ritm/{ritm_number}/verify-policy` – no changes.
- `GET /ritm/{ritm_number}/export-errors` – no changes.
- Object naming conventions (`Host_`, `Net_`, `IPR_`) – no changes.
- Approval lock endpoints – no changes (remain separate from editor lock).

---

## 7. Domain-Change Scenario

When an engineer changes a rule's domain from A to B between two Try & Verify runs:

- **Attempt 1** (initial): Domain A, Package X – rule created, objects created, rule disabled, session published.
- **Engineer edits**: removes the policy for Domain A, adds new policy for Domain B.
- **Attempt 2** (correction):
  - Domain A – old rule is deleted (part of rollback from removing it from policies; or it remains disabled until cleanup).
  - Domain B – new objects created, new rule created, disabled, published.
- **Evidence history shows:**
  - Domain A → Package X → Attempt 1 (rule created), Attempt 2 (rule deleted if explicitly removed)
  - Domain B → Package Y → Attempt 2 (objects + rule created)

> **Note:** Explicitly deleting the old disabled rule from Domain A when an engineer removes it from policies is a separate concern. The current Try & Verify does not clean up rules from previous attempts that are no longer in the policy list. This is out of scope for v2 and should be tracked separately.

---

## 8. Out of Scope (Future)

- Automatic cleanup of orphaned disabled rules when policies are modified between attempts.
- Expiration datetime on rules.
- Install policy after publish.
- CMDB state updates.
- Admin-level RITM reassignment.
