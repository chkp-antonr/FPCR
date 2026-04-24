# RITM Try & Verify Workflow Design

Date: 2026-04-22

Status: Design Approved

Author: AI Assistant

## Overview

Refactor the RITM workflow to match the documented Firewall Policy Change Request flow. The current 3-step workflow (Plan → Apply → Verify) will be replaced with a cleaner 2-step workflow (Plan → Try & Verify), where Try & Verify combines object creation, rule creation, verification, rollback on failure, rule disabling, and evidence generation into a single atomic operation.

## Motivation

The current implementation has several gaps compared to the documented flow:

1. Rules remain enabled after apply (should be disabled)
2. No rollback on verification failure
3. Separate Apply/Verify buttons instead of combined operation
4. No evidence generation after each package
5. Missing session UID persistence for evidence re-creation
6. No publish after successful verification

## Architecture

### Service Layer

```
src/fa/services/
├── package_workflow.py          # NEW: Per-package workflow
└── ritm_workflow_service.py      # NEW: Try & Verify orchestrator
```

### New Models

```
src/fa/models.py
├── TryVerifyResponse             # NEW: Combined response
├── PackageResult                 # NEW: Per-package result
├── CreateResult                  # NEW: Creation result with UIDs
└── RITMSession                   # NEW: Session UID storage
```

### New API Endpoint

```
POST /ritm/{ritm_number}/try-verify
    → Replaces separate /apply and /verify
    → Returns TryVerifyResponse with evidence PDF
```

## Try & Verify Workflow

### Per-Package Flow

For each unique domain/package combination:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. VERIFY FIRST (pre-check)                                 │
│    - Call verify-policy                                     │
│    - On FAIL → Skip package, continue to next               │
└─────────────────────────────────────────────────────────────┘
                    ↓ PASS
┌─────────────────────────────────────────────────────────────┐
│ 2. CREATE OBJECTS AND RULES                                │
│    - Match/create objects via ObjectMatcher                │
│    - Create rules via CheckPointRuleManager                │
│    - Store created UIDs for potential rollback              │
│    - On FAIL → Skip package, continue                      │
└─────────────────────────────────────────────────────────────┘
                    ↓ SUCCESS
┌─────────────────────────────────────────────────────────────┐
│ 3. VERIFY AGAIN (post-creation)                            │
│    - Call verify-policy again                              │
│    - On FAIL → Rollback rules, continue to next             │
└─────────────────────────────────────────────────────────────┘
                    ↓ PASS
┌─────────────────────────────────────────────────────────────┐
│ 4. SUCCESS PATH                                            │
│    - Capture session_changes for this package (evidence)   │
│    - Disable newly created rules                           │
│    - Mark package as successful                             │
└─────────────────────────────────────────────────────────────┘
```

### After All Packages

```
┌─────────────────────────────────────────────────────────────┐
│ 1. COMBINE EVIDENCE                                         │
│    - Merge session_changes from all successful packages     │
│    - Generate combined PDF                                  │
│    - Generate combined HTML                                 │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. STORE SESSION UIDS                                       │
│    - Store session UID per domain in RITMSession table      │
│    - Enables evidence re-creation later                     │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. PUBLISH                                                  │
│    - If any packages succeeded → Publish                    │
│    - Session name: "{ritm_number} {username} Created"       │
└─────────────────────────────────────────────────────────────┘
```

## Service Classes

### PackageWorkflowService

```python
class PackageWorkflowService:
    """Handles per-package workflow operations."""

    async def verify_first(self) -> VerifyResult:
        """Pre-creation verification. Skip package on failure."""

    async def create_objects_and_rules(self) -> CreateResult:
        """Create objects and rules. Return UIDs for rollback."""

    async def verify_again(self) -> VerifyResult:
        """Post-creation verification. Triggers rollback on failure."""

    async def rollback_rules(self, rule_uids: list[str]) -> None:
        """Delete newly created rules when verification fails."""

    async def disable_rules(self, rule_uids: list[str]) -> None:
        """Disable newly created rules after successful verification."""

    async def capture_evidence(self) -> EvidenceData:
        """Capture show-changes for this package's session."""
```

### RITMWorkflowService

```python
class RITMWorkflowService:
    """Orchestrates Try & Verify across all packages."""

    async def try_verify(
        self, ritm_number: str, session: SessionData
    ) -> TryVerifyResponse:
        """Execute full Try & Verify workflow."""

    def _group_by_package(self, ritm_number: str) -> list[PackageInfo]:
        """Group policies by unique domain/package combinations."""

    def _generate_combined_evidence(
        self, evidence_list: list[EvidenceData]
    ) -> tuple[bytes, str]:
        """Combine per-package evidence into single PDF and HTML."""

    async def _publish_session(
        self, ritm_number: str, username: str
    ) -> None:
        """Publish changes with session name format."""
```

## API Changes

### New Endpoint

```python
@router.post("/ritm/{ritm_number}/try-verify")
async def try_verify_ritm(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> TryVerifyResponse:
    """Execute Try & Verify workflow with automatic rollback and disable."""
```

### Comment Out Old Endpoints

```python
# @router.post("/ritm/{ritm_number}/apply")
# async def apply_ritm(...):
#     """DEPRECATED: Use /try-verify instead."""

# @router.post("/ritm/{ritm_number}/verify")
# async def verify_ritm(...):
#     """DEPRECATED: Verification now internal to /try-verify."""
```

### New Re-creation Endpoint

```python
@router.post("/ritm/{ritm_number}/recreate-evidence")
async def recreate_evidence(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> EvidenceResponse:
    """Re-generate evidence from stored session UIDs.

    Fetches fresh show-changes from Check Point to capture any manual changes.
    """
```

## Models

```python
class PackageResult(BaseModel):
    package: str
    status: Literal["success", "skipped", "create_failed", "verify_failed"]
    rules_created: int = 0
    objects_created: int = 0
    errors: list[str] = []

class TryVerifyResponse(BaseModel):
    results: list[PackageResult]
    evidence_pdf: bytes
    evidence_html: str
    published: bool

class CreateResult(BaseModel):
    objects_created: int
    rules_created: int
    created_rule_uids: list[str]
    created_object_uids: list[str]
    errors: list[str] = []

class EvidenceData(BaseModel):
    domain_name: str
    package_name: str
    session_changes: dict[str, Any]

class RITMSession(Base):
    """Store session UIDs per domain for each RITM."""
    __tablename__ = "ritm_sessions"

    id: int = Field(primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number")
    domain_name: str
    domain_uid: str
    session_uid: str
    sid: str
    created_at: datetime = Field(default_factory=datetime.now(UTC))
```

## Frontend Changes

### RitmEdit.tsx

1. Remove "Verify" step and button
2. Rename "Apply" → "Try & Verify"
3. Remove `verifyResult` state
4. Add `tryVerifyResult` state
5. Update workflow steps: `idle` → `planned` → `verified`
6. Add "Re-create Evidence" button (shown when evidence exists and not approved)

```typescript
type WorkflowStep = 'idle' | 'planned' | 'verified';

const handleTryVerify = async () => {
  const response = await ritmApi.tryVerifyRitm(ritmNumber);
  setTryVerifyResult(response);
  setWorkflowStep('verified');
  // Display per-package results and evidence
};

const handleRecreateEvidence = async () => {
  const response = await ritmApi.recreateEvidence(ritmNumber);
  setEvidenceHtml(response.evidence_html);
};
```

### endpoints.ts

```typescript
tryVerifyRitm(ritmNumber: string): Promise<TryVerifyResponse> {
  return this.post(`/ritm/${ritmNumber}/try-verify`);
}

recreateEvidence(ritmNumber: string): Promise<EvidenceResponse> {
  return this.post(`/ritm/${ritmNumber}/recreate-evidence`);
}
```

## Error Handling

### Error Response Structure

All errors are collected per-package and returned in the response. The operation never fails partially — if one package fails, others continue processing.

### Logging Strategy

- Structured logging at each workflow step with package prefix
- Format: `[Package] Step: {step_name} | Status: {PASS/FAIL/SKIP}`
- Frontend "Workflow Activity" panel displays log entries

### Rollback Behavior

| Failure Point | Action |
|---------------|--------|
| Pre-verify fails | Skip package, no rollback needed |
| Object/rule creation fails | Skip package, nothing to rollback |
| Post-verify fails | Rollback created rules, continue |
| Disable fails | Log warning, don't fail operation |
| Publish fails | Log error, return partial success |

## Evidence Generation

### Evidence #1 (Original - Created by Engineer 1)

- Generated after each successful package during Try & Verify
- Combined into single PDF/HTML at end
- Shows disabled rules (as created, then disabled)
- Stored in `ritm.session_changes_evidence1`

### Evidence #2 (Approved - After Engineer 2 Approves)

- Generated when approver clicks "Approve"
- Shows enabled rules and any changes made by approver
- Stored in `ritm.session_changes_evidence2`
- Implementation: Future enhancement (not in this design)

### Re-creation

Users can re-create evidence anytime before approval:

- Fetches stored session UIDs from `RITMSession` table
- Calls `show-changes` with `to-session` parameter
- Captures any manual changes made since original Try & Verify
- Updates stored evidence PDF/HTML

## Database Schema Changes

### New Table

```sql
CREATE TABLE ritm_sessions (
    id INTEGER PRIMARY KEY,
    ritm_number VARCHAR NOT NULL REFERENCES ritm(ritm_number),
    domain_name VARCHAR NOT NULL,
    domain_uid VARCHAR NOT NULL,
    session_uid VARCHAR NOT NULL,
    sid VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

**Migration:** Delete `_tmp/cache.db` on schema errors (no Alembic).

## Implementation Order

1. Create `PackageWorkflowService` class
2. Create `RITMWorkflowService` class
3. Add new models to `models.py`
4. Create new `/try-verify` endpoint
5. Create new `/recreate-evidence` endpoint
6. Comment out old `/apply` and `/verify` endpoints
7. Update `RitmEdit.tsx` frontend
8. Update `endpoints.ts` API client
9. Test with multi-domain, multi-package RITM
10. Test rollback scenarios
11. Test evidence re-creation

## Testing Considerations

### Unit Tests

- `PackageWorkflowService.verify_first()` — mock PolicyVerifier
- `PackageWorkflowService.create_objects_and_rules()` — mock ObjectMatcher, RuleManager
- `PackageWorkflowService.rollback_rules()` — mock RuleManager.delete()
- `PackageWorkflowService.disable_rules()` — mock api_call

### Integration Tests

- Successful Try & Verify with single package
- Successful Try & Verify with multiple packages
- Pre-verify failure (skip package)
- Post-verify failure with rollback
- Partial success (some packages fail, some succeed)
- Evidence re-creation after manual changes
- Session UID persistence

## Open Questions

None at this time.
