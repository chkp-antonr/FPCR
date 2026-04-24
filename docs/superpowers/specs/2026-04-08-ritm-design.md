# RITM (Requested Item) Module Design

**Date:** 2026-04-08
**Status:** Approved
**Author:** AI Assistant + User Collaboration

---

## Overview

Add an approval workflow layer to the FPCR WebUI for managing firewall policy change requests through RITMs (Requested Items). The module provides separation of duties between requesters and approvers, with full audit trail and state management.

---

## Architecture

### Frontend Components

| Component | Description | Based On |
|-----------|-------------|----------|
| `Dashboard.tsx` (modified) | Main entry point with RITM action cards | Existing |
| `RitmEdit.tsx` (new) | Rule editor for RITM with auto-save | `Domains.tsx` |
| `RitmApprove.tsx` (new) | Approval interface with feedback | New |

### Backend Components

| Component | Description |
|-----------|-------------|
| `src/fa/routes/ritm.py` (new) | RITM CRUD and status management endpoints |
| `src/fa/models.py` (extended) | `RITM` and `Policy` SQLModel tables |

### Database

| Table | Purpose |
|-------|---------|
| `ritm` | RITM metadata, status tracking, approval locking |
| `policy` | Full rule data linked to RITM |

---

## Status Flow

```
work_in_progress (0)
      ↓
ready_for_approval (1)
      ↓                    ↗
approved (2)            returned (feedback provided)
      ↓
completed (3)
```

**Status Values:**

- `0` - Work in progress (creator editing)
- `1` - Ready for approval (awaiting reviewer)
- `2` - Approved (awaiting publish)
- `3` - Completed (published, archived)

---

## Dashboard Layout

The modified Dashboard displays five sections:

| Section | Shows | Action |
|---------|-------|--------|
| **New RITM** | Button | Opens modal for RITM number |
| **My RITMs** | Current user's `work_in_progress` or `returned` | "Continue" → edit |
| **Ready for Approval** | `ready_for_approval`, `approver_locked_by IS NULL` | "Review" → approve |
| **Under Review (by me)** | `approver_locked_by = current_user` | "Continue" → approve |
| **Under Review (by others)** | `approver_locked_by != current_user` | Read-only, shows reviewer |
| **Approved RITMs** | `approved` status | "Publish" |

Each section collapses if empty.

---

## /ritm/edit Page

Based on `Domains.tsx` with modifications:

### New Columns

- **Comments** - Prepopulated `RITM{number} #{YYYY-MM-DD}#`, editable
- **Rule Name** - Prepopulated `RITM{number}`, editable

### Actions

- **Save Draft** - Saves policy to database (no status change)
- **Submit for Approval** - Saves policy, sets status to `ready_for_approval`, sets `date_updated`

### Auto-save Behavior

- Current rule saved to `policy` table when switching between rules
- On page load, all existing rules loaded from database

### Navigation

- Breadcrumb: `Dashboard > RITM {number} > Edit`
- Cancel returns to Dashboard

---

## /ritm/approve Page

Read-only view for reviewing RITM policy:

### Display

- RITM metadata header (number, creator, dates)
- RulesTable in read-only mode (expandable for details)
- Comments and Rule Name columns visible

### Actions

- **Approve** - Sets status to `approved`, records `username_approved`, `date_approved`
- **Return for Changes** - Requires feedback text, sets status to `work_in_progress`, saves `feedback`
- **Cancel** - Releases approval lock, returns to Dashboard

### Creator Override

- Creator opening `ready_for_approval` RITM redirected to edit page with warning

---

## Database Schema

### ritm Table

| Column | Type | Description |
|--------|------|-------------|
| `ritm_number` | TEXT PRIMARY KEY | RITM identifier (e.g., "RITM2452257") |
| `username_created` | TEXT NOT NULL | Creator username |
| `date_created` | TEXT NOT NULL | Naive UTC-0, when work started |
| `date_updated` | TEXT | Set on submit for approval |
| `date_approved` | TEXT | Set when approved |
| `username_approved` | TEXT | Approver username |
| `feedback` | TEXT | Feedback when returned |
| `status` | INTEGER NOT NULL DEFAULT 0 | 0-3 status code |
| `approver_locked_by` | TEXT | User currently reviewing |
| `approver_locked_at` | TEXT | Lock acquisition time (for timeout) |

### policy Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `ritm_number` | TEXT NOT NULL | Foreign key to ritm.ritm_number |
| `comments` | TEXT | `RITM{number} #{YYYY-MM-DD}#` |
| `rule_name` | TEXT | `RITM{number}` |
| `domain_uid` | TEXT NOT NULL | Check Point domain UID |
| `domain_name` | TEXT NOT NULL | Domain name |
| `package_uid` | TEXT NOT NULL | Package UID |
| `package_name` | TEXT NOT NULL | Package name |
| `section_uid` | TEXT | Section UID (nullable) |
| `section_name` | TEXT | Section name |
| `position_type` | TEXT NOT NULL | 'top', 'bottom', 'custom' |
| `position_number` | INTEGER | For custom position |
| `action` | TEXT NOT NULL | 'accept' or 'drop' |
| `track` | TEXT NOT NULL | 'log' or 'none' |
| `source_ips` | TEXT NOT NULL | JSON array |
| `dest_ips` | TEXT NOT NULL | JSON array |
| `services` | TEXT NOT NULL | JSON array |

---

## API Endpoints

### POST /api/v1/ritm

Create new RITM.

**Request:**

```json
{
  "ritm_number": "RITM2452257"
}
```

**Response:** RITM object

**Side effects:** Sets `date_created`, `username_created`, status=0

### GET /api/v1/ritm

List RITMs with optional filtering.

**Query params:**

- `status` (optional) - Filter by status
- `username` (optional) - Filter by creator

**Response:** Array of RITM objects

### GET /api/v1/ritm/{ritm_number}

Get single RITM with associated policies.

**Response:** RITM object + policies array

### PUT /api/v1/ritm/{ritm_number}

Update RITM status and/or feedback.

**Request:**

```json
{
  "status": 1,
  "feedback": "Please fix the source IPs"
}
```

**Side effects:** Sets `date_updated`, `date_approved`, `username_approved`, `feedback` as appropriate

### POST /api/v1/ritm/{ritm_number}/policy

Save policy draft.

**Request:** Array of policy objects (full rule data)

**Side effects:** Creates/updates policy records for the RITM

### POST /api/v1/ritm/{ritm_number}/publish

Publish approved RITM to Check Point.

**Process:**

1. Reads all policies from database
2. Calls `rules2Api.createBatch()` endpoint
3. On success: sets status to `completed`
4. On failure: keeps status as `approved`, returns error

---

## Routing

| Route | Purpose | Access Control |
|-------|---------|----------------|
| `/` | Dashboard | Authenticated users |
| `/ritm/new` | Create new RITM modal | Authenticated users |
| `/ritm/edit/{ritm_number}` | Edit page | Creator only, or returned status |
| `/ritm/approve/{ritm_number}` | Approve page | Non-creators with ready status |
| `/domains` | Legacy demo page | Unchanged |
| `/domains-2` | Legacy demo page | Unchanged |

---

## Approval Locking

### Lock Acquisition

- When user clicks "Review" on ready RITM, set `approver_locked_by` and `approver_locked_at`
- RITM moves from "Ready" to "Under Review (by me)"

### Lock Expiration

- Lock expires after 30 minutes of inactivity (configurable via `APPROVAL_LOCK_MINUTES` env var)
- Background task checks `approver_locked_at` and releases expired locks
- Expired RITMs return to "Ready for Approval"

### Lock Release

- "Cancel" in approve page releases lock immediately
- Successful approve/publish releases lock

---

## Error Handling

### RITM Number Validation

- Must be unique - reject duplicates on creation
- Must match pattern `RITM\d+` (e.g., "RITM2452257")

### State Transitions

- Prevent invalid transitions (e.g., publish if not approved)
- Creator redirected to edit if trying to approve own RITM

### Publish Failures

- Keep RITM as "approved" (not "completed") on Check Point API failure
- Show error with retry option

### Session Expiry

- Preserve unsaved work in localStorage
- Warn user on next page load

---

## Testing Strategy

### Unit Tests

- RITM CRUD operations
- Approval locking (acquire, timeout, release)
- Policy save/retrieve functionality

### Integration Tests (API)

- Full workflow: create → edit → submit → approve → publish
- Concurrent access scenarios
- Error cases (duplicate numbers, invalid transitions)

### Frontend Tests

- Dashboard rendering based on RITM state
- Edit page auto-save behavior
- Approve page actions

### Manual Testing Scenarios

1. Create RITM, add rules, save draft, close browser, reopen - data persists
2. Submit for approval, verify appears in another user's "Ready" list
3. Approval timeout after X minutes inactivity
4. Creator opens own "ready" RITM - redirected to edit with warning
5. Publish failure - RITM stays "approved" for retry

### Test Database

- Use `.env.test` for test database configuration
- Records can be created/deleted safely during tests

### Configuration

- Use Pydantic v2 `BaseSettings` for configuration management
- Load from `.env`, `.env.secrets`, or `.env.test` (for testing)
- New settings:
  - `APPROVAL_LOCK_MINUTES` - Lock timeout duration (default: 30)

---

## Notes

- Existing `/domains` and `/domains-2` pages remain unchanged for demo purposes
- Actual firewall rule work flows through `/ritm/edit` and `/ritm/approve`
- All dates are naive UTC-0 (no timezone handling)
- Comments format: `RITM{number} #{YYYY-MM-DD}#` uses RITM's `date_created`
