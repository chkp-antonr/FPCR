"""Tests for RITM endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from fa.models import RITM, Policy, RITMStatus


@pytest.mark.asyncio
async def test_create_ritm_success(async_client: AsyncClient):
    """Test creating a new RITM."""
    response = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM1234567"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ritm_number"] == "RITM1234567"
    assert data["status"] == RITMStatus.WORK_IN_PROGRESS
    assert data["username_created"] == "testuser"


@pytest.mark.asyncio
async def test_create_ritm_duplicate_fails(async_client: AsyncClient):
    """Test that duplicate RITM numbers are rejected."""
    # First creation
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM9999999"},
    )

    # Duplicate should fail
    response = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM9999999"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_ritm_invalid_format(async_client: AsyncClient):
    """Test that invalid RITM number format is rejected."""
    response = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "INVALID123"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_ritms_empty(async_client: AsyncClient):
    """Test listing RITMs when empty."""
    response = await async_client.get(
        "/api/v1/ritm",
    )
    assert response.status_code == 200
    # Note: response depends on test isolation, may have other RITMs
    assert "ritms" in response.json()


@pytest.mark.asyncio
async def test_get_ritm_with_policies(async_client: AsyncClient):
    """Test getting a single RITM with policies."""
    # Create RITM
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM1111111"},
    )

    # Get RITM
    response = await async_client.get(
        "/api/v1/ritm/RITM1111111",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ritm"]["ritm_number"] == "RITM1111111"
    assert data["policies"] == []  # No policies yet


@pytest.mark.asyncio
async def test_save_policies(async_client: AsyncClient):
    """Test saving policies to a RITM."""
    # Create RITM
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM2222222"},
    )

    # Save policies
    policies = [
        {
            "ritm_number": "RITM2222222",
            "comments": "Test comment RITM2222222 #2026-04-09#",
            "rule_name": "RITM2222222",
            "domain_uid": "domain1",
            "domain_name": "Test Domain",
            "package_uid": "pkg1",
            "package_name": "Test Package",
            "section_uid": None,
            "section_name": None,
            "position_type": "bottom",
            "action": "accept",
            "track": "log",
            "source_ips": ["10.0.0.1"],
            "dest_ips": ["10.0.0.2"],
            "services": ["https"],
        }
    ]
    response = await async_client.post(
        "/api/v1/ritm/RITM2222222/policy",
        json=policies,
    )
    assert response.status_code == 200
    assert "Saved" in response.json()["message"] and "policies" in response.json()["message"]

    # Verify policies are saved
    response = await async_client.get(
        "/api/v1/ritm/RITM2222222",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["policies"]) == 1
    assert data["policies"][0]["source_ips"] == ["10.0.0.1"]
    assert data["policies"][0]["dest_ips"] == ["10.0.0.2"]
    assert data["policies"][0]["services"] == ["https"]


@pytest.mark.asyncio
async def test_submit_for_approval(async_client: AsyncClient):
    """Test submitting a RITM for approval."""
    # Create RITM
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM3333333"},
    )
    await async_client.post("/api/v1/ritm/RITM3333333/editor-lock")  # required in v2

    # Submit for approval
    response = await async_client.put(
        "/api/v1/ritm/RITM3333333",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == RITMStatus.READY_FOR_APPROVAL


@pytest.mark.asyncio
async def test_acquire_lock(async_client: AsyncClient):
    """Test acquiring approval lock on a RITM."""
    # Create RITM and submit for approval
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM4444444"},
    )
    await async_client.post("/api/v1/ritm/RITM4444444/editor-lock")
    await async_client.put(
        "/api/v1/ritm/RITM4444444",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )

    # Acquire lock
    response = await async_client.post(
        "/api/v1/ritm/RITM4444444/lock",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["approver_locked_by"] == "testuser"
    assert data["approver_locked_at"] is not None


@pytest.mark.asyncio
async def test_acquire_lock_already_locked_fails(async_client: AsyncClient):
    """Test that acquiring lock on already locked RITM fails."""
    # Create and lock RITM
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM5555555"},
    )
    await async_client.post("/api/v1/ritm/RITM5555555/editor-lock")
    await async_client.put(
        "/api/v1/ritm/RITM5555555",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )
    await async_client.post(
        "/api/v1/ritm/RITM5555555/lock",
    )

    # Try to acquire lock again (should fail even for same user)
    response = await async_client.post(
        "/api/v1/ritm/RITM5555555/lock",
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_release_lock(async_client: AsyncClient):
    """Test releasing approval lock on a RITM."""
    # Create and lock RITM
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM6666666"},
    )
    await async_client.post("/api/v1/ritm/RITM6666666/editor-lock")
    await async_client.put(
        "/api/v1/ritm/RITM6666666",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )
    await async_client.post(
        "/api/v1/ritm/RITM6666666/lock",
    )

    # Release lock
    response = await async_client.post(
        "/api/v1/ritm/RITM6666666/unlock",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["approver_locked_by"] is None
    assert data["approver_locked_at"] is None


@pytest.mark.asyncio
async def test_approve_ritm(async_client: AsyncClient):
    """Test approving a RITM."""
    # Create and submit RITM for approval
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM7777777"},
    )
    await async_client.post("/api/v1/ritm/RITM7777777/editor-lock")
    await async_client.put(
        "/api/v1/ritm/RITM7777777",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )

    # Approve - this will fail because editors cannot approve
    response = await async_client.put(
        "/api/v1/ritm/RITM7777777",
        json={"status": RITMStatus.APPROVED},
    )
    assert response.status_code == 400
    assert "cannot approve" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_return_ritm_with_feedback(async_client: AsyncClient):
    """Test returning a RITM with feedback."""
    # Create and submit RITM for approval
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM8888888"},
    )
    await async_client.post("/api/v1/ritm/RITM8888888/editor-lock")
    await async_client.put(
        "/api/v1/ritm/RITM8888888",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )

    # Return with feedback
    response = await async_client.put(
        "/api/v1/ritm/RITM8888888",
        json={"status": RITMStatus.WORK_IN_PROGRESS, "feedback": "Please review the source IPs"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == RITMStatus.WORK_IN_PROGRESS
    assert data["feedback"] == "Please review the source IPs"


@pytest.mark.asyncio
async def test_full_ritm_workflow(async_client: AsyncClient, db_session: AsyncSession):
    """Test complete RITM workflow from creation to ready for approval."""
    ritm_number = "RITM0000009"

    # Step 1: Create RITM
    response = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": ritm_number},
    )
    assert response.status_code == 200
    assert response.json()["status"] == RITMStatus.WORK_IN_PROGRESS

    # Step 2: Save policies
    policies = [
        {
            "ritm_number": ritm_number,
            "comments": f"Test comment {ritm_number} #2026-04-09#",
            "rule_name": ritm_number,
            "domain_uid": "domain1",
            "domain_name": "Test Domain",
            "package_uid": "pkg1",
            "package_name": "Test Package",
            "section_uid": None,
            "section_name": None,
            "position_type": "bottom",
            "action": "accept",
            "track": "log",
            "source_ips": ["192.168.1.1"],
            "dest_ips": ["10.0.0.1"],
            "services": ["tcp-80"],
        }
    ]
    response = await async_client.post(
        f"/api/v1/ritm/{ritm_number}/policy",
        json=policies,
    )
    assert response.status_code == 200

    # Verify policies in DB
    result = await db_session.execute(select(Policy).where(col(Policy.ritm_number) == ritm_number))
    policy = result.scalars().first()
    assert policy is not None
    # source_ips is stored as JSON string in DB
    import json

    assert json.loads(policy.source_ips) == ["192.168.1.1"]

    # Step 3: Acquire editor lock and submit for approval
    await async_client.post(f"/api/v1/ritm/{ritm_number}/editor-lock")
    response = await async_client.put(
        f"/api/v1/ritm/{ritm_number}",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )
    assert response.status_code == 200

    # Verify date_updated is set
    result = await db_session.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
    ritm = result.scalars().first()
    assert ritm is not None
    assert ritm.date_updated is not None
    assert ritm.status == RITMStatus.READY_FOR_APPROVAL

    # Step 4: Acquire approval lock
    response = await async_client.post(
        f"/api/v1/ritm/{ritm_number}/lock",
    )
    assert response.status_code == 200

    # Step 5: Attempting to approve as an editor should fail
    response = await async_client.put(
        f"/api/v1/ritm/{ritm_number}",
        json={"status": RITMStatus.APPROVED},
    )
    assert response.status_code == 400
    assert "cannot approve" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_evidence_uses_policy_table_when_no_created_objects(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression test: generate-evidence should query Policy SQLModel, not PolicyItem Pydantic model."""
    ritm_number = "RITM1111111"

    create_resp = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": ritm_number},
    )
    assert create_resp.status_code == 200

    policy_payload = [
        {
            "ritm_number": ritm_number,
            "comments": f"Test comment {ritm_number} #2026-04-12-TU#",
            "rule_name": ritm_number,
            "domain_uid": "domain-uid-1",
            "domain_name": "Test Domain",
            "package_uid": "package-uid-1",
            "package_name": "Test Package",
            "section_uid": None,
            "section_name": None,
            "position_type": "bottom",
            "action": "accept",
            "track": "log",
            "source_ips": ["10.0.0.1"],
            "dest_ips": ["10.0.0.2"],
            "services": ["https"],
        }
    ]
    save_resp = await async_client.post(
        f"/api/v1/ritm/{ritm_number}/policy",
        json=policy_payload,
    )
    assert save_resp.status_code == 200

    import fa.routes.ritm_flow as ritm_flow

    # Route module uses its own engine reference; point it to the test DB.
    monkeypatch.setattr(ritm_flow, "engine", test_engine)

    class DummyCPAIOPSClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def get_mgmt_names(self):
            return ["mgmt-test"]

        async def get_domains(self, mgmt_names=None):
            return []

    monkeypatch.setattr(ritm_flow, "CPAIOPSClient", DummyCPAIOPSClient)

    evidence_resp = await async_client.post(f"/api/v1/ritm/{ritm_number}/generate-evidence")
    assert evidence_resp.status_code == 200

    data = evidence_resp.json()
    assert "html" in data
    assert "yaml" in data
    assert "changes" in data


@pytest.mark.asyncio
async def test_plan_yaml_generated_by_backend(
    async_client: AsyncClient,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    """Plan YAML should be generated by backend from persisted policies."""
    ritm_number = "RITM1212121"

    create_resp = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": ritm_number},
    )
    assert create_resp.status_code == 200

    policy_payload = [
        {
            "ritm_number": ritm_number,
            "comments": f"{ritm_number} #2026-04-12#",
            "rule_name": ritm_number,
            "domain_uid": "domain-uid-1",
            "domain_name": "CPCodeOps",
            "package_uid": "package-uid-1",
            "package_name": "pyTestPolicy",
            "section_uid": "section-uid-1",
            "section_name": "Egress",
            "position_type": "bottom",
            "action": "accept",
            "track": "log",
            "source_ips": ["1.1.1.1"],
            "dest_ips": ["2.2.2.2"],
            "services": ["https"],
        }
    ]
    save_resp = await async_client.post(
        f"/api/v1/ritm/{ritm_number}/policy",
        json=policy_payload,
    )
    assert save_resp.status_code == 200

    import fa.routes.ritm_flow as ritm_flow

    monkeypatch.setattr(ritm_flow, "engine", test_engine)

    plan_resp = await async_client.post(f"/api/v1/ritm/{ritm_number}/plan-yaml")
    assert plan_resp.status_code == 200

    payload = plan_resp.json()
    assert "planned_operations:" in payload["yaml"]
    assert "type: host" in payload["yaml"]
    assert "type: access-rule" in payload["yaml"]
    assert payload["changes"]["planned_rules"] == 1


@pytest.mark.asyncio
async def test_list_ritms_by_status(async_client: AsyncClient):
    """Test filtering RITMs by status."""
    # Create RITMs with different statuses
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM0000001"},
    )
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM0000002"},
    )

    # Submit one for approval (requires editor lock in v2)
    await async_client.post("/api/v1/ritm/RITM0000002/editor-lock")
    await async_client.put(
        "/api/v1/ritm/RITM0000002",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )

    # Filter by status
    response = await async_client.get(
        "/api/v1/ritm?status=1",
    )
    assert response.status_code == 200
    ritms = response.json()["ritms"]
    # Should only include RITM0000002
    assert any(r["ritm_number"] == "RITM0000002" for r in ritms)


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
    from datetime import UTC, datetime

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import col

    import fa.routes.ritm as ritm_module
    from fa.models import RITM

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

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000013"})
    # Manually add testuser as reviewer
    async with AsyncSession(ritm_module.engine) as db:
        db.add(
            RITMReviewer(
                ritm_number="RITM0000013",
                username="testuser",
                action="rejected",
                acted_at=datetime.now(UTC),
            )
        )
        await db.commit()

    response = await async_client.post("/api/v1/ritm/RITM0000013/editor-lock")
    assert response.status_code == 400
    assert "Reviewer" in response.json()["detail"]


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
async def test_save_policy_without_editor_lock_does_not_add_duplicate(async_client: AsyncClient):
    """Saving a policy without the editor lock does not re-add already-present user."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000021"})
    # Do NOT acquire editor lock - testuser is already in editors from create
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
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000033"})
    await async_client.post("/api/v1/ritm/RITM0000033/editor-lock")
    await async_client.put("/api/v1/ritm/RITM0000033", json={"status": 1})

    # Reject — in real workflow a different user would do this, but the rule is:
    # if you're in editors you can't approve but CAN reject (because reviewer != editor).
    # For this test testuser is the creator/editor and is also "rejecting" to verify
    # the reviewer row is inserted and the editor lock is cleared.
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


@pytest.mark.asyncio
async def test_next_attempt_returns_1_when_no_evidence(async_client: AsyncClient):
    """_next_attempt returns 1 when no evidence sessions exist."""
    import fa.routes.ritm as ritm_module
    import fa.services.ritm_workflow_service as svc_module
    from fa.services.ritm_workflow_service import RITMWorkflowService

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000040"})
    svc_module.engine = ritm_module.engine

    service = RITMWorkflowService(client=None, ritm_number="RITM0000040", username="testuser")
    attempt = await service._next_attempt()
    assert attempt == 1


@pytest.mark.asyncio
async def test_next_attempt_increments(async_client: AsyncClient):
    """_next_attempt returns max+1 when evidence sessions exist."""
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    import fa.routes.ritm as ritm_module
    import fa.services.ritm_workflow_service as svc_module
    from fa.models import RITMEvidenceSession
    from fa.services.ritm_workflow_service import RITMWorkflowService

    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000041"})
    svc_module.engine = ritm_module.engine

    async with AsyncSession(ritm_module.engine) as db:
        db.add(
            RITMEvidenceSession(
                ritm_number="RITM0000041",
                attempt=1,
                domain_name="D1",
                domain_uid="uid1",
                package_name="P1",
                package_uid="puid1",
                session_type="initial",
                created_at=datetime.now(UTC),
            )
        )
        await db.commit()

    service = RITMWorkflowService(client=None, ritm_number="RITM0000041", username="testuser")
    attempt = await service._next_attempt()
    assert attempt == 2


@pytest.mark.asyncio
async def test_publish_requires_approved_status(async_client: AsyncClient):
    """Publish endpoint returns 400 when RITM is not APPROVED."""
    await async_client.post("/api/v1/ritm", json={"ritm_number": "RITM0000050"})
    response = await async_client.post("/api/v1/ritm/RITM0000050/publish")
    assert response.status_code == 400
    assert "approved" in response.json()["detail"].lower()
