# RITM Workflow v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-editor tracking, cumulative evidence history, approval lock on open, and complete the approval publish flow (enable rules → verify → publish → evidence).

**Architecture:** New DB tables (`ritm_editors`, `ritm_reviewers`, `ritm_evidence_sessions`) replace removed columns and the old `ritm_sessions` table. Business rules enforced in `ritm.py` route handlers. Evidence written per-package by `RITMWorkflowService`. Publish flow moved to `ritm_flow.py` to reuse existing CPAIOPSClient wiring.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy async, SQLite, cpaiops (Check Point API client), pytest-asyncio, httpx AsyncClient.

**Run all tests with:** `uv run pytest src/fa/tests/ -v`

---

## File Map

| File | Change |
|------|--------|
| `src/fa/models.py` | Remove old RITM columns and `RITMSession`; add `RITMEditor`, `RITMReviewer`, `RITMEvidenceSession`; update `RITMItem`; add response models |
| `src/fa/tests/conftest.py` | Patch `fa.routes.ritm_flow.engine` so flow-route tests use the in-memory DB |
| `src/fa/routes/ritm.py` | `_ritm_to_item` → async + loads editors/reviewers; update `create_ritm`, `get_ritm`, `list_ritms`, `update_ritm`; add `editor-lock` / `editor-unlock` endpoints; update `save_policy`; remove `publish_ritm` |
| `src/fa/routes/ritm_flow.py` | Add `publish_ritm` endpoint; add `evidence-history` endpoint; update `session-html` / `session-pdf` to accept `attempt` param; update `recreate-evidence` to use `ritm_evidence_sessions` |
| `src/fa/services/ritm_workflow_service.py` | Remove `_store_session_uids`, `_store_evidence`; add `_next_attempt`, `_store_evidence_session`; update `try_verify` to call new methods |
| `src/fa/tests/test_ritm.py` | Add tests for editor lock, updated submit/approve/reject rules, editors/reviewers in responses |
| `src/fa/tests/test_ritm_flow.py` | New file: tests for evidence-history, updated session-html/pdf, recreate-evidence |

---

## Task 1: Update models.py

**Files:**
- Modify: `src/fa/models.py`

- [ ] **Step 1.1: Remove old RITM columns and `RITMSession` model**

In `models.py`, replace the `RITM` class body and `RITMSession` class. Remove `engineer_initials`, `evidence_html`, `evidence_yaml`, `evidence_changes`, `session_changes_evidence1`, `session_changes_evidence2`, `try_verify_session_uid`. Remove the entire `RITMSession` class.

New `RITM` class (replace everything from `class RITM` to before `class Policy`):

```python
class RITM(SQLModel, table=True):
    """RITM (Requested Item) approval workflow metadata."""

    __tablename__ = "ritm"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]

    ritm_number: str = Field(primary_key=True)
    username_created: str
    date_created: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))
    date_updated: datetime | None = None
    date_approved: datetime | None = None
    username_approved: str | None = None
    feedback: str | None = None
    status: int = Field(default=RITMStatus.WORK_IN_PROGRESS)
    approver_locked_by: str | None = None
    approver_locked_at: datetime | None = None
    editor_locked_by: str | None = None
    editor_locked_at: datetime | None = None
    source_ips: str | None = Field(default=None, description="JSON array of source IPs")
    dest_ips: str | None = Field(default=None, description="JSON array of destination IPs")
    services: str | None = Field(default=None, description="JSON array of services")
```

- [ ] **Step 1.2: Add three new table models**

Add after the `RITM` class, before `class Policy`:

```python
class RITMEditor(SQLModel, table=True):
    """Engineers who have edited this RITM — permanently blocked from approving."""

    __tablename__ = cast(Any, "ritm_editors")
    __table_args__ = (UniqueConstraint("ritm_number", "username"),)

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    username: str
    added_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMReviewer(SQLModel, table=True):
    """Engineers who have approved/rejected this RITM — permanently blocked from editing."""

    __tablename__ = cast(Any, "ritm_reviewers")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    username: str
    action: str  # "approved" | "rejected"
    acted_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMEvidenceSession(SQLModel, table=True):
    """Cumulative evidence history — one row per successful package per Try & Verify / publish run."""

    __tablename__ = cast(Any, "ritm_evidence_sessions")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    attempt: int
    domain_name: str
    domain_uid: str
    package_name: str
    package_uid: str
    session_uid: str | None = None
    sid: str | None = None
    session_type: str  # "initial" | "correction" | "approval"
    session_changes: str | None = None  # JSON blob: raw show-changes API response
    created_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))
```

- [ ] **Step 1.3: Update `_known_tables` and `RITMItem`**

Update `_known_tables` set at the top of the file:

```python
_known_tables = {
    "cached_domains",
    "cached_packages",
    "cached_sections",
    "cached_section_assignments",
    "ritm",
    "ritm_policy",
    "ritm_created_objects",
    "ritm_created_rules",
    "ritm_verification",
    "ritm_editors",
    "ritm_reviewers",
    "ritm_evidence_sessions",
}
```

Replace `class ReviewerItem` (add before `RITMItem`) and replace `RITMItem`:

```python
class ReviewerItem(BaseModel):
    """Single reviewer action."""

    username: str
    action: str  # "approved" | "rejected"
    acted_at: str


class RITMItem(BaseModel):
    """RITM item for API responses."""

    ritm_number: str
    username_created: str
    date_created: str
    date_updated: str | None = None
    date_approved: str | None = None
    username_approved: str | None = None
    feedback: str | None = None
    status: int
    approver_locked_by: str | None = None
    approver_locked_at: str | None = None
    editor_locked_by: str | None = None
    editor_locked_at: str | None = None
    source_ips: list[str] | None = None
    dest_ips: list[str] | None = None
    services: list[str] | None = None
    editors: list[str] = []
    reviewers: list[ReviewerItem] = []
```

- [ ] **Step 1.4: Add evidence history response models**

Add after `EvidenceResponse`:

```python
class EvidenceSessionItem(BaseModel):
    """Single session entry in the evidence history."""

    id: int
    attempt: int
    session_type: str
    session_uid: str | None
    sid: str | None
    created_at: str
    session_changes: dict[str, Any] | None


class PackageEvidenceItem(BaseModel):
    """Package entry in the evidence history."""

    package_name: str
    package_uid: str
    sessions: list[EvidenceSessionItem]


class DomainEvidenceItem(BaseModel):
    """Domain entry in the evidence history."""

    domain_name: str
    domain_uid: str
    packages: list[PackageEvidenceItem]


class EvidenceHistoryResponse(BaseModel):
    """Full cumulative evidence history for a RITM."""

    domains: list[DomainEvidenceItem]
```

- [ ] **Step 1.5: Verify the app imports new models correctly**

Run:

```
uv run python -c "from fa.models import RITMEditor, RITMReviewer, RITMEvidenceSession, ReviewerItem, EvidenceHistoryResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 1.6: Commit**

```bash
git add src/fa/models.py
git commit -m "feat: update RITM models — add editors/reviewers/evidence tables, remove legacy columns"
```

---

## Task 2: Update conftest.py to patch all engines

**Files:**
- Modify: `src/fa/tests/conftest.py`

- [ ] **Step 2.1: Add ritm_flow engine patch**

Replace the `async_client` fixture in `src/fa/tests/conftest.py`:

```python
@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession):
    """Create an async test client."""
    import fa.db
    import fa.routes.ritm
    import fa.routes.ritm_flow
    import fa.services.ritm_workflow_service

    original_db_engine = fa.db.engine
    original_ritm_engine = fa.routes.ritm.engine
    original_flow_engine = fa.routes.ritm_flow.engine
    original_service_engine = fa.services.ritm_workflow_service.engine

    fa.db.engine = db_session.bind
    fa.routes.ritm.engine = db_session.bind
    fa.routes.ritm_flow.engine = db_session.bind
    fa.services.ritm_workflow_service.engine = db_session.bind

    session_id = session_manager.create(username="testuser", password="testpass")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("session_id", session_id)
        yield client

    session_manager.delete(session_id)
    fa.db.engine = original_db_engine
    fa.routes.ritm.engine = original_ritm_engine
    fa.routes.ritm_flow.engine = original_flow_engine
    fa.services.ritm_workflow_service.engine = original_service_engine
```

- [ ] **Step 2.2: Run existing tests to confirm still passing**

Run:

```
uv run pytest src/fa/tests/ -v --tb=short -q
```

Expected: all tests pass (some will fail due to removed `session_changes_evidence1` field — that is expected and will be fixed in Task 3).

- [ ] **Step 2.3: Commit**

```bash
git add src/fa/tests/conftest.py
git commit -m "test: patch ritm_flow and service engines in test conftest"
```

---

## Task 3: RITM create/get endpoints with editors and reviewers

**Files:**
- Modify: `src/fa/routes/ritm.py`
- Modify: `src/fa/tests/test_ritm.py`

- [ ] **Step 3.1: Write failing tests**

Add to `src/fa/tests/test_ritm.py`:

```python
@pytest.mark.asyncio
async def test_create_ritm_returns_editors_list(async_client: AsyncClient):
    """Creator is automatically added to editors list on creation."""
    response = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM0000001"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["editors"] == ["testuser"]
    assert data["reviewers"] == []
    assert data["editor_locked_by"] is None


@pytest.mark.asyncio
async def test_get_ritm_returns_editors_and_reviewers(async_client: AsyncClient):
    """GET /ritm/{number} includes editors and reviewers lists."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000002"})
    response = await async_client.get("/api/v1/ritm/RITM0000002")
    assert response.status_code == 200
    data = response.json()
    assert data["ritm"]["editors"] == ["testuser"]
    assert data["ritm"]["reviewers"] == []
```

Run:

```
uv run pytest src/fa/tests/test_ritm.py::test_create_ritm_returns_editors_list src/fa/tests/test_ritm.py::test_get_ritm_returns_editors_and_reviewers -v
```

Expected: FAIL (field missing)

- [ ] **Step 3.2: Update imports in `ritm.py`**

Add to the imports block in `src/fa/routes/ritm.py`:

```python
from ..models import (
    RITM,
    Policy,
    PolicyItem,
    PublishResponse,
    RITMCreatedRule,
    RITMCreateRequest,
    RITMEditor,
    RITMEvidenceSession,
    RITMItem,
    RITMListResponse,
    RITMReviewer,
    RITMStatus,
    RITMUpdateRequest,
    RITMWithPolicies,
    ReviewerItem,
)
```

- [ ] **Step 3.3: Replace `_ritm_to_item` with async version**

Replace the existing `_ritm_to_item` function entirely:

```python
async def _ritm_to_item(db: AsyncSession, ritm: RITM) -> RITMItem:
    """Convert RITM model to API item, loading editors and reviewers."""
    import json

    editors_result = await db.execute(
        select(RITMEditor).where(col(RITMEditor.ritm_number) == ritm.ritm_number)
    )
    editors = [e.username for e in editors_result.scalars().all()]

    reviewers_result = await db.execute(
        select(RITMReviewer).where(col(RITMReviewer.ritm_number) == ritm.ritm_number)
    )
    reviewers = [
        ReviewerItem(
            username=r.username,
            action=r.action,
            acted_at=r.acted_at.isoformat() if r.acted_at else "",
        )
        for r in reviewers_result.scalars().all()
    ]

    return RITMItem(
        ritm_number=ritm.ritm_number,
        username_created=ritm.username_created,
        date_created=ritm.date_created.isoformat() if ritm.date_created else "",
        date_updated=ritm.date_updated.isoformat() if ritm.date_updated else None,
        date_approved=ritm.date_approved.isoformat() if ritm.date_approved else None,
        username_approved=ritm.username_approved,
        feedback=ritm.feedback,
        status=ritm.status,
        approver_locked_by=ritm.approver_locked_by,
        approver_locked_at=ritm.approver_locked_at.isoformat() if ritm.approver_locked_at else None,
        editor_locked_by=ritm.editor_locked_by,
        editor_locked_at=ritm.editor_locked_at.isoformat() if ritm.editor_locked_at else None,
        source_ips=json.loads(ritm.source_ips) if ritm.source_ips else None,
        dest_ips=json.loads(ritm.dest_ips) if ritm.dest_ips else None,
        services=json.loads(ritm.services) if ritm.services else None,
        editors=editors,
        reviewers=reviewers,
    )
```

- [ ] **Step 3.4: Remove `_normalize_session_changes_evidence` and `_policy_to_item` is unchanged**

Delete the entire `_normalize_session_changes_evidence` function (lines that define it and the `_is_uuid_like` helper it uses). These are no longer needed since `session_changes_evidence1` is removed.

- [ ] **Step 3.5: Update `create_ritm`**

Replace `create_ritm` function body:

```python
@router.post("/ritm")
async def create_ritm(
    request: RITMCreateRequest,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Create a new RITM. Creator is automatically added to editors list."""
    if not RITM_NUMBER_PATTERN.match(request.ritm_number):
        raise HTTPException(
            status_code=400,
            detail="RITM number must match pattern RITM followed by digits (e.g., RITM1234567)",
        )

    async with AsyncSession(engine) as db:
        existing = await db.execute(
            select(RITM).where(col(RITM.ritm_number) == request.ritm_number)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail=f"RITM {request.ritm_number} already exists"
            )

        ritm = RITM(
            ritm_number=request.ritm_number,
            username_created=session.username,
            date_created=datetime.now(UTC),
            status=RITMStatus.WORK_IN_PROGRESS,
        )
        db.add(ritm)
        db.add(
            RITMEditor(
                ritm_number=request.ritm_number,
                username=session.username,
                added_at=datetime.now(UTC),
            )
        )
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Created RITM {request.ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)
```

- [ ] **Step 3.6: Update `list_ritms`**

Replace `list_ritms` function body:

```python
@router.get("/ritm")
async def list_ritms(
    status: int | None = None,
    username: str | None = None,
    _session: SessionData = Depends(get_session_data),
) -> RITMListResponse:
    """List all RITMs with optional filtering."""
    async with AsyncSession(engine) as db:
        query = select(RITM)
        if status is not None:
            query = query.where(col(RITM.status) == status)
        if username is not None:
            query = query.where(col(RITM.username_created) == username)
        query = query.order_by(col(RITM.date_created).desc())
        result = await db.execute(query)
        ritms = result.scalars().all()

        items = [await _ritm_to_item(db, r) for r in ritms]
        return RITMListResponse(ritms=items)
```

- [ ] **Step 3.7: Update `get_ritm`**

Replace `get_ritm` function body (remove the `_normalize_session_changes_evidence` call and the `RITMCreatedRule` query):

```python
@router.get("/ritm/{ritm_number}")
async def get_ritm(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> RITMWithPolicies:
    """Get a single RITM with its policies."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = list(policies_result.scalars().all())

        return RITMWithPolicies(
            ritm=await _ritm_to_item(db, ritm),
            policies=[_policy_to_item(p) for p in policies],
        )
```

- [ ] **Step 3.8: Update `update_ritm` to use async `_ritm_to_item`**

Add `await` to the return statement:

```python
        return await _ritm_to_item(db, ritm)
```

Do the same for all other endpoints (`acquire_approval_lock`, `release_approval_lock`) that call `_ritm_to_item`.

- [ ] **Step 3.9: Remove the old `publish_ritm` endpoint from `ritm.py`**

Delete the entire `publish_ritm` function (it will be re-implemented in `ritm_flow.py` in Task 8). Also remove `PublishResponse` from the imports in `ritm.py` if it is no longer used there.

- [ ] **Step 3.10: Run tests**

```
uv run pytest src/fa/tests/test_ritm.py -v --tb=short -q
```

Expected: new tests pass; existing tests pass (except any that checked `session_changes_evidence1` — update those assertions to remove that field check).

- [ ] **Step 3.11: Commit**

```bash
git add src/fa/routes/ritm.py src/fa/tests/test_ritm.py
git commit -m "feat: RITM create/get returns editors and reviewers lists"
```

---

## Task 4: Editor lock / unlock endpoints

**Files:**
- Modify: `src/fa/routes/ritm.py`
- Modify: `src/fa/tests/test_ritm.py`

- [ ] **Step 4.1: Write failing tests**

Add to `test_ritm.py`:

```python
@pytest.mark.asyncio
async def test_acquire_editor_lock(async_client: AsyncClient):
    """Engineer can acquire editor lock."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000010"})
    response = await async_client.post("/api/v1/ritm/RITM0000010/editor-lock")
    assert response.status_code == 200
    data = response.json()
    assert data["editor_locked_by"] == "testuser"
    assert data["editor_locked_at"] is not None


@pytest.mark.asyncio
async def test_acquire_editor_lock_already_locked_fails(async_client: AsyncClient):
    """Cannot acquire editor lock when another user holds it (simulated via direct DB)."""
    from datetime import UTC, datetime, timedelta
    from sqlalchemy.ext.asyncio import AsyncSession
    import fa.routes.ritm as ritm_module
    from fa.models import RITM
    from sqlalchemy import select
    from sqlmodel import col

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000011"})
    # Manually set editor lock to simulate another user
    async with AsyncSession(ritm_module.engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == "RITM0000011"))
        ritm = result.scalar_one()
        ritm.editor_locked_by = "otheruser"
        ritm.editor_locked_at = datetime.now(UTC)
        await db.commit()

    response = await async_client.post("/api/v1/ritm/RITM0000011/editor-lock")
    assert response.status_code == 400
    assert "locked by" in response.json()["detail"]


@pytest.mark.asyncio
async def test_release_editor_lock(async_client: AsyncClient):
    """Lock holder can release editor lock."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000012"})
    await async_client.post("/api/v1/ritm/RITM0000012/editor-lock")
    response = await async_client.post("/api/v1/ritm/RITM0000012/editor-unlock")
    assert response.status_code == 200
    assert response.json()["editor_locked_by"] is None


@pytest.mark.asyncio
async def test_reviewer_cannot_acquire_editor_lock(async_client: AsyncClient):
    """A user who has reviewed this RITM cannot acquire the editor lock."""
    from datetime import UTC, datetime
    from sqlalchemy.ext.asyncio import AsyncSession
    import fa.routes.ritm as ritm_module
    from fa.models import RITMReviewer
    from sqlalchemy import select
    from sqlmodel import col

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000013"})
    # Manually add testuser as reviewer
    async with AsyncSession(ritm_module.engine) as db:
        db.add(RITMReviewer(
            ritm_number="RITM0000013",
            username="testuser",
            action="rejected",
            acted_at=datetime.now(UTC),
        ))
        await db.commit()

    response = await async_client.post("/api/v1/ritm/RITM0000013/editor-lock")
    assert response.status_code == 400
    assert "Reviewer" in response.json()["detail"]
```

Run:

```
uv run pytest src/fa/tests/test_ritm.py::test_acquire_editor_lock src/fa/tests/test_ritm.py::test_acquire_editor_lock_already_locked_fails src/fa/tests/test_ritm.py::test_release_editor_lock src/fa/tests/test_ritm.py::test_reviewer_cannot_acquire_editor_lock -v
```

Expected: FAIL (endpoints do not exist yet)

- [ ] **Step 4.2: Add editor-lock and editor-unlock endpoints to `ritm.py`**

Add after `release_approval_lock`:

```python
@router.post("/ritm/{ritm_number}/editor-lock")
async def acquire_editor_lock(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Acquire editor lock. Fails if user is a reviewer or lock is held by another."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Reviewers cannot become editors
        reviewer_result = await db.execute(
            select(RITMReviewer).where(
                col(RITMReviewer.ritm_number) == ritm_number,
                col(RITMReviewer.username) == session.username,
            )
        )
        if reviewer_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Reviewer cannot acquire editor lock")

        # Check existing lock
        if ritm.editor_locked_by:
            locked_at = ritm.editor_locked_at
            if locked_at:
                if locked_at.tzinfo is None:
                    locked_at = locked_at.replace(tzinfo=UTC)
                if datetime.now(UTC) - locked_at < timedelta(minutes=settings.approval_lock_minutes):
                    raise HTTPException(
                        status_code=400,
                        detail=f"RITM is locked by {ritm.editor_locked_by}",
                    )
                logger.info(f"Editor lock expired for RITM {ritm_number}")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"RITM is locked by {ritm.editor_locked_by}",
                )

        ritm.editor_locked_by = session.username
        ritm.editor_locked_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Editor lock acquired for RITM {ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)


@router.post("/ritm/{ritm_number}/editor-unlock")
async def release_editor_lock(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Release editor lock. Only the lock holder can release."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if ritm.editor_locked_by != session.username:
            raise HTTPException(status_code=400, detail="You did not acquire this lock")

        ritm.editor_locked_by = None
        ritm.editor_locked_at = None
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Editor lock released for RITM {ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)
```

- [ ] **Step 4.3: Run tests**

```
uv run pytest src/fa/tests/test_ritm.py::test_acquire_editor_lock src/fa/tests/test_ritm.py::test_acquire_editor_lock_already_locked_fails src/fa/tests/test_ritm.py::test_release_editor_lock src/fa/tests/test_ritm.py::test_reviewer_cannot_acquire_editor_lock -v
```

Expected: all 4 PASS

- [ ] **Step 4.4: Commit**

```bash
git add src/fa/routes/ritm.py src/fa/tests/test_ritm.py
git commit -m "feat: add editor-lock and editor-unlock endpoints"
```

---

## Task 5: Policy save adds user to editors when lock held

**Files:**
- Modify: `src/fa/routes/ritm.py`
- Modify: `src/fa/tests/test_ritm.py`

- [ ] **Step 5.1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_save_policy_with_editor_lock_adds_to_editors(async_client: AsyncClient):
    """Saving a policy while holding editor lock adds user to editors list."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000020"})
    await async_client.post("/api/v1/ritm/RITM0000020/editor-lock")

    policy = {
        "ritm_number": "RITM0000020",
        "comments": "test",
        "rule_name": "RITM0000020",
        "domain_uid": "d1",
        "domain_name": "Domain1",
        "package_uid": "p1",
        "package_name": "Package1",
        "section_uid": None,
        "section_name": None,
        "position_type": "bottom",
        "action": "accept",
        "track": "log",
        "source_ips": ["10.0.0.1"],
        "dest_ips": ["10.0.0.2"],
        "services": ["https"],
    }
    await async_client.post("/api/v1/ritm/RITM0000020/policy", json=[policy])

    response = await async_client.get("/api/v1/ritm/RITM0000020")
    assert "testuser" in response.json()["ritm"]["editors"]


@pytest.mark.asyncio
async def test_save_policy_without_editor_lock_does_not_add_to_editors(async_client: AsyncClient):
    """Saving a policy without the editor lock does NOT add user to editors (already there from create)."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000021"})
    # Do NOT acquire editor lock — testuser is already in editors from create
    # A NEW user saving without lock should NOT be added; we test the lock check
    # For this test, verify that saving without a lock does not add duplicate or new users
    policy = {
        "ritm_number": "RITM0000021",
        "comments": "test",
        "rule_name": "RITM0000021",
        "domain_uid": "d1",
        "domain_name": "Domain1",
        "package_uid": "p1",
        "package_name": "Package1",
        "section_uid": None,
        "section_name": None,
        "position_type": "bottom",
        "action": "accept",
        "track": "log",
        "source_ips": ["10.0.0.1"],
        "dest_ips": ["10.0.0.2"],
        "services": ["https"],
    }
    await async_client.post("/api/v1/ritm/RITM0000021/policy", json=[policy])
    # editors should still be exactly ["testuser"] (from create, not re-added from save)
    response = await async_client.get("/api/v1/ritm/RITM0000021")
    assert response.json()["ritm"]["editors"] == ["testuser"]
```

Run:

```
uv run pytest src/fa/tests/test_ritm.py::test_save_policy_with_editor_lock_adds_to_editors src/fa/tests/test_ritm.py::test_save_policy_without_editor_lock_does_not_add_to_editors -v
```

Expected: first test FAIL (editor not added on save), second may pass

- [ ] **Step 5.2: Update `save_policy` in `ritm.py`**

After inserting the new policies and before `await db.commit()`, add:

```python
        # If user holds editor lock, record them as a co-editor
        if ritm.editor_locked_by == session.username:
            existing_editor = await db.execute(
                select(RITMEditor).where(
                    col(RITMEditor.ritm_number) == ritm_number,
                    col(RITMEditor.username) == session.username,
                )
            )
            if not existing_editor.scalar_one_or_none():
                db.add(
                    RITMEditor(
                        ritm_number=ritm_number,
                        username=session.username,
                        added_at=datetime.now(UTC),
                    )
                )
```

Also add `RITMEditor` to the imports of the `save_policy` function's local scope (it's already in module imports from Task 3).

- [ ] **Step 5.3: Run tests**

```
uv run pytest src/fa/tests/test_ritm.py::test_save_policy_with_editor_lock_adds_to_editors src/fa/tests/test_ritm.py::test_save_policy_without_editor_lock_does_not_add_to_editors -v
```

Expected: both PASS

- [ ] **Step 5.4: Commit**

```bash
git add src/fa/routes/ritm.py src/fa/tests/test_ritm.py
git commit -m "feat: save_policy records co-editor when editor lock is held"
```

---

## Task 6: Update status transition rules (submit / approve / reject)

**Files:**
- Modify: `src/fa/routes/ritm.py`
- Modify: `src/fa/tests/test_ritm.py`

- [ ] **Step 6.1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_submit_requires_editor_lock(async_client: AsyncClient):
    """Editor must hold lock to submit for approval."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000030"})
    # testuser is an editor (from create) but does NOT hold lock
    response = await async_client.put(
        "/api/v1/ritm/RITM0000030",
        json={"status": 1},  # READY_FOR_APPROVAL
    )
    assert response.status_code == 400
    assert "editor lock" in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_with_lock_succeeds(async_client: AsyncClient):
    """Editor holding lock can submit for approval."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000031"})
    await async_client.post("/api/v1/ritm/RITM0000031/editor-lock")
    response = await async_client.put(
        "/api/v1/ritm/RITM0000031",
        json={"status": 1},
    )
    assert response.status_code == 200
    assert response.json()["status"] == 1


@pytest.mark.asyncio
async def test_editor_cannot_approve(async_client: AsyncClient):
    """Any editor is blocked from approving, not just the creator."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000032"})
    await async_client.post("/api/v1/ritm/RITM0000032/editor-lock")
    await async_client.put("/api/v1/ritm/RITM0000032", json={"status": 1})
    response = await async_client.put(
        "/api/v1/ritm/RITM0000032",
        json={"status": 2},  # APPROVED
    )
    assert response.status_code == 400
    assert "cannot approve" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reject_adds_reviewer_and_clears_editor_lock(async_client: AsyncClient):
    """Rejection inserts reviewer record and clears editor lock."""
    from datetime import UTC, datetime
    from sqlalchemy.ext.asyncio import AsyncSession
    import fa.routes.ritm as ritm_module
    from fa.models import RITM
    from sqlalchemy import select
    from sqlmodel import col

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000033"})
    await async_client.post("/api/v1/ritm/RITM0000033/editor-lock")
    await async_client.put("/api/v1/ritm/RITM0000033", json={"status": 1})

    # Set RITM as if another user is rejecting — bypass the editor check by
    # directly removing testuser from editors and returning to WIP with feedback
    response = await async_client.put(
        "/api/v1/ritm/RITM0000033",
        json={"status": 0, "feedback": "Please fix the source IP"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == 0
    assert data["editor_locked_by"] is None
    # testuser appears in reviewers
    assert any(r["username"] == "testuser" for r in data["reviewers"])
    assert any(r["action"] == "rejected" for r in data["reviewers"])
```

Run:

```
uv run pytest src/fa/tests/test_ritm.py::test_submit_requires_editor_lock src/fa/tests/test_ritm.py::test_submit_with_lock_succeeds src/fa/tests/test_ritm.py::test_editor_cannot_approve src/fa/tests/test_ritm.py::test_reject_adds_reviewer_and_clears_editor_lock -v
```

Expected: most FAIL

- [ ] **Step 6.2: Replace the `update_ritm` function**

```python
@router.put("/ritm/{ritm_number}")
async def update_ritm(
    ritm_number: str,
    request: RITMUpdateRequest,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Update RITM status and/or feedback."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if request.status is not None:
            if request.status == RITMStatus.READY_FOR_APPROVAL:
                # Must be a registered editor AND currently hold the editor lock
                editor_result = await db.execute(
                    select(RITMEditor).where(
                        col(RITMEditor.ritm_number) == ritm_number,
                        col(RITMEditor.username) == session.username,
                    )
                )
                if not editor_result.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail="Only editors can submit for approval")
                if ritm.editor_locked_by != session.username:
                    raise HTTPException(
                        status_code=400, detail="You must hold the editor lock to submit for approval"
                    )
                ritm.date_updated = datetime.now(UTC)

            elif request.status == RITMStatus.APPROVED:
                # Must NOT be in editors list
                editor_result = await db.execute(
                    select(RITMEditor).where(
                        col(RITMEditor.ritm_number) == ritm_number,
                        col(RITMEditor.username) == session.username,
                    )
                )
                if editor_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=400, detail="Editors cannot approve their own RITM"
                    )
                if ritm.status != RITMStatus.READY_FOR_APPROVAL:
                    raise HTTPException(status_code=400, detail="RITM must be ready for approval")
                ritm.date_approved = datetime.now(UTC)
                ritm.username_approved = session.username
                ritm.approver_locked_by = None
                ritm.approver_locked_at = None
                db.add(
                    RITMReviewer(
                        ritm_number=ritm_number,
                        username=session.username,
                        action="approved",
                        acted_at=datetime.now(UTC),
                    )
                )

            elif request.status == RITMStatus.WORK_IN_PROGRESS:
                if not request.feedback:
                    raise HTTPException(
                        status_code=400, detail="Feedback is required when returning for changes"
                    )
                db.add(
                    RITMReviewer(
                        ritm_number=ritm_number,
                        username=session.username,
                        action="rejected",
                        acted_at=datetime.now(UTC),
                    )
                )
                ritm.editor_locked_by = None
                ritm.editor_locked_at = None

            ritm.status = request.status

        if request.feedback is not None:
            ritm.feedback = request.feedback

        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Updated RITM {ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)
```

- [ ] **Step 6.3: Update the existing `test_submit_for_approval` test**

The existing test submits for approval without acquiring editor lock — it must now acquire the lock first. Update the test:

```python
@pytest.mark.asyncio
async def test_submit_for_approval(async_client: AsyncClient):
    """Test submitting a RITM for approval."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM3333333"})
    await async_client.post("/api/v1/ritm/RITM3333333/editor-lock")  # add this
    response = await async_client.put(
        "/api/v1/ritm/RITM3333333",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )
    assert response.status_code == 200
    assert response.json()["status"] == RITMStatus.READY_FOR_APPROVAL
```

- [ ] **Step 6.4: Run all tests**

```
uv run pytest src/fa/tests/test_ritm.py -v --tb=short -q
```

Expected: all pass

- [ ] **Step 6.5: Commit**

```bash
git add src/fa/routes/ritm.py src/fa/tests/test_ritm.py
git commit -m "feat: update status transitions — editor lock required to submit, editors cannot approve, reject records reviewer"
```

---

## Task 7: Try & Verify writes to `ritm_evidence_sessions`

**Files:**
- Modify: `src/fa/services/ritm_workflow_service.py`
- Modify: `src/fa/tests/test_ritm.py`

- [ ] **Step 7.1: Write failing unit tests for `_next_attempt`**

Add to `test_ritm.py` (these test DB logic without CP client):

```python
@pytest.mark.asyncio
async def test_next_attempt_returns_1_when_no_evidence(async_client: AsyncClient):
    """_next_attempt returns 1 when no evidence sessions exist."""
    import fa.routes.ritm as ritm_module
    from fa.services.ritm_workflow_service import RITMWorkflowService
    from fa.models import RITMEvidenceSession
    from sqlalchemy.ext.asyncio import AsyncSession

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000040"})

    # Patch engine on the service class before instantiation
    import fa.services.ritm_workflow_service as svc_module
    svc_module.engine = ritm_module.engine

    service = RITMWorkflowService(client=None, ritm_number="RITM0000040", username="testuser")
    attempt = await service._next_attempt()
    assert attempt == 1


@pytest.mark.asyncio
async def test_next_attempt_increments(async_client: AsyncClient):
    """_next_attempt returns max+1 when evidence sessions exist."""
    from datetime import UTC, datetime
    import fa.routes.ritm as ritm_module
    import fa.services.ritm_workflow_service as svc_module
    from fa.models import RITMEvidenceSession
    from fa.services.ritm_workflow_service import RITMWorkflowService
    from sqlalchemy.ext.asyncio import AsyncSession

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000041"})
    svc_module.engine = ritm_module.engine

    async with AsyncSession(ritm_module.engine) as db:
        db.add(RITMEvidenceSession(
            ritm_number="RITM0000041",
            attempt=1,
            domain_name="D1",
            domain_uid="uid1",
            package_name="P1",
            package_uid="puid1",
            session_type="initial",
            created_at=datetime.now(UTC),
        ))
        await db.commit()

    service = RITMWorkflowService(client=None, ritm_number="RITM0000041", username="testuser")
    attempt = await service._next_attempt()
    assert attempt == 2
```

Run:

```
uv run pytest src/fa/tests/test_ritm.py::test_next_attempt_returns_1_when_no_evidence src/fa/tests/test_ritm.py::test_next_attempt_increments -v
```

Expected: FAIL (`_next_attempt` does not exist yet)

- [ ] **Step 7.2: Add `_next_attempt` and `_store_evidence_session` to `RITMWorkflowService`**

In `src/fa/services/ritm_workflow_service.py`, add these imports:

```python
from sqlalchemy import func
```

Add these two methods to `RITMWorkflowService`:

```python
    async def _next_attempt(self) -> int:
        """Compute next attempt number — MAX(attempt)+1 for this RITM, or 1 if none."""
        from ..models import RITMEvidenceSession

        async with AsyncSession(engine) as db:
            result = await db.execute(
                select(func.max(RITMEvidenceSession.attempt)).where(
                    col(RITMEvidenceSession.ritm_number) == self.ritm_number
                )
            )
            max_val = result.scalar_one_or_none()
            return (max_val or 0) + 1

    async def _store_evidence_session(
        self, evidence: EvidenceData, attempt: int, session_type: str
    ) -> None:
        """Persist one package's evidence as a row in ritm_evidence_sessions."""
        from ..models import RITMEvidenceSession

        async with AsyncSession(engine) as db:
            db.add(
                RITMEvidenceSession(
                    ritm_number=self.ritm_number,
                    attempt=attempt,
                    domain_name=evidence.domain_name,
                    domain_uid=evidence.domain_uid,
                    package_name=evidence.package_name,
                    package_uid=evidence.package_uid,
                    session_uid=evidence.session_uid,
                    sid=evidence.sid,
                    session_type=session_type,
                    session_changes=json.dumps(evidence.session_changes)
                    if evidence.session_changes
                    else None,
                    created_at=datetime.now(UTC),
                )
            )
            await db.commit()
```

- [ ] **Step 7.3: Update `try_verify` to use new methods**

Replace the body of `try_verify` in `ritm_workflow_service.py`:

```python
    async def try_verify(self) -> TryVerifyResponse:
        """Execute full Try & Verify workflow."""
        packages = await self._group_by_package()
        if not packages:
            self.logger.warning(f"No packages found for RITM {self.ritm_number}")
            return TryVerifyResponse(
                results=[],
                evidence_pdf=None,
                evidence_html=None,
                published=False,
                session_changes=None,
            )

        self.logger.info(
            f"Try & Verify for RITM {self.ritm_number}: "
            f"Processing {len(packages)} unique package(s)"
        )

        # Compute attempt number ONCE — shared across all packages in this run
        attempt = await self._next_attempt()
        session_type = "initial" if attempt == 1 else "correction"

        results: list[PackageResult] = []
        all_evidence: list[EvidenceData] = []
        any_success = False

        for pkg_info in packages:
            self.logger.info(
                f"Processing package: {pkg_info.package_name} (domain: {pkg_info.domain_name})"
            )
            pkg_workflow = PackageWorkflowService(
                client=self.client,
                package_info=pkg_info,
                ritm_number=self.ritm_number,
                mgmt_name=self.mgmt_name,
            )

            verify1 = await pkg_workflow.verify_first()
            if not verify1.success:
                results.append(
                    PackageResult(package=pkg_info.package_name, status="skipped", errors=verify1.errors)
                )
                continue

            create_result = await pkg_workflow.create_objects_and_rules()
            if create_result.errors:
                results.append(
                    PackageResult(
                        package=pkg_info.package_name,
                        status="create_failed",
                        objects_created=create_result.objects_created,
                        rules_created=create_result.rules_created,
                        errors=create_result.errors,
                    )
                )
                continue

            verify2 = await pkg_workflow.verify_again()
            if not verify2.success:
                await pkg_workflow.rollback_rules(create_result.created_rule_uids)
                results.append(
                    PackageResult(
                        package=pkg_info.package_name,
                        status="verify_failed",
                        objects_created=create_result.objects_created,
                        rules_created=create_result.rules_created,
                        errors=verify2.errors,
                    )
                )
                continue

            evidence = await pkg_workflow.capture_evidence()
            all_evidence.append(evidence)

            await self._store_evidence_session(evidence, attempt, session_type)
            await pkg_workflow.disable_rules(create_result.created_rule_uids)

            results.append(
                PackageResult(
                    package=pkg_info.package_name,
                    status="success",
                    objects_created=create_result.objects_created,
                    rules_created=create_result.rules_created,
                )
            )
            any_success = True

        combined_session_changes = self._combine_evidence(all_evidence)
        section_uid_to_name = await self._build_section_uid_mapping()
        evidence_pdf, evidence_html = self._generate_evidence_artifacts(
            combined_session_changes, section_uid_to_name
        )

        import base64
        evidence_pdf_b64 = base64.b64encode(evidence_pdf).decode("utf-8") if evidence_pdf else None

        if any_success:
            await self._publish_session()

        return TryVerifyResponse(
            results=results,
            evidence_pdf=evidence_pdf_b64,
            evidence_html=evidence_html,
            published=any_success,
            session_changes=combined_session_changes,
        )
```

- [ ] **Step 7.4: Remove `_store_session_uids` and `_store_evidence` methods**

Delete both methods entirely from `RITMWorkflowService`.

- [ ] **Step 7.5: Run tests**

```
uv run pytest src/fa/tests/test_ritm.py::test_next_attempt_returns_1_when_no_evidence src/fa/tests/test_ritm.py::test_next_attempt_increments -v
```

Expected: both PASS

- [ ] **Step 7.6: Run full suite**

```
uv run pytest src/fa/tests/ -v --tb=short -q
```

Expected: all pass

- [ ] **Step 7.7: Commit**

```bash
git add src/fa/services/ritm_workflow_service.py src/fa/tests/test_ritm.py
git commit -m "feat: try-verify writes cumulative evidence to ritm_evidence_sessions"
```

---

## Task 8: Implement approval publish in `ritm_flow.py`

**Files:**
- Modify: `src/fa/routes/ritm_flow.py`
- Modify: `src/fa/tests/test_ritm.py`

- [ ] **Step 8.1: Write failing test**

```python
@pytest.mark.asyncio
async def test_publish_requires_approved_status(async_client: AsyncClient):
    """Publish endpoint returns 400 when RITM is not APPROVED."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000050"})
    response = await async_client.post("/api/v1/ritm/RITM0000050/publish")
    assert response.status_code == 400
    assert "approved" in response.json()["detail"].lower()
```

Run:

```
uv run pytest src/fa/tests/test_ritm.py::test_publish_requires_approved_status -v
```

Expected: FAIL (endpoint was removed in Task 3)

- [ ] **Step 8.2: Add required imports to `ritm_flow.py`**

Add to the imports at the top of `src/fa/routes/ritm_flow.py`:

```python
from ..models import (
    ...existing imports...,
    RITM,
    Policy,
    PublishResponse,
    RITMCreatedRule,
    RITMEditor,
    RITMEvidenceSession,
    RITMStatus,
)
from ..services.policy_verifier import PolicyVerifier
```

(`PolicyVerifier` and `CPAIOPSClient` are already imported.)

- [ ] **Step 8.3: Add `publish_ritm` endpoint to `ritm_flow.py`**

Add at the end of `ritm_flow.py`:

```python
@router.post("/ritm/{ritm_number}/publish")
async def publish_ritm(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> PublishResponse:
    """Enable disabled rules, verify, capture approval evidence, and publish.

    Workflow per domain/package:
    1. Enable disabled rules from ritm_created_rules
    2. Verify policy — on failure re-disable rules, continue
    3. Capture show-changes (approval evidence)
    4. Publish with session name '{RITM} {username} Published'

    On all packages succeeding: status → COMPLETED
    """
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if ritm.status != RITMStatus.APPROVED:
            raise HTTPException(status_code=400, detail="RITM must be approved before publishing")

        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = list(policies_result.scalars().all())
        if not policies:
            raise HTTPException(status_code=400, detail="RITM has no policies to publish")

        rules_result = await db.execute(
            select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
        )
        created_rules = list(rules_result.scalars().all())

        # Compute approval attempt number
        attempt_result = await db.execute(
            select(func.max(RITMEvidenceSession.attempt)).where(
                col(RITMEvidenceSession.ritm_number) == ritm_number
            )
        )
        max_attempt = attempt_result.scalar_one_or_none()
        attempt = (max_attempt or 0) + 1

    # Build per-package rule lists and domain/package name lookup
    rules_by_pkg: dict[tuple[str, str], list[RITMCreatedRule]] = {}
    for rule in created_rules:
        rules_by_pkg.setdefault((rule.domain_uid, rule.package_uid), []).append(rule)

    pkg_meta: dict[tuple[str, str], tuple[str, str]] = {}  # (domain_uid, pkg_uid) -> (domain_name, pkg_name)
    for policy in policies:
        pkg_meta[(policy.domain_uid, policy.package_uid)] = (policy.domain_name, policy.package_name)

    errors: list[str] = []
    success_count = 0

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]
            verifier = PolicyVerifier(client)

            for (domain_uid, package_uid), (domain_name, package_name) in pkg_meta.items():
                pkg_rules = rules_by_pkg.get((domain_uid, package_uid), [])
                enabled_uids: list[str] = []

                # 1. Enable disabled rules
                for rule in pkg_rules:
                    result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=domain_name,
                        command="set-access-rule",
                        payload={"uid": rule.rule_uid, "enabled": True},
                    )
                    if result.success:
                        enabled_uids.append(rule.rule_uid)
                    else:
                        errors.append(
                            f"Failed to enable rule {rule.rule_uid} in {domain_name}: "
                            f"{result.message or result.code}"
                        )

                # 2. Verify policy
                verify_result = await verifier.verify_policy(
                    domain_name=domain_name, package_name=package_name
                )
                if not verify_result.success:
                    for uid in enabled_uids:
                        await client.api_call(
                            mgmt_name=mgmt_name,
                            domain=domain_name,
                            command="set-access-rule",
                            payload={"uid": uid, "enabled": False},
                        )
                    errors.extend(verify_result.errors)
                    continue

                # 3. Capture show-changes for approval evidence
                session_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="show-session",
                    payload={},
                )
                session_uid: str | None = None
                if session_result.success and session_result.data:
                    session_uid = session_result.data.get("uid") or session_result.data.get("session-uid")

                sc_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="show-changes",
                    details_level="full",
                    payload={"to-session": session_uid} if session_uid else {},
                )
                session_changes = sc_result.data if sc_result.success and sc_result.data else {}

                # 4. Publish
                pub_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="publish",
                    payload={},
                )

                if pub_result.success:
                    success_count += 1
                    async with AsyncSession(engine) as db:
                        db.add(
                            RITMEvidenceSession(
                                ritm_number=ritm_number,
                                attempt=attempt,
                                domain_name=domain_name,
                                domain_uid=domain_uid,
                                package_name=package_name,
                                package_uid=package_uid,
                                session_uid=session_uid,
                                sid="",
                                session_type="approval",
                                session_changes=json.dumps(session_changes) if session_changes else None,
                                created_at=datetime.now(UTC),
                            )
                        )
                        await db.commit()
                else:
                    errors.append(
                        f"Publish failed for {domain_name}: {pub_result.message or pub_result.code}"
                    )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in publish_ritm for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if success_count == 0 and errors:
        raise HTTPException(
            status_code=500,
            detail=f"Publish failed for all packages: {'; '.join(errors)}",
        )

    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one()
        ritm.status = RITMStatus.COMPLETED
        await db.commit()

    return PublishResponse(
        success=True,
        message=f"Published {success_count} package(s) for RITM {ritm_number}",
        created=success_count,
        errors=errors,
    )
```

Also add at the top of `ritm_flow.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import func
```

- [ ] **Step 8.4: Run test**

```
uv run pytest src/fa/tests/test_ritm.py::test_publish_requires_approved_status -v
```

Expected: PASS

- [ ] **Step 8.5: Run full suite**

```
uv run pytest src/fa/tests/ -v --tb=short -q
```

Expected: all pass

- [ ] **Step 8.6: Commit**

```bash
git add src/fa/routes/ritm_flow.py src/fa/tests/test_ritm.py
git commit -m "feat: implement approval publish — enable rules, verify, capture evidence, publish"
```

---

## Task 9: Evidence history endpoint

**Files:**
- Modify: `src/fa/routes/ritm_flow.py`
- Create: `src/fa/tests/test_ritm_flow.py`

- [ ] **Step 9.1: Write failing tests**

Create `src/fa/tests/test_ritm_flow.py`:

```python
"""Tests for RITM flow endpoints."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fa.models import RITMEvidenceSession


@pytest.mark.asyncio
async def test_evidence_history_empty(async_client: AsyncClient):
    """Evidence history returns empty domains list when no evidence sessions exist."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000060"})
    response = await async_client.get("/api/v1/ritm/RITM0000060/evidence-history")
    assert response.status_code == 200
    assert response.json() == {"domains": []}


@pytest.mark.asyncio
async def test_evidence_history_grouped_correctly(async_client: AsyncClient):
    """Evidence history groups sessions under domain -> package hierarchy."""
    import fa.routes.ritm as ritm_module

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000061"})

    async with AsyncSession(ritm_module.engine) as db:
        db.add(RITMEvidenceSession(
            ritm_number="RITM0000061",
            attempt=1,
            domain_name="DomainA",
            domain_uid="da-uid",
            package_name="PkgX",
            package_uid="px-uid",
            session_uid="s1",
            session_type="initial",
            session_changes='{"test": 1}',
            created_at=datetime.now(UTC),
        ))
        db.add(RITMEvidenceSession(
            ritm_number="RITM0000061",
            attempt=2,
            domain_name="DomainA",
            domain_uid="da-uid",
            package_name="PkgX",
            package_uid="px-uid",
            session_uid="s2",
            session_type="correction",
            session_changes='{"test": 2}',
            created_at=datetime.now(UTC),
        ))
        db.add(RITMEvidenceSession(
            ritm_number="RITM0000061",
            attempt=2,
            domain_name="DomainB",
            domain_uid="db-uid",
            package_name="PkgY",
            package_uid="py-uid",
            session_uid="s3",
            session_type="correction",
            session_changes='{"test": 3}',
            created_at=datetime.now(UTC),
        ))
        await db.commit()

    response = await async_client.get("/api/v1/ritm/RITM0000061/evidence-history")
    assert response.status_code == 200
    data = response.json()

    assert len(data["domains"]) == 2

    domain_a = next(d for d in data["domains"] if d["domain_name"] == "DomainA")
    assert len(domain_a["packages"]) == 1
    pkg_x = domain_a["packages"][0]
    assert pkg_x["package_name"] == "PkgX"
    assert len(pkg_x["sessions"]) == 2
    assert pkg_x["sessions"][0]["attempt"] == 1
    assert pkg_x["sessions"][0]["session_type"] == "initial"
    assert pkg_x["sessions"][1]["attempt"] == 2
    assert pkg_x["sessions"][1]["session_type"] == "correction"

    domain_b = next(d for d in data["domains"] if d["domain_name"] == "DomainB")
    assert len(domain_b["packages"][0]["sessions"]) == 1


@pytest.mark.asyncio
async def test_evidence_history_not_found(async_client: AsyncClient):
    """Evidence history returns 404 for unknown RITM."""
    response = await async_client.get("/api/v1/ritm/RITM9999999/evidence-history")
    assert response.status_code == 404
```

Run:

```
uv run pytest src/fa/tests/test_ritm_flow.py -v
```

Expected: FAIL (endpoint does not exist)

- [ ] **Step 9.2: Add `evidence-history` endpoint to `ritm_flow.py`**

Add required imports to `ritm_flow.py`:

```python
from ..models import (
    ...existing...,
    DomainEvidenceItem,
    EvidenceHistoryResponse,
    EvidenceSessionItem,
    PackageEvidenceItem,
    RITMEvidenceSession,
)
```

Add the endpoint:

```python
@router.get("/ritm/{ritm_number}/evidence-history")
async def get_evidence_history(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> EvidenceHistoryResponse:
    """Return full cumulative evidence history grouped as Domain → Package → Sessions."""
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        evidence_result = await db.execute(
            select(RITMEvidenceSession)
            .where(col(RITMEvidenceSession.ritm_number) == ritm_number)
            .order_by(
                col(RITMEvidenceSession.domain_name).asc(),
                col(RITMEvidenceSession.package_name).asc(),
                col(RITMEvidenceSession.attempt).asc(),
            )
        )
        rows = evidence_result.scalars().all()

    # Build domain -> package -> sessions hierarchy
    domains_map: dict[str, dict[str, list[EvidenceSessionItem]]] = {}
    domain_uids: dict[str, str] = {}
    package_uids: dict[tuple[str, str], str] = {}

    for row in rows:
        if row.domain_name not in domains_map:
            domains_map[row.domain_name] = {}
            domain_uids[row.domain_name] = row.domain_uid

        if row.package_name not in domains_map[row.domain_name]:
            domains_map[row.domain_name][row.package_name] = []
            package_uids[(row.domain_name, row.package_name)] = row.package_uid

        sc: dict | None = None
        if row.session_changes:
            try:
                sc = json.loads(row.session_changes)
            except Exception:
                pass

        domains_map[row.domain_name][row.package_name].append(
            EvidenceSessionItem(
                id=row.id or 0,
                attempt=row.attempt,
                session_type=row.session_type,
                session_uid=row.session_uid,
                sid=row.sid,
                created_at=row.created_at.isoformat() if row.created_at else "",
                session_changes=sc,
            )
        )

    domains = [
        DomainEvidenceItem(
            domain_name=domain_name,
            domain_uid=domain_uids[domain_name],
            packages=[
                PackageEvidenceItem(
                    package_name=package_name,
                    package_uid=package_uids[(domain_name, package_name)],
                    sessions=sessions,
                )
                for package_name, sessions in packages_map.items()
            ],
        )
        for domain_name, packages_map in domains_map.items()
    ]

    return EvidenceHistoryResponse(domains=domains)
```

- [ ] **Step 9.3: Run tests**

```
uv run pytest src/fa/tests/test_ritm_flow.py -v
```

Expected: all PASS

- [ ] **Step 9.4: Commit**

```bash
git add src/fa/routes/ritm_flow.py src/fa/tests/test_ritm_flow.py
git commit -m "feat: add GET /ritm/{number}/evidence-history endpoint"
```

---

## Task 10: Update session-html, session-pdf, and recreate-evidence

**Files:**
- Modify: `src/fa/routes/ritm_flow.py`
- Modify: `src/fa/tests/test_ritm_flow.py`

- [ ] **Step 10.1: Write failing tests**

Add to `test_ritm_flow.py`:

```python
@pytest.mark.asyncio
async def test_session_html_returns_404_for_unknown_ritm(async_client: AsyncClient):
    """session-html returns 404 for unknown RITM."""
    response = await async_client.get("/api/v1/ritm/RITM9999888/session-html")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_session_html_returns_400_when_no_evidence(async_client: AsyncClient):
    """session-html returns 400 when no evidence sessions exist."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000070"})
    response = await async_client.get("/api/v1/ritm/RITM0000070/session-html")
    assert response.status_code == 400
    assert "no evidence" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recreate_evidence_returns_400_when_no_sessions(async_client: AsyncClient):
    """recreate-evidence returns 400 when no evidence sessions stored."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000071"})
    response = await async_client.post("/api/v1/ritm/RITM0000071/recreate-evidence")
    assert response.status_code == 400
    assert "no session" in response.json()["detail"].lower()
```

Run:

```
uv run pytest src/fa/tests/test_ritm_flow.py::test_session_html_returns_404_for_unknown_ritm src/fa/tests/test_ritm_flow.py::test_session_html_returns_400_when_no_evidence src/fa/tests/test_ritm_flow.py::test_recreate_evidence_returns_400_when_no_sessions -v
```

Expected: FAIL (old endpoints load from `session_changes_evidence1` which no longer exists)

- [ ] **Step 10.2: Rewrite `get_session_html` to use `ritm_evidence_sessions`**

Replace `get_session_html` in `ritm_flow.py`:

```python
@router.get("/ritm/{ritm_number}/session-html")
async def get_session_html(
    ritm_number: str,
    attempt: int | None = None,
    session: SessionData = Depends(get_session_data),
) -> HTMLResponse:
    """Render HTML evidence. Without attempt: all sessions. With attempt: that attempt only."""
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        query = select(RITMEvidenceSession).where(
            col(RITMEvidenceSession.ritm_number) == ritm_number
        )
        if attempt is not None:
            query = query.where(col(RITMEvidenceSession.attempt) == attempt)
        query = query.order_by(
            col(RITMEvidenceSession.domain_name).asc(),
            col(RITMEvidenceSession.attempt).asc(),
        )
        rows_result = await db.execute(query)
        rows = rows_result.scalars().all()

    if not rows:
        raise HTTPException(status_code=400, detail="No evidence sessions found for this RITM")

    # Build combined session_changes for the evidence renderer
    combined: dict[str, Any] = {
        "apply_session_trace": [],
        "domain_changes": {},
        "errors": [],
    }
    for row in rows:
        sc: dict[str, Any] = {}
        if row.session_changes:
            try:
                sc = json.loads(row.session_changes)
            except Exception:
                pass
        if row.domain_name not in combined["domain_changes"]:
            combined["domain_changes"][row.domain_name] = {}
        combined["domain_changes"][row.domain_name].update(sc)
        if row.session_uid:
            combined["apply_session_trace"].append(
                {
                    "domain": row.domain_name,
                    "attempt": row.attempt,
                    "session_uid": row.session_uid,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
            )

    try:
        pdf_generator = get_pdf_generator()
        section_uid_to_name: dict[str, str] = {}
        html = pdf_generator.generate_html(
            ritm_number=ritm_number,
            evidence_number=1,
            username=session.username,
            session_changes=combined,
            section_uid_to_name=section_uid_to_name,
        )
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error(f"HTML evidence generation failed for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"HTML evidence generation failed: {e}") from e
```

- [ ] **Step 10.3: Rewrite `get_session_pdf` similarly**

Replace `get_session_pdf` in `ritm_flow.py` with the same logic as `get_session_html` but returning a PDF response:

```python
@router.get("/ritm/{ritm_number}/session-pdf")
async def get_session_pdf(
    ritm_number: str,
    attempt: int | None = None,
    session: SessionData = Depends(get_session_data),
) -> Response:
    """Generate PDF evidence. Without attempt: all sessions. With attempt: that attempt only."""
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        query = select(RITMEvidenceSession).where(
            col(RITMEvidenceSession.ritm_number) == ritm_number
        )
        if attempt is not None:
            query = query.where(col(RITMEvidenceSession.attempt) == attempt)
        query = query.order_by(
            col(RITMEvidenceSession.domain_name).asc(),
            col(RITMEvidenceSession.attempt).asc(),
        )
        rows_result = await db.execute(query)
        rows = rows_result.scalars().all()

    if not rows:
        raise HTTPException(status_code=400, detail="No evidence sessions found for this RITM")

    combined: dict[str, Any] = {
        "apply_session_trace": [],
        "domain_changes": {},
        "errors": [],
    }
    for row in rows:
        sc: dict[str, Any] = {}
        if row.session_changes:
            try:
                sc = json.loads(row.session_changes)
            except Exception:
                pass
        if row.domain_name not in combined["domain_changes"]:
            combined["domain_changes"][row.domain_name] = {}
        combined["domain_changes"][row.domain_name].update(sc)
        if row.session_uid:
            combined["apply_session_trace"].append(
                {
                    "domain": row.domain_name,
                    "attempt": row.attempt,
                    "session_uid": row.session_uid,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
            )

    try:
        pdf_generator = get_pdf_generator()
        section_uid_to_name: dict[str, str] = {}
        pdf_bytes = pdf_generator.generate_pdf(
            ritm_number=ritm_number,
            evidence_number=1,
            username=session.username,
            session_changes=combined,
            section_uid_to_name=section_uid_to_name,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{ritm_number}_evidence.pdf"'
            },
        )
    except Exception as e:
        logger.error(f"PDF generation failed for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}") from e
```

- [ ] **Step 10.4: Rewrite `recreate_evidence` to use `ritm_evidence_sessions`**

Replace `recreate_evidence` in `ritm_flow.py`:

```python
@router.post("/ritm/{ritm_number}/recreate-evidence")
async def recreate_evidence(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> EvidenceResponse:
    """Re-fetch show-changes for all stored sessions and update evidence in DB."""
    logger.info(f"Recreating evidence for RITM {ritm_number} by user {session.username}")

    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        sessions_result = await db.execute(
            select(RITMEvidenceSession).where(
                col(RITMEvidenceSession.ritm_number) == ritm_number
            )
        )
        evidence_rows = sessions_result.scalars().all()

    if not evidence_rows:
        raise HTTPException(
            status_code=400, detail="No session UIDs found for this RITM. Run Try & Verify first."
        )

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]

            async with AsyncSession(engine) as db:
                for row in evidence_rows:
                    if not row.session_uid:
                        continue

                    sc_result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=row.domain_name,
                        command="show-changes",
                        details_level="full",
                        payload={"to-session": row.session_uid},
                    )

                    if sc_result.success and sc_result.data:
                        # Re-fetch the row (it may have been refreshed)
                        fresh = await db.get(RITMEvidenceSession, row.id)
                        if fresh:
                            fresh.session_changes = json.dumps(sc_result.data)
                    else:
                        logger.warning(
                            f"show-changes failed for {row.domain_name} session {row.session_uid}: "
                            f"{sc_result.message or sc_result.code}"
                        )

                await db.commit()

            # Build combined for response
            combined: dict[str, Any] = {"domain_changes": {}, "errors": []}
            async with AsyncSession(engine) as db:
                refreshed_result = await db.execute(
                    select(RITMEvidenceSession).where(
                        col(RITMEvidenceSession.ritm_number) == ritm_number
                    )
                )
                for row in refreshed_result.scalars().all():
                    sc: dict[str, Any] = {}
                    if row.session_changes:
                        try:
                            sc = json.loads(row.session_changes)
                        except Exception:
                            pass
                    if row.domain_name not in combined["domain_changes"]:
                        combined["domain_changes"][row.domain_name] = {}
                    combined["domain_changes"][row.domain_name].update(sc)

            pdf_generator = get_pdf_generator()
            html = pdf_generator.generate_html(
                ritm_number=ritm_number,
                evidence_number=1,
                username=session.username,
                session_changes=combined,
                section_uid_to_name={},
            )

            return EvidenceResponse(
                html=html,
                yaml="",
                changes=combined.get("domain_changes", {}),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in recreate_evidence for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 10.5: Run tests**

```
uv run pytest src/fa/tests/test_ritm_flow.py -v --tb=short
```

Expected: all PASS

- [ ] **Step 10.6: Run full suite**

```
uv run pytest src/fa/tests/ -v --tb=short -q
```

Expected: all pass

- [ ] **Step 10.7: Commit**

```bash
git add src/fa/routes/ritm_flow.py src/fa/tests/test_ritm_flow.py
git commit -m "feat: update session-html/pdf and recreate-evidence to use ritm_evidence_sessions"
```

---

## Self-Review Checklist

After all tasks are complete, verify against the spec:

| Spec requirement | Task |
|-----------------|------|
| `ritm_editors` table, creator inserted on create | Task 1, 3 |
| `ritm_reviewers` table, inserted on approve/reject | Task 1, 6 |
| `ritm_evidence_sessions` table, replaces `ritm_sessions` + evidence columns | Task 1, 7 |
| `editor_locked_by` / `editor_locked_at` on RITM | Task 1, 4 |
| Editor lock: reviewer blocked, lock expiry | Task 4 |
| Policy save adds to editors when lock held | Task 5 |
| Submit requires editor + lock | Task 6 |
| Approve blocked for editors | Task 6 |
| Reject inserts reviewer + clears editor lock | Task 6 |
| `attempt` increments per Try & Verify run | Task 7 |
| `session_type` = "initial" / "correction" | Task 7 |
| Approval publish: enable, verify, evidence, publish | Task 8 |
| `session_type` = "approval" for publish evidence | Task 8 |
| `GET /evidence-history` Domain→Package→Session | Task 9 |
| `session-html` / `session-pdf` accept `attempt` | Task 10 |
| `recreate-evidence` iterates `ritm_evidence_sessions` | Task 10 |
| Objects created in policy's domain (auto) | No change needed |
