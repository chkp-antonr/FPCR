# RITM State Machine Refactor + Pre-Verify Step — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit status-transition table to `update_ritm()`, add a formal `/pre-verify` workflow endpoint, and remove the `force_continue` escape hatch so Try & Verify is unconditionally All-or-No.

**Architecture:** A new module `ritm_transitions.py` owns the topology graph; existing handler `if/elif` branches keep their business-rule guards. The pre-verify endpoint is a thin route that delegates to the already-existing `verify_policy_grouped()` service method. Removing `force_continue` collapses a dead branch from `try_verify()`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, pytest + pytest-asyncio.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `src/fa/services/ritm_transitions.py` | **Create** | Transition table + `assert_transition()` |
| `src/fa/tests/test_ritm_transitions.py` | **Create** | Unit tests for transition table |
| `src/fa/routes/ritm.py` | **Modify** | Import + call `assert_transition()` at top of `update_ritm()` (line 219) |
| `src/fa/routes/ritm_flow.py` | **Modify** | Add `pre_verify` endpoint; remove `force_continue` from `try_verify_ritm` call |
| `src/fa/services/ritm_workflow_service.py` | **Modify** | Remove `force_continue` param + branch from `try_verify()` |
| `src/fa/models.py` | **Modify** | Remove `force_continue` field from `TryVerifyRequest` |

---

## Task 1: Create the transition table module

**Files:**
- Create: `src/fa/services/ritm_transitions.py`
- Create: `src/fa/tests/test_ritm_transitions.py`

- [ ] **Step 1: Write the failing tests**

```python
# src/fa/tests/test_ritm_transitions.py
"""Tests for RITM status transition table."""

import pytest
from fastapi import HTTPException

from fa.models import RITMStatus
from fa.services.ritm_transitions import ALLOWED_TRANSITIONS, assert_transition

WIP = RITMStatus.WORK_IN_PROGRESS
RFA = RITMStatus.READY_FOR_APPROVAL
APP = RITMStatus.APPROVED
COM = RITMStatus.COMPLETED


def test_allowed_transitions_covers_all_states():
    """Every RITMStatus value must appear as a key in the table."""
    for status in RITMStatus:
        assert status in ALLOWED_TRANSITIONS, f"{status} missing from ALLOWED_TRANSITIONS"


def test_valid_transitions_do_not_raise():
    valid = [
        (WIP, RFA),
        (RFA, APP),
        (RFA, WIP),
        (APP, COM),
    ]
    for current, target in valid:
        assert_transition(current, target)  # must not raise


def test_invalid_transition_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        assert_transition(WIP, APP)  # cannot skip READY_FOR_APPROVAL
    assert exc_info.value.status_code == 400


def test_completed_is_terminal():
    for target in RITMStatus:
        with pytest.raises(HTTPException):
            assert_transition(COM, target)


def test_approved_cannot_go_to_wip():
    with pytest.raises(HTTPException):
        assert_transition(APP, WIP)


def test_wip_cannot_go_to_completed():
    with pytest.raises(HTTPException):
        assert_transition(WIP, COM)
```

- [ ] **Step 2: Run tests — confirm they fail with ImportError**

```bash
uv run pytest src/fa/tests/test_ritm_transitions.py -v
```

Expected: `ModuleNotFoundError: No module named 'fa.services.ritm_transitions'`

- [ ] **Step 3: Create the module**

```python
# src/fa/services/ritm_transitions.py
"""Explicit RITM status transition topology.

The table here owns *which* transitions are valid.
Guards (who is allowed) and side-effects (what happens) stay in the callers.
"""

from fastapi import HTTPException

from fa.models import RITMStatus

ALLOWED_TRANSITIONS: dict[RITMStatus, set[RITMStatus]] = {
    RITMStatus.WORK_IN_PROGRESS:   {RITMStatus.READY_FOR_APPROVAL},
    RITMStatus.READY_FOR_APPROVAL: {RITMStatus.APPROVED, RITMStatus.WORK_IN_PROGRESS},
    RITMStatus.APPROVED:           {RITMStatus.COMPLETED},
    RITMStatus.COMPLETED:          set(),
}


def assert_transition(current: RITMStatus, target: RITMStatus) -> None:
    """Raise HTTP 400 if target is not a legal successor of current."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition RITM from '{current.name}' to '{target.name}'",
        )
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
uv run pytest src/fa/tests/test_ritm_transitions.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/fa/services/ritm_transitions.py src/fa/tests/test_ritm_transitions.py
git commit -m "feat: add RITM status transition table"
```

---

## Task 2: Wire transition guard into `update_ritm()`

**Files:**
- Modify: `src/fa/routes/ritm.py`

The target block is lines 219–282 in `ritm.py`. The `if request.status is not None:` block needs one call before its first `if/elif`.

- [ ] **Step 1: Add the import**

Open `src/fa/routes/ritm.py`. Find the existing imports at the top. Add after the other `fa.*` imports:

```python
from fa.services.ritm_transitions import assert_transition
```

- [ ] **Step 2: Insert the guard**

Find this block (line ~219):

```python
        if request.status is not None:
            if request.status == RITMStatus.READY_FOR_APPROVAL:
```

Replace with:

```python
        if request.status is not None:
            assert_transition(ritm.status, RITMStatus(request.status))
            if request.status == RITMStatus.READY_FOR_APPROVAL:
```

`ritm.status` is the current DB value; `request.status` is an `int` from the request body — wrap it in `RITMStatus()` so `assert_transition` receives the enum.

- [ ] **Step 3: Verify with mypy**

```bash
uv run mypy src/fa/routes/ritm.py --ignore-missing-imports
```

Expected: no new errors.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest src/fa/tests/ -v
```

Expected: all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/fa/routes/ritm.py
git commit -m "feat: enforce status transition table in update_ritm"
```

---

## Task 3: Add `POST /pre-verify` endpoint

The service method `verify_policy_grouped()` already exists in `RITMWorkflowService`. This task adds a new route that exposes it as a named workflow step, distinct from the existing `/verify-policy` debug route.

**Files:**
- Modify: `src/fa/routes/ritm_flow.py`

- [ ] **Step 1: Add the endpoint**

Open `src/fa/routes/ritm_flow.py`. Find the existing `verify_policy_pre_check` function (line ~361). Insert the new function **directly above it** (before `@router.post("/ritm/{ritm_number}/verify-policy")`):

```python
@router.post("/ritm/{ritm_number}/pre-verify")
async def pre_verify(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> GroupedVerifyResponse:
    """Workflow step 1: verify all affected policy packages before creating anything.

    Runs verify-policy against every unique (domain, package) from saved policies.
    Returns grouped results (domain → packages → errors).
    HTTP 200 regardless of pass/fail — check `all_passed` in the response body.
    Returns HTTP 400 if no policies are saved for this RITM.
    """
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            workflow = RITMWorkflowService(
                client=client,
                ritm_number=ritm_number,
                username=session.username,
            )
            packages = await workflow._group_by_package()
            if not packages:
                raise HTTPException(status_code=400, detail="No policies found for RITM")
            return await workflow.verify_policy_grouped(packages)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in pre_verify for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 2: Run mypy on the file**

```bash
uv run mypy src/fa/routes/ritm_flow.py --ignore-missing-imports
```

Expected: no new errors.

- [ ] **Step 3: Run existing tests**

```bash
uv run pytest src/fa/tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/fa/routes/ritm_flow.py
git commit -m "feat: add POST /pre-verify as formal workflow step"
```

---

## Task 4: Remove `force_continue` — All-or-No Try & Verify

Three changes in three files, all part of the same logical removal. Do them together in one commit.

**Files:**
- Modify: `src/fa/models.py` — remove field from `TryVerifyRequest`
- Modify: `src/fa/services/ritm_workflow_service.py` — remove param + branch
- Modify: `src/fa/routes/ritm_flow.py` — remove param from call site

- [ ] **Step 1: Write a test that will fail once force_continue is removed from the schema**

Add to `src/fa/tests/test_ritm_workflow_service.py`:

```python
from pydantic import ValidationError
from fa.models import TryVerifyRequest


def test_try_verify_request_rejects_force_continue():
    """force_continue must not be accepted — it was removed in favour of All-or-No policy."""
    with pytest.raises(ValidationError):
        TryVerifyRequest(force_continue=True)


def test_try_verify_request_defaults_valid():
    req = TryVerifyRequest()
    assert req.skip_package_uids == []
```

- [ ] **Step 2: Run that test — expect it to FAIL (force_continue still accepted)**

```bash
uv run pytest src/fa/tests/test_ritm_workflow_service.py::test_try_verify_request_rejects_force_continue -v
```

Expected: FAIL — `TryVerifyRequest(force_continue=True)` currently succeeds.

- [ ] **Step 3: Remove `force_continue` from `TryVerifyRequest` in `models.py`**

Find in `src/fa/models.py` (lines 442–446):

```python
class TryVerifyRequest(BaseModel):
    """Request body for the try-verify endpoint."""

    force_continue: bool = False
    skip_package_uids: list[str] = []
```

Replace with:

```python
class TryVerifyRequest(BaseModel):
    """Request body for the try-verify endpoint."""

    skip_package_uids: list[str] = []
    model_config = {"extra": "forbid"}
```

`extra = "forbid"` makes Pydantic reject any unknown field (including `force_continue`) with a `ValidationError`.

- [ ] **Step 4: Remove `force_continue` from `try_verify()` in `ritm_workflow_service.py`**

Find the method signature (lines 50–63):

```python
    async def try_verify(
        self,
        force_continue: bool = False,
        skip_package_uids: set[str] | None = None,
    ) -> TryVerifyResponse:
        """Execute full Try & Verify workflow.

        Args:
            force_continue: When True, packages that fail pre-check are recorded
                as PRECHECK_FAILED_SKIPPED and workflow continues for the rest.
                When False (default), any pre-check failure aborts the whole run.
            skip_package_uids: Optional explicit set of package UIDs to skip
                (e.g. pre-populated from a prior /verify-policy call).
        """
```

Replace with:

```python
    async def try_verify(
        self,
        skip_package_uids: set[str] | None = None,
    ) -> TryVerifyResponse:
        """Execute full Try & Verify workflow (All-or-No policy).

        Any pre-check failure aborts the entire run — no partial execution.
        Use POST /pre-verify first to surface verification errors before calling this.

        Args:
            skip_package_uids: Optional explicit set of package UIDs to skip.
        """
```

Find the log line (line ~78):

```python
        self.logger.info(
            f"Try & Verify for RITM {self.ritm_number}: "
            f"Processing {len(packages)} unique package(s) "
            f"(force_continue={force_continue})"
        )
```

Replace with:

```python
        self.logger.info(
            f"Try & Verify for RITM {self.ritm_number}: "
            f"Processing {len(packages)} unique package(s)"
        )
```

Find the pre-check failure block (lines 136–149):

```python
                if not force_continue:
                    # Abort the whole run – caller must retry with force_continue=True
                    self.logger.warning(
                        f"Pre-check failed for {pkg_info.package_name}; "
                        "aborting (force_continue=False)"
                    )
                    return TryVerifyResponse(
                        results=results,
                        evidence_pdf=None,
                        evidence_html=None,
                        published=False,
                        session_changes=None,
                    )
                continue
```

Replace with:

```python
                self.logger.warning(
                    f"Pre-check failed for {pkg_info.package_name}; aborting run"
                )
                return TryVerifyResponse(
                    results=results,
                    evidence_pdf=None,
                    evidence_html=None,
                    published=False,
                    session_changes=None,
                )
```

- [ ] **Step 5: Remove `force_continue` from the call site in `ritm_flow.py`**

Find in `src/fa/routes/ritm_flow.py` (lines 434–437):

```python
            result = await workflow.try_verify(
                force_continue=body.force_continue,
                skip_package_uids=set(body.skip_package_uids),
            )
```

Replace with:

```python
            result = await workflow.try_verify(
                skip_package_uids=set(body.skip_package_uids),
            )
```

Also remove the `force_continue` mention from the `try_verify_ritm` docstring (line ~407):

```python
    1. Verify policy (pre-check) – if failed and force_continue=False, abort.
```

Replace with:

```python
    1. Verify policy (pre-check) – if failed, abort entire run (All-or-No policy).
```

- [ ] **Step 6: Run mypy across all three files**

```bash
uv run mypy src/fa/models.py src/fa/services/ritm_workflow_service.py src/fa/routes/ritm_flow.py --ignore-missing-imports
```

Expected: no new errors.

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest src/fa/tests/ -v
```

Expected: all pass, including the new `test_try_verify_request_rejects_force_continue`.

- [ ] **Step 8: Commit**

```bash
git add src/fa/models.py src/fa/services/ritm_workflow_service.py src/fa/routes/ritm_flow.py src/fa/tests/test_ritm_workflow_service.py
git commit -m "feat: remove force_continue — try-verify is now All-or-No"
```

---

## Self-Review Checklist

- [x] **Spec coverage**
  - Transition table → Task 1 + 2 ✓
  - `/pre-verify` endpoint → Task 3 ✓
  - All-or-No / remove `force_continue` → Task 4 ✓
- [x] **No placeholders** — all code blocks are complete and runnable.
- [x] **Type consistency** — `assert_transition(current: RITMStatus, target: RITMStatus)` used consistently; `RITMStatus(request.status)` cast at call site; `GroupedVerifyResponse` return type matches existing model.
- [x] **`model_config = {"extra": "forbid"}`** added to `TryVerifyRequest` so Pydantic v2 rejects unknown fields (including old `force_continue` from stale clients).
- [x] **`skip_package_uids` is preserved** — it is a separate mechanism from `force_continue` and is not removed.
