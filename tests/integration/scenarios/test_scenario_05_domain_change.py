"""
Scenario 5 — Domain Change After Rejection

eng1 creates a RITM with policy in DomainA only.
eng2 rejects: "move rules to DomainB".
eng3 acquires editor lock, switches policy to DomainB.
plan-yaml validates DomainA objects absent, DomainB objects present.
try-verify attempt 2 creates DomainB rules.
Evidence history shows DomainA session (attempt 1) and DomainB session (attempt 2).
eng4 approves and publishes -> COMPLETED.
"""

import pytest
from httpx import AsyncClient

RITM_NUMBER = "RITM9990005"


@pytest.mark.integration
@pytest.mark.usefixtures("cp_restored")
class TestDomainChange:

    @pytest.mark.order(1)
    async def test_01_eng1_creates(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            "/api/v1/ritm", json={"ritm_number": RITM_NUMBER}
        )
        assert resp.status_code == 201, resp.text

    @pytest.mark.order(2)
    async def test_02_policy_domain_a_only(
        self, eng1_client: AsyncClient, test_env
    ):
        policy = [
            {
                "ritm_number": RITM_NUMBER,
                "comments": "Scenario 5 DomainA rule",
                "rule_name": "RITM9990005_A_rule1",
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
            }
        ]
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(3)
    async def test_03_try_verify_domain_a(
        self, eng1_client: AsyncClient, test_env
    ):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        states = [r.get("state", "") for r in data["results"]]
        assert all(s == "verified_pending_approval_disabled" for s in states)
        ev = await eng1_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        domain_names = [d["domain_name"] for d in ev.json()["domains"]]
        assert test_env.domain_a_name in domain_names
        assert test_env.domain_b_name not in domain_names

    @pytest.mark.order(4)
    async def test_04_submit(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(5)
    async def test_05_eng2_rejects_with_domain_feedback(
        self, eng2_client: AsyncClient
    ):
        await eng2_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
        resp = await eng2_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}",
            json={"status": 0, "feedback": "Move rules to DomainB instead."},
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(6)
    async def test_06_eng3_acquires_editor_lock(
        self, eng3_client: AsyncClient
    ):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(7)
    async def test_07_eng3_changes_policy_to_domain_b(
        self, eng3_client: AsyncClient, test_env
    ):
        policy = [
            {
                "ritm_number": RITM_NUMBER,
                "comments": "Scenario 5 DomainB rule (after domain change)",
                "rule_name": "RITM9990005_B_rule1",
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
                "source_ips": ["10.0.0.1"],
                "dest_ips": ["Net_10.1.0.0_24"],
                "services": ["svc_custom_9999"],
            }
        ]
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(8)
    async def test_08_plan_yaml_has_domain_b_not_domain_a(
        self, eng3_client: AsyncClient, test_env
    ):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/plan-yaml"
        )
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert test_env.domain_b_name in body or "RITM9990005_B_rule1" in body, (
            "plan-yaml must reference DomainB rule"
        )
        assert "RITM9990005_A_rule1" not in body, (
            "plan-yaml must not reference the old DomainA rule after policy replacement"
        )

    @pytest.mark.order(9)
    async def test_09_try_verify_attempt2_domain_b(
        self, eng3_client: AsyncClient, test_env
    ):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        states = [r.get("state", "") for r in data["results"]]
        assert all(s == "verified_pending_approval_disabled" for s in states)

    @pytest.mark.order(10)
    async def test_10_cp_state_domain_a_rules_persisted(
        self, eng3_client: AsyncClient, test_env
    ):
        """
        Spec step 10: DomainA rules from attempt 1 remain in CP as published-disabled
        after submit-for-approval published them. Verify via CP API.
        Also, the plan-yaml for attempt 2 should reference removal of those rules.
        """
        import os
        from cpaiops import CPAIOPSClient

        async with CPAIOPSClient(
            username=os.environ["API_USERNAME"],
            password=os.environ["API_PASSWORD"],
            mgmt_ip=os.environ["API_MGMT"],
        ) as cp:
            mgmt_name: str = cp.get_mgmt_names()[0]
            result = await cp.api_call(
                mgmt_name,
                "show-access-rule",
                test_env.domain_a_name,
                payload={
                    "layer": test_env.package_name,
                    "name": "RITM9990005_A_rule1",
                },
            )
            assert result.success, (
                "DomainA rule from attempt 1 must still exist in CP as published-disabled. "
                f"Response: {result.data}"
            )
            rule_enabled = result.data.get("enabled", True)
            assert rule_enabled is False, (
                f"DomainA rule must be disabled (published-disabled state), got enabled={rule_enabled}"
            )

    @pytest.mark.order(11)
    async def test_11_evidence_history_has_both_domains(
        self, eng3_client: AsyncClient, test_env
    ):
        resp = await eng3_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        domain_names = {d["domain_name"] for d in data["domains"]}
        assert test_env.domain_a_name in domain_names, (
            "DomainA evidence (attempt 1) must still be present"
        )
        assert test_env.domain_b_name in domain_names, (
            "DomainB evidence (attempt 2) must be present"
        )
        for d in data["domains"]:
            if d["domain_name"] == test_env.domain_b_name:
                for p in d["packages"]:
                    for s in p["sessions"]:
                        assert s["session_type"] == "correction", (
                            f"DomainB sessions must be 'correction', got {s['session_type']}"
                        )

    @pytest.mark.order(12)
    async def test_12_eng3_submits(self, eng3_client: AsyncClient):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(13)
    async def test_13_eng4_approves(self, eng4_client: AsyncClient):
        await eng4_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
        resp = await eng4_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 200, resp.text
        check = await eng4_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.status_code == 200, check.text
        assert check.json()["status"] == 2, f"Expected APPROVED (2), got {check.json()['status']}"

    @pytest.mark.order(14)
    async def test_14_eng4_publishes(self, eng4_client: AsyncClient):
        resp = await eng4_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/publish"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

    @pytest.mark.order(15)
    async def test_15_completed(self, eng4_client: AsyncClient):
        check = await eng4_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.status_code == 200, check.text
        assert check.json()["status"] == 3  # COMPLETED
