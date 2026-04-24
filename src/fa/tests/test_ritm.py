"""Tests for RITM endpoints."""

from types import SimpleNamespace

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
    await async_client.put(
        "/api/v1/ritm/RITM7777777",
        json={"status": RITMStatus.READY_FOR_APPROVAL},
    )

    # Approve - this will fail because same user can't approve own RITM
    response = await async_client.put(
        "/api/v1/ritm/RITM7777777",
        json={"status": RITMStatus.APPROVED},
    )
    assert response.status_code == 400
    assert "cannot approve your own RITM" in response.json()["detail"]


@pytest.mark.asyncio
async def test_return_ritm_with_feedback(async_client: AsyncClient):
    """Test returning a RITM with feedback."""
    # Create and submit RITM for approval
    await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": "RITM8888888"},
    )
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

    # Step 3: Submit for approval
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

    # Step 4: Acquire lock
    response = await async_client.post(
        f"/api/v1/ritm/{ritm_number}/lock",
    )
    assert response.status_code == 200

    # Step 5: Attempting to approve own RITM should fail
    response = await async_client.put(
        f"/api/v1/ritm/{ritm_number}",
        json={"status": RITMStatus.APPROVED},
    )
    assert response.status_code == 400
    assert "cannot approve your own RITM" in response.json()["detail"]


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
async def test_session_html_returns_rendered_html_from_stored_evidence(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    """session-html should render HTML from stored session_changes evidence."""
    import json

    ritm_number = "RITM2026222"

    create_resp = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": ritm_number},
    )
    assert create_resp.status_code == 200

    ritm_result = await db_session.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
    ritm = ritm_result.scalar_one()

    ritm.session_changes_evidence1 = json.dumps(
        {
            "domain_changes": {
                "General": {
                    "tasks": [
                        {
                            "task-details": [
                                {
                                    "changes": [
                                        {
                                            "operations": {
                                                "added-objects": [
                                                    {
                                                        "type": "access-rule",
                                                        "rule-number": 1,
                                                        "name": "Allow HTTPS",
                                                        "source": [{"name": "1.1.1.1"}],
                                                        "destination": [{"name": "2.2.2.2"}],
                                                        "service": [{"name": "https"}],
                                                        "action": {"name": "Accept"},
                                                        "track": {"type": {"name": "Log"}},
                                                        "layer": {"name": "Egress"},
                                                        "package": "Standard",
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            }
        }
    )
    await db_session.commit()

    import fa.routes.ritm_flow as ritm_flow

    monkeypatch.setattr(ritm_flow, "engine", test_engine)

    response = await async_client.get(f"/api/v1/ritm/{ritm_number}/session-html?evidence=1")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert f"Apply Results: RITM {ritm_number} - Evidence #1" in response.text
    assert "Section: Egress" in response.text


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
async def test_apply_returns_domain_sessions_and_uses_package_name_fallback(
    async_client: AsyncClient,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    """Apply should prefetch layers and choose the current package domain layer over Global."""
    ritm_number = "RITM7654321"

    create_resp = await async_client.post(
        "/api/v1/ritm",
        json={"ritm_number": ritm_number},
    )
    assert create_resp.status_code == 200

    policy_payload = [
        {
            "ritm_number": ritm_number,
            "comments": f"{ritm_number} #2026-04-21#",
            "rule_name": ritm_number,
            "domain_uid": "domain-general-uid",
            "domain_name": "General",
            "package_uid": "missing-package-uid",
            "package_name": "Standard",
            "section_uid": "section-egress-uid",
            "section_name": "Egress",
            "position_type": "bottom",
            "action": "accept",
            "track": "log",
            "source_ips": ["1.1.1.1", "2.2.2.2"],
            "dest_ips": ["5.5.5.5", "10.192.10.0/24"],
            "services": ["https"],
        }
    ]
    save_resp = await async_client.post(
        f"/api/v1/ritm/{ritm_number}/policy",
        json=policy_payload,
    )
    assert save_resp.status_code == 200

    import cpcrud.rule_manager as rule_manager_module
    import fa.routes.ritm_flow as ritm_flow

    monkeypatch.setattr(ritm_flow, "engine", test_engine)

    captured_layers: list[str] = []

    class DummyMatcher:
        def __init__(self, client):
            self.client = client

        async def match_and_create_objects(
            self,
            inputs,
            domain_uid,
            domain_name,
            create_missing,
        ):
            return [
                {
                    "input": value,
                    "created": True,
                    "object_uid": f"uid-{value}",
                    "object_type": "host",
                    "object_name": value,
                }
                for value in inputs
            ]

    class DummyRuleManager:
        def __init__(self, client):
            self.client = client

        async def add(self, mgmt_name, domain, rule_type, data):
            captured_layers.append(data["layer"])
            return {"success": [{"uid": "rule-uid-1", "rule-number": 101}]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.cache = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def get_mgmt_names(self):
            return ["mgmt-test"]

        async def get_sid(self, mgmt_name, domain):
            if domain == "General":
                return SimpleNamespace(sid="sid-general-apply")
            return None

        async def get_uid_by_sid(self, sid):
            if sid == "sid-general-apply":
                return "uid-general-apply"
            return None

        async def api_call(self, mgmt_name, command, domain="", **kwargs):
            if command == "show-package":
                return SimpleNamespace(
                    success=True,
                    data={
                        "access-layer": "global-network-layer",
                        "access-layers": [
                            {
                                "uid": "global-network-layer",
                                "name": "Network",
                                "domain": {"uid": "global-domain-uid", "name": "Global"},
                            },
                            {
                                "uid": "current-domain-network-layer",
                                "name": "Network",
                                "domain": {"uid": "domain-general-uid", "name": "General"},
                            },
                        ],
                    },
                    message="",
                    code="",
                )

            assert command == "show-changes"
            return SimpleNamespace(
                success=True,
                data={"requested-domain": domain, "tasks": []},
                message="",
                code="",
            )

    monkeypatch.setattr(ritm_flow, "ObjectMatcher", DummyMatcher)
    monkeypatch.setattr(ritm_flow, "CPAIOPSClient", DummyClient)
    monkeypatch.setattr(rule_manager_module, "CheckPointRuleManager", DummyRuleManager)

    apply_resp = await async_client.post(f"/api/v1/ritm/{ritm_number}/apply")
    assert apply_resp.status_code == 200

    payload = apply_resp.json()
    assert payload["rules_created"] == 1
    assert captured_layers == ["current-domain-network-layer"]
    assert payload["session_changes"]["apply_sessions"]["General"] == "sid-general-apply"
    assert payload["session_changes"]["apply_session_trace"] == [
        {"domain": "General", "sid": "sid-general-apply", "session_uid": "uid-general-apply"}
    ]
    assert payload["session_changes"]["show_changes_requests"]["General"] == {
        "mgmt_name": "mgmt-test",
        "domain": "General",
        "command": "show-changes",
        "details_level": "full",
        "payload": {"to-session": "uid-general-apply"},
    }
    assert payload["session_changes"]["domain_changes"]["General"]["requested-domain"] == "General"


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

    # Submit one for approval
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
