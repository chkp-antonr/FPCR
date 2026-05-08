# RITM State Machine Refactor + Pre-Verify Step — Design Spec

**Date:** 2026-05-08

**Branch:** dev/ritm-v3

**Author:** Anton Razumov

---

## Background

The RITM workflow has four top-level status states and seven per-package attempt states.
Status transitions are currently handled by `if/elif` chains in `update_ritm()` with guards and
side-effects entangled in the same blocks. This makes it impossible to answer "what transitions are
valid from state X?" without reading all handler code.

Additionally, `prompt.md` (`docs/_AI_/2605/260507-RITM_details/`) identified two functional gaps:

1. No standalone pre-verify step — the pre-check is buried inside `try-verify`.
2. `try-verify` allows skipping failed packages via `force_continue`, violating the All-or-No policy.

---

## Scope

### In scope

- Add an explicit transition table for `RITMStatus` (topology only; guards stay in handlers).
- New endpoint `POST /ritm/{number}/pre-verify` — standalone verify of all affected packages,
  hard-stop on any failure, grouped error response.
- Remove `force_continue` from `try-verify`; make it unconditionally All-or-No.

### Out of scope

- `RITMPackageAttemptState` machine refactor (separate session).
- Frontend changes (clear package/section on domain change, object highlighting in evidence).
- DB schema changes.
- Evidence HTML/PDF template changes.
- Existing standalone `POST /verify-policy` debug endpoint (untouched).

---

## Track 1: Transition Table

### New module

**File:** `src/fa/services/ritm_transitions.py`

```python
from fastapi import HTTPException
from fa.models import RITMStatus

ALLOWED_TRANSITIONS: dict[RITMStatus, set[RITMStatus]] = {
    RITMStatus.WORK_IN_PROGRESS:   {RITMStatus.READY_FOR_APPROVAL},
    RITMStatus.READY_FOR_APPROVAL: {RITMStatus.APPROVED, RITMStatus.WORK_IN_PROGRESS},
    RITMStatus.APPROVED:           {RITMStatus.COMPLETED},
    RITMStatus.COMPLETED:          set(),
}

def assert_transition(current: RITMStatus, target: RITMStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition RITM from '{current}' to '{target}'",
        )
```

### Change to `update_ritm()`

`src/fa/routes/ritm.py` — add one call at the top of `update_ritm()`, before any `if/elif`:

```python
assert_transition(ritm.status, request.status)
```

The `if/elif` branches keep their existing guard checks (who can do it) and side-effects
(what happens). The table owns topology; the branches own business rules.

**No DB changes. No new dependencies.**

---

## Track 2: Pre-Verify Endpoint

### Response schema

```python
class PackageVerifyResult(BaseModel):
    package_name: str
    package_uid: str
    passed: bool
    errors: list[str]   # from verify-policy "details" field

class DomainVerifyResult(BaseModel):
    domain_name: str
    domain_uid: str
    packages: list[PackageVerifyResult]

class PreVerifyResponse(BaseModel):
    passed: bool                        # True only if ALL packages passed
    results: list[DomainVerifyResult]
```

### Endpoint

**Route:** `POST /ritm/{ritm_number}/pre-verify`

**File:** `src/fa/routes/ritm_flow.py`

Behaviour:

1. Load saved policies for the RITM; derive unique `(domain_uid, package_uid)` pairs.
2. Return `400` if no policies saved.
3. For each pair, call `verify-policy` via the existing CP API wrapper.
4. Collect results; group by `domain_name → packages`.
5. Set `passed = all packages passed`.
6. Return `PreVerifyResponse` with HTTP 200 regardless of pass/fail
   (caller decides how to surface errors — do not use HTTP 4xx for CP verification failures).

No writes to DB. No sessions opened or closed. Pure read + CP API call.

### Error detail extraction

The Check Point `verify-policy` API returns a `details` list when verification fails.
Each entry is surfaced verbatim as a string in `errors`. If `details` is absent, fall back to
the top-level `message` field.

---

## Track 3: Remove `force_continue` from Try-Verify

### Change to `try_verify()` service method

**File:** `src/fa/services/ritm_workflow_service.py`

- Remove the `force_continue` parameter from the method signature.
- Remove the `force_continue` parameter from `TryVerifyRequest` schema entirely (clients sending it get a validation error, which is the correct signal that the option no longer exists).
- After pre-check failure for any package: abort the entire run, return error immediately.
  Do not start object/rule creation for any remaining packages.

### Behaviour after removal

If the pre-check fails on package N:

1. No objects or rules have been created yet for package N (pre-check is step 1).
2. Packages processed before N are rolled back (same rollback path as post-check failure).
3. `TryVerifyResponse` returns per-package results with `PRECHECK_FAILED_SKIPPED` for package N
   and `rolled_back: true` for any preceding packages that had work done.

If the caller wants to skip broken packages and proceed — they must first fix the policy in
Smart Console, then re-run pre-verify to confirm, then run try-verify.

---

## File Change Summary

| File | Change |
|------|--------|
| `src/fa/services/ritm_transitions.py` | **New** — transition table + `assert_transition()` |
| `src/fa/routes/ritm.py` | Add `assert_transition()` call at top of `update_ritm()` |
| `src/fa/routes/ritm_flow.py` | Add `pre_verify()` endpoint; add `PreVerifyResponse` schema |
| `src/fa/services/ritm_workflow_service.py` | Remove `force_continue`; add pre-verify service method |
| `src/fa/schemas.py` (or inline) | Add `PreVerifyResponse`, `DomainVerifyResult`, `PackageVerifyResult` |

---

## What Is Not Changed

- `POST /verify-policy` standalone debug endpoint — untouched.
- DB schema — no migrations needed.
- `RITMPackageAttemptState` enum — untouched.
- Evidence generation, HTML/PDF templates — untouched.
- Approval lock / editor lock logic — untouched.
- Frontend — out of scope.
