"""
Scenario 2 — Pre-Verify Error and Correction

1. Enable BROKEN_RULE in DomainA to make pre-verify fail.
2. Create RITM, add policy targeting DomainA.
3. Pre-verify -> fails (references BROKEN_RULE).
4. Delete BROKEN_RULE via CP API.
5. Pre-verify again -> passes.
6. Try-verify -> succeeds.
7. Submit -> eng2 approves -> publish -> COMPLETED.
"""

import pytest
from httpx import AsyncClient

RITM_NUMBER = "RITM9990002"


@pytest.mark.integration
@pytest.mark.usefixtures("cp_restored")
class TestPreVerifyError:

    @pytest.mark.order(1)
    async def test_01_enable_broken_rule(
        self, eng1_client: AsyncClient, test_env, admin_cp
    ):
        """Enable BROKEN_RULE in DomainA so that pre-verify fails."""
        cp, mgmt_name = admin_cp
        await cp.api_call(
            mgmt_name,
            "set-access-rule",
            test_env.domain_a_name,
            payload={
                "layer": test_env.package_name,
                "name": "BROKEN_RULE",
                "enabled": True,
            },
        )
        await cp.api_call(
            mgmt_name,
            "publish",
            test_env.domain_a_name,
        )

    @pytest.mark.order(2)
    async def test_02_create_ritm(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            "/api/v1/ritm",
            json={"ritm_number": RITM_NUMBER},
        )
        assert resp.status_code == 201, resp.text

    @pytest.mark.order(3)
    async def test_03_add_policy(
        self, eng1_client: AsyncClient, test_env
    ):
        policy = [
            {
                "ritm_number": RITM_NUMBER,
                "comments": "Scenario 2 DomainA rule",
                "rule_name": "RITM9990002_A_rule1",
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

    @pytest.mark.order(4)
    async def test_04_preverify_fails(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["all_passed"] is False, (
            "Pre-verify should fail with BROKEN_RULE active"
        )
        all_errors = [
            e
            for r in data["results"]
            for e in r.get("errors", [])
        ]
        assert len(all_errors) > 0, "Expected error messages in pre-verify result"
        broken_rule_mentioned = any(
            "BROKEN_RULE" in str(e) for e in all_errors
        )
        assert broken_rule_mentioned, (
            f"Expected at least one error to mention BROKEN_RULE: {all_errors}"
        )

    @pytest.mark.order(5)
    async def test_05_delete_broken_rule(
        self, eng1_client: AsyncClient, test_env, admin_cp
    ):
        """Delete BROKEN_RULE via CP API to fix the pre-verify issue."""
        cp, mgmt_name = admin_cp
        await cp.api_call(
            mgmt_name,
            "delete-access-rule",
            test_env.domain_a_name,
            payload={
                "layer": test_env.package_name,
                "name": "BROKEN_RULE",
            },
        )
        await cp.api_call(
            mgmt_name,
            "publish",
            test_env.domain_a_name,
        )

    @pytest.mark.order(6)
    async def test_06_preverify_passes(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["all_passed"] is True, (
            f"Pre-verify still failing after fix: {data}"
        )

    @pytest.mark.order(7)
    async def test_07_try_verify(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        states = [r.get("state", "") for r in data["results"]]
        assert all(
            s == "verified_pending_approval_disabled" for s in states
        ), f"Unexpected states: {states}"

    @pytest.mark.order(8)
    async def test_08_submit(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(9)
    async def test_09_approve(self, eng2_client: AsyncClient):
        await eng2_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
        resp = await eng2_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(10)
    async def test_10_publish_completed(self, eng2_client: AsyncClient):
        resp = await eng2_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/publish"
        )
        assert resp.status_code == 200, resp.text
        check = await eng2_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.json()["status"] == 3  # COMPLETED
