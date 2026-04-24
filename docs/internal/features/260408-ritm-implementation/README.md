# RITM Module Implementation

**Date:** 2026-04-08

**Status:** Completed

## Overview

Implemented a complete RITM (Requested Item) approval workflow module for the FPCR (Firewall Policy Change Request) tool. This adds formal approval/audit trail before firewall changes are published, with separation of duties between requesters and approvers.

## Key Features

- **RITM Creation**: Users create RITMs with unique numbers (format: RITM + digits)
- **Draft Storage**: Policies saved locally, pushed to Check Point only when approved
- **Approval Workflow**: work_in_progress → ready_for_approval → approved → completed
- **Approval Locking**: 30-minute timeout prevents concurrent approvals
- **Input Pool Persistence**: Source IPs, Dest IPs, Services saved with RITM
- **Separation of Duties**: Creator cannot approve own RITM
- **Feedback Loop**: Approvers can return RITMs with feedback for revisions

## Database Schema

### RITM Table

```sql
CREATE TABLE ritm (
    ritm_number VARCHAR PRIMARY KEY,
    username_created VARCHAR NOT NULL,
    date_created DATETIME NOT NULL,
    date_updated DATETIME,
    date_approved DATETIME,
    username_approved VARCHAR,
    feedback TEXT,
    status INTEGER DEFAULT 0,
    approver_locked_by VARCHAR,
    approver_locked_at DATETIME,
    source_ips TEXT,  -- JSON array
    dest_ips TEXT,    -- JSON array
    services TEXT     -- JSON array
);
```

### Policy Table

```sql
CREATE TABLE ritm_policy (
    id INTEGER PRIMARY KEY,
    ritm_number VARCHAR REFERENCES ritm(ritm_number),
    comments TEXT,
    rule_name TEXT,
    domain_uid VARCHAR,
    domain_name VARCHAR,
    package_uid VARCHAR,
    package_name VARCHAR,
    section_uid VARCHAR,
    section_name VARCHAR,
    position_type VARCHAR,
    position_number INTEGER,
    action VARCHAR,
    track VARCHAR,
    source_ips TEXT,  -- JSON array
    dest_ips TEXT,    -- JSON array
    services TEXT     -- JSON array
);
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ritm` | Create new RITM |
| GET | `/api/v1/ritm` | List RITMs (with status filter) |
| GET | `/api/v1/ritm/{ritm_number}` | Get RITM with policies |
| PUT | `/api/v1/ritm/{ritm_number}` | Update status/feedback |
| POST | `/api/v1/ritm/{ritm_number}/policy` | Save policies |
| POST | `/api/v1/ritm/{ritm_number}/pools` | Save input pools |
| POST | `/api/v1/ritm/{ritm_number}/lock` | Acquire approval lock |
| POST | `/api/v1/ritm/{ritm_number}/unlock` | Release approval lock |
| POST | `/api/v1/ritm/{ritm_number}/publish` | Publish to Check Point |

## Frontend Pages

### Dashboard (`/`)

- Lists RITMs by status (My RITMs, For Approval, Approved)
- Polls every 30 seconds for real-time updates
- New RITM creation modal

### RITM Edit (`/ritm/edit/{ritm_number}`)

- Auto-saves policies with 1-second debounce
- Auto-saves input pools when changed
- Domain/Package/Section dropdowns with on-demand loading
- Submit for Approval functionality

### RITM Approve (`/ritm/approve/{ritm_number}`)

- View-only rules display
- Approve/Return with feedback actions
- Lock status display with countdown
- Publish to Check Point (when approved)

## Configuration

### Environment Variables

```bash
# Approval lock timeout (minutes)
APPROVAL_LOCK_MINUTES=30

# Database
DATABASE_URL=sqlite+aiosqlite:///_tmp/cache.db
```

## Testing

14 comprehensive integration tests covering:

- RITM creation (valid format, duplicates, invalid format)
- Policy saving
- Status transitions
- Approval locking (acquire, duplicate lock, release)
- Approve/Return workflow
- Full end-to-end workflow
- List filtering by status

All tests passing.

## Implementation Details

### Status Codes

- `0` - Work in Progress
- `1` - Ready for Approval
- `2` - Approved
- `3` - Completed

### Key Decisions

1. **Natural Keys**: Used `ritm_number` as primary key (not auto-increment ID)
2. **JSON Storage**: IPs and services stored as JSON arrays (simpler than junction tables)
3. **Auto-Save**: Debounced save (1 second) to prevent excessive database writes
4. **AuthContext**: Migrated from localStorage to proper AuthContext for username management
5. **Timezone Handling**: Fixed datetime comparison bug for SQLite (naive datetimes from DB)

### Known Limitations

- Check Point API required for cache refresh and publishing
- Mock mode available for testing without Check Point connection
- 30-minute lock timeout is configurable
