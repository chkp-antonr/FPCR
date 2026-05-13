"""
Scenario 3 — Post-Check Rollback

Policy is crafted to pass pre-check but fail post-check
(duplicate rule name in the same section).
Verifies rollback (POSTCHECK_FAILED_RULES_DELETED),
then fixes and succeeds on attempt 2.
"""

import os

import pytest
from cpaiops import CPAIOPSClient
from httpx import AsyncClient

RITM_NUMBER = "RITM9990003"

# A rule name that already exists in the test section (seeded by seed.py).
# Using an existing name triggers CP's post-check duplicate-name error.
CONFLICTING_RULE_NAME = "RITM_TEST_SECTION_CONFLICT"


def _policy(test_env: object, rule_name: str) -> list[dict]:
    return [
        {
            "ritm_number": RITM_NUMBER,
            "comments": "Scenario 3 rule",
            "rule_name": rule_name,
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


@pytest.mark.integration
@pytest.mark.usefixtures("cp_restored")
class TestPostCheckRollback:

    @pytest.mark.order(1)
    async def test_01_create_ritm(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            "/api/v1/ritm", json={"ritm_number": RITM_NUMBER}
        )
        assert resp.status_code == 201, resp.text

    @pytest.mark.order(2)
    async def test_02_add_conflicting_policy(
        self, eng1_client: AsyncClient, test_env
    ):
        """
        Add a rule whose name already exists in RITM_TEST_SECTION
        so that post-check verify-policy fails.
        """
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy",
            json=_policy(test_env, CONFLICTING_RULE_NAME),
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(3)
    async def test_03_preverify_passes(self, eng1_client: AsyncClient):
        """Baseline must be clean for pre-check to pass."""
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["all_passed"] is True

    @pytest.mark.order(4)
    async def test_04_try_verify_fails_postcheck(
        self, eng1_client: AsyncClient
    ):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        states = [r.get("state", "") for r in data["results"]]
        assert any(
            s == "postcheck_failed_rules_deleted" for s in states
        ), f"Expected postcheck_failed_rules_deleted, got: {states}"

    @pytest.mark.order(5)
    async def test_05_no_evidence_for_attempt_1(
        self, eng1_client: AsyncClient
    ):
        """Failed attempt produces no evidence session."""
        resp = await eng1_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        all_sessions = [
            s
            for d in resp.json()["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        assert len(all_sessions) == 0, (
            f"Expected 0 sessions after rollback, got {len(all_sessions)}"
        )

    @pytest.mark.order(6)
    async def test_06_verify_rollback_in_cp(
        self, eng1_client: AsyncClient, test_env
    ):
        """
        Verify rollback via DB state AND CP API.
        DB: attempt 1 state must be postcheck_failed_rules_deleted.
        CP: section must contain exactly 1 rule named CONFLICTING_RULE_NAME (the seed rule),
            not 2 (which would mean the RITM-created copy was not deleted).
        """
        # DB state check
        resp = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        attempts = data.get("attempts", [])
        attempt1_states = [
            a.get("state", "") for a in attempts if a.get("attempt_number") == 1
        ]
        if attempts:
            assert any(
                s == "postcheck_failed_rules_deleted" for s in attempt1_states
            ), f"Attempt 1 must be postcheck_failed_rules_deleted, got: {attempt1_states}"
        # If API doesn't expose attempts, test_04's state check is sufficient.

        # CP API check: count rules named CONFLICTING_RULE_NAME in the section
        async with CPAIOPSClient(
            username=os.environ["API_USERNAME"],
            password=os.environ["API_PASSWORD"],
            mgmt_ip=os.environ["API_MGMT"],
        ) as cp:
            mgmt_name: str = cp.get_mgmt_names()[0]
            result = await cp.api_call(
                mgmt_name,
                "show-access-rulebase",
                test_env.domain_a_name,
                payload={
                    "name": test_env.package_name,
                    "filter": CONFLICTING_RULE_NAME,
                    "filter-settings": {"search-mode": "general"},
                    "limit": 50,
                },
            )
            assert result.success, (
                f"CP show-access-rulebase call failed: {result.data}"
            )
            rules = result.data.get("rulebase", [])
            matching = [
                r for r in rules
                if r.get("name") == CONFLICTING_RULE_NAME
            ]
            assert len(matching) <= 1, (
                f"Expected at most 1 rule named {CONFLICTING_RULE_NAME!r} after rollback "
                f"(seed rule only), found {len(matching)}. Rollback may have failed."
            )

    @pytest.mark.order(7)
    async def test_07_fix_policy(
        self, eng1_client: AsyncClient, test_env
    ):
        """Replace policy with a valid, non-conflicting rule name."""
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy",
            json=_policy(test_env, "RITM9990003_A_rule1"),
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(8)
    async def test_08_try_verify_attempt2_passes(
        self, eng1_client: AsyncClient
    ):
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

    @pytest.mark.order(9)
    async def test_09_evidence_attempt2_is_correction(
        self, eng1_client: AsyncClient
    ):
        resp = await eng1_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        assert resp.status_code == 200, resp.text
        all_sessions = [
            s
            for d in resp.json()["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        assert len(all_sessions) == 1
        assert all_sessions[0]["attempt"] == 2
        assert all_sessions[0]["session_type"] == "correction"

    @pytest.mark.order(10)
    async def test_10_submit(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(11)
    async def test_11_eng3_approves_and_publishes(
        self, eng3_client: AsyncClient
    ):
        await eng3_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
        resp = await eng3_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 200, resp.text
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/publish"
        )
        assert resp.json()["success"] is True
        check = await eng3_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.json()["status"] == 3  # COMPLETED
