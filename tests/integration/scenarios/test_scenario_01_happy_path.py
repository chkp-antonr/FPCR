"""
Scenario 1 — Happy Path

eng1 creates a RITM with policy in both domains, runs try-verify,
submits for approval. eng2 approves and publishes. Verifies COMPLETED.
"""

import pytest
from httpx import AsyncClient

RITM_NUMBER = "RITM9990001"


@pytest.mark.integration
@pytest.mark.usefixtures("cp_restored")
class TestHappyPath:
    ritm_id: str = RITM_NUMBER

    @pytest.mark.order(1)
    async def test_01_create_ritm(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            "/api/v1/ritm",
            json={"ritm_number": RITM_NUMBER},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ritm_number"] == RITM_NUMBER
        assert data["status"] == 0  # WORK_IN_PROGRESS
        assert data["editor_locked_by"] is not None
        editors = [e for e in data.get("editors", [])]
        assert any(editors), "eng1 must be in ritm_editors after create"

    @pytest.mark.order(2)
    async def test_02_add_policy(
        self, eng1_client: AsyncClient, test_env
    ):
        policy = [
            {
                "ritm_number": RITM_NUMBER,
                "comments": "Test rule DomainA",
                "rule_name": "RITM9990001_A_rule1",
                "domain_uid": test_env.domain_a_uid,
                "domain_name": test_env.domain_a_name,
                "package_uid": test_env.package_a_uid,
                "package_name": test_env.package_name,
                "section_uid": test_env.section_a_uid,
                "section_name": test_env.section_name,
                "position_type": "top",
                "position_number": None,
                "action": "accept",
                "track": "log",
                "source_ips": ["10.0.0.1"],
                "dest_ips": ["10.0.0.2"],
                "services": ["svc_http_8080"],
            },
            {
                "ritm_number": RITM_NUMBER,
                "comments": "Test rule DomainB",
                "rule_name": "RITM9990001_B_rule1",
                "domain_uid": test_env.domain_b_uid,
                "domain_name": test_env.domain_b_name,
                "package_uid": test_env.package_b_uid,
                "package_name": test_env.package_name,
                "section_uid": test_env.section_b_uid,
                "section_name": test_env.section_name,
                "position_type": "top",
                "position_number": None,
                "action": "accept",
                "track": "log",
                "source_ips": ["10.1.0.0/24"],
                "dest_ips": ["10.0.0.2"],
                "services": ["svc_custom_9999"],
            },
        ]
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy",
            json=policy,
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(3)
    async def test_03_pre_verify_passes(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["all_passed"] is True, (
            f"Pre-verify failed unexpectedly: {data}"
        )

    @pytest.mark.order(4)
    async def test_04_plan_yaml_has_section(
        self, eng1_client: AsyncClient, test_env
    ):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/plan-yaml"
        )
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert test_env.section_name in body, (
            f"Expected {test_env.section_name!r} in plan YAML"
        )
        assert "Host_10.0.0.1" in body or "10.0.0.1" in body

    @pytest.mark.order(5)
    async def test_05_try_verify(self, eng1_client: AsyncClient, test_env):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["published"] is True or len(data["results"]) > 0
        assert data["evidence_html"] is not None, "evidence_html must be present"
        states = [r.get("state", "") for r in data["results"]]
        assert all(
            s == "verified_pending_approval_disabled" for s in states
        ), f"Unexpected package states: {states}"

    @pytest.mark.order(6)
    async def test_06_evidence_history(self, eng1_client: AsyncClient):
        resp = await eng1_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        all_sessions = [
            s
            for d in data["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        assert len(all_sessions) == 2, (
            f"Expected 2 evidence sessions, got {len(all_sessions)}"
        )
        assert all(s["session_type"] == "initial" for s in all_sessions), (
            f"Expected all session_type=initial: {[s['session_type'] for s in all_sessions]}"
        )

    @pytest.mark.order(7)
    async def test_07_session_pdf(self, eng1_client: AsyncClient):
        resp = await eng1_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/session-pdf",
            params={"attempt": 1},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers.get("content-type", "").startswith(
            "application/pdf"
        ), f"Expected PDF, got: {resp.headers.get('content-type')}"

    @pytest.mark.order(8)
    async def test_08_submit_for_approval(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text
        check = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.status_code == 200
        assert check.json()["status"] == 1  # READY_FOR_APPROVAL

    @pytest.mark.order(9)
    async def test_09_not_in_editor_list(self, eng1_client: AsyncClient):
        resp = await eng1_client.get(
            "/api/v1/ritm",
            params={"status": 0},
        )
        assert resp.status_code == 200
        numbers = [r["ritm_number"] for r in resp.json()]
        assert RITM_NUMBER not in numbers, (
            "RITM should not appear in WIP list after submit"
        )

    @pytest.mark.order(10)
    async def test_10_eng1_cannot_approve(self, eng1_client: AsyncClient):
        resp = await eng1_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}",
            json={"status": 2},
        )
        assert resp.status_code == 400, (
            f"Expected 400 (eng1 is editor), got {resp.status_code}"
        )

    @pytest.mark.order(11)
    async def test_11_eng2_acquires_lock(self, eng2_client: AsyncClient):
        resp = await eng2_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/lock"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["approver_locked_by"] is not None

    @pytest.mark.order(12)
    async def test_12_eng2_sees_evidence(self, eng2_client: AsyncClient):
        resp = await eng2_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        all_sessions = [
            s
            for d in data["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        assert len(all_sessions) == 2

    @pytest.mark.order(13)
    async def test_13_eng2_approves(self, eng2_client: AsyncClient):
        resp = await eng2_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}",
            json={"status": 2},
        )
        assert resp.status_code == 200, resp.text
        check = await eng2_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        data = check.json()
        assert data["status"] == 2  # APPROVED
        reviewers = data.get("reviewers", [])
        assert any(
            r["action"] == "approved" for r in reviewers
        ), f"No approved reviewer found: {reviewers}"

    @pytest.mark.order(14)
    async def test_14_publish(self, eng2_client: AsyncClient):
        resp = await eng2_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/publish"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True, f"Publish failed: {data}"

    @pytest.mark.order(15)
    async def test_15_completed(self, eng1_client: AsyncClient):
        resp = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert resp.status_code == 200
        assert resp.json()["status"] == 3  # COMPLETED
