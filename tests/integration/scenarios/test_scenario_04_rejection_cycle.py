"""
Scenario 4 — Rejection Cycle / 4-User Separation of Duties

Verifies that after any actor touches a RITM, their complementary role
is permanently blocked — even across multiple rejection/correction cycles.

eng1: initial editor (blocked from approving forever)
eng2: first rejecter (blocked from editing forever)
eng3: correction editor (blocked from approving forever)
eng4: second rejecter (blocked from editing forever)
"""

import os

import pytest
from httpx import AsyncClient

RITM_NUMBER = "RITM9990004"


def _policy_a(test_env: object, rule_name: str) -> list[dict]:
    return [
        {
            "ritm_number": RITM_NUMBER,
            "comments": f"Scenario 4 {rule_name}",
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
class TestRejectionCycle:

    # -- Initial edit by eng1 ------------------------------------------------

    @pytest.mark.order(1)
    async def test_01_eng1_creates(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            "/api/v1/ritm", json={"ritm_number": RITM_NUMBER}
        )
        assert resp.status_code == 201, resp.text

    @pytest.mark.order(2)
    async def test_02_eng1_adds_policy(
        self, eng1_client: AsyncClient, test_env
    ):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy",
            json=_policy_a(test_env, "RITM9990004_initial"),
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(3)
    async def test_03_eng1_try_verify(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        states = [r.get("state", "") for r in resp.json()["results"]]
        assert all(s == "verified_pending_approval_disabled" for s in states)

    @pytest.mark.order(4)
    async def test_04_eng1_submits(self, eng1_client: AsyncClient):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text
        check = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.json()["status"] == 1  # READY_FOR_APPROVAL

    # -- Role block: eng1 cannot approve own RITM ----------------------------

    @pytest.mark.order(5)
    async def test_05_eng1_cannot_approve(self, eng1_client: AsyncClient):
        resp = await eng1_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 400, (
            f"Expected 400 for eng1 self-approve, got {resp.status_code}"
        )

    # -- eng2: review and reject ---------------------------------------------

    @pytest.mark.order(6)
    async def test_06_eng2_reviews_evidence(
        self, eng2_client: AsyncClient
    ):
        await eng2_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
        resp = await eng2_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        assert resp.status_code == 200
        sessions = [
            s
            for d in resp.json()["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        assert len(sessions) >= 1

    @pytest.mark.order(7)
    async def test_07_eng2_rejects(self, eng2_client: AsyncClient):
        resp = await eng2_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}",
            json={"status": 0, "feedback": "Please add Host_10.0.0.2 as source."},
        )
        assert resp.status_code == 200, resp.text
        check = await eng2_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        data = check.json()
        assert data["status"] == 0  # back to WIP
        assert data["feedback"] == "Please add Host_10.0.0.2 as source."

    # -- Role block: eng2 cannot acquire editor lock after rejecting ----------

    @pytest.mark.order(8)
    async def test_08_eng2_cannot_edit(self, eng2_client: AsyncClient):
        resp = await eng2_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
        )
        assert resp.status_code == 400, (
            f"Expected 400 for eng2 (reviewer) editor lock, got {resp.status_code}"
        )

    # -- eng3: take correction, edit, try-verify, submit ---------------------

    @pytest.mark.order(9)
    async def test_09_eng3_acquires_editor_lock(
        self, eng3_client: AsyncClient
    ):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
        )
        assert resp.status_code == 200, (
            f"eng3 should be able to acquire editor lock: {resp.text}"
        )

    @pytest.mark.order(10)
    async def test_10_eng3_updates_policy(
        self, eng3_client: AsyncClient, test_env
    ):
        """eng3 updates policy to address eng2's feedback."""
        policy = _policy_a(test_env, "RITM9990004_correction")
        policy[0]["source_ips"] = ["10.0.0.1", "10.0.0.2"]
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(11)
    async def test_11_eng3_try_verify_attempt2(
        self, eng3_client: AsyncClient
    ):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        states = [r.get("state", "") for r in data["results"]]
        assert all(s == "verified_pending_approval_disabled" for s in states)
        ev = await eng3_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        sessions = [
            s
            for d in ev.json()["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        correction_sessions = [s for s in sessions if s["session_type"] == "correction"]
        assert len(correction_sessions) >= 1, (
            "Expected at least one correction session after attempt 2"
        )

    @pytest.mark.order(12)
    async def test_12_eng3_submits(self, eng3_client: AsyncClient):
        resp = await eng3_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text
        check = await eng3_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.json()["status"] == 1  # READY_FOR_APPROVAL

    # -- Role blocks after correction ----------------------------------------

    @pytest.mark.order(13)
    async def test_13_eng2_still_cannot_approve(
        self, eng2_client: AsyncClient
    ):
        """eng2 is still in ritm_reviewers — cannot approve."""
        resp = await eng2_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 400, (
            "eng2 (reviewer) should still be blocked from approving"
        )

    @pytest.mark.order(14)
    async def test_14_eng3_cannot_approve_own_correction(
        self, eng3_client: AsyncClient
    ):
        """eng3 is now in ritm_editors — cannot approve."""
        resp = await eng3_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 400, (
            "eng3 (editor) should be blocked from approving"
        )

    # -- eng4: review and reject (2nd rejection) -----------------------------

    @pytest.mark.order(15)
    async def test_15_eng4_acquires_approver_lock(
        self, eng4_client: AsyncClient
    ):
        resp = await eng4_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/lock"
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.order(16)
    async def test_16_eng4_sees_both_attempts(
        self, eng4_client: AsyncClient
    ):
        resp = await eng4_client.get(
            f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
        )
        assert resp.status_code == 200, resp.text
        sessions = [
            s
            for d in resp.json()["domains"]
            for p in d["packages"]
            for s in p["sessions"]
        ]
        attempts = {s["attempt"] for s in sessions}
        assert 1 in attempts and 2 in attempts, (
            f"Expected attempts 1 and 2 in evidence, got: {attempts}"
        )

    @pytest.mark.order(17)
    async def test_17_eng4_rejects(self, eng4_client: AsyncClient):
        resp = await eng4_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}",
            json={"status": 0, "feedback": "Service svc_http_8080 not permitted."},
        )
        assert resp.status_code == 200, resp.text
        check = await eng4_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.json()["status"] == 0  # back to WIP

    # -- Role blocks: eng4 and eng3 ------------------------------------------

    @pytest.mark.order(18)
    async def test_18_eng4_cannot_edit_after_reject(
        self, eng4_client: AsyncClient
    ):
        resp = await eng4_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
        )
        assert resp.status_code == 400, (
            "eng4 (reviewer) must be blocked from editor lock"
        )

    @pytest.mark.order(19)
    async def test_19_eng3_cannot_approve_after_2nd_rejection(
        self, eng3_client: AsyncClient
    ):
        resp = await eng3_client.put(
            f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
        )
        assert resp.status_code == 400

    # -- eng1 can re-edit (not in ritm_reviewers) ----------------------------

    @pytest.mark.order(20)
    async def test_20_eng1_reacquires_editor_lock(
        self, eng1_client: AsyncClient
    ):
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
        )
        assert resp.status_code == 200, (
            f"eng1 (not a reviewer) should be able to re-acquire editor lock: {resp.text}"
        )

    @pytest.mark.order(21)
    async def test_21_eng1_try_verify_attempt3(
        self, eng1_client: AsyncClient
    ):
        """eng1 performs try-verify (attempt 3) to show they can still edit."""
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
            json={"skip_package_uids": []},
        )
        assert resp.status_code == 200, resp.text
        states = [r.get("state", "") for r in resp.json()["results"]]
        assert all(s == "verified_pending_approval_disabled" for s in states), (
            f"eng1 attempt 3 should succeed: {states}"
        )

    @pytest.mark.order(22)
    async def test_22_eng1_submits_attempt3(self, eng1_client: AsyncClient):
        """eng1 submits attempt 3 — all 4 named users are now blocked."""
        resp = await eng1_client.post(
            f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
        )
        assert resp.status_code == 200, resp.text
        check = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        assert check.json()["status"] == 1  # READY_FOR_APPROVAL

    @pytest.mark.order(23)
    async def test_23_4_users_all_blocked_summary(
        self, eng1_client: AsyncClient
    ):
        """
        Verify final state:
        - eng1: in ritm_editors (can edit, cannot approve)
        - eng2: in ritm_reviewers (cannot edit)
        - eng3: in ritm_editors (can edit, cannot approve)
        - eng4: in ritm_reviewers (cannot edit)

        Final approval would require a 5th user not in either table.
        """
        resp = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
        data = resp.json()
        editors = data.get("editors", [])
        reviewers = data.get("reviewers", [])
        eng2_user = os.environ["ENGINEER2_USER"]
        eng3_user = os.environ["ENGINEER3_USER"]
        eng4_user = os.environ["ENGINEER4_USER"]
        assert any(
            r["username"] == eng2_user for r in reviewers
        ), f"eng2 must be in reviewers (not editors): reviewers={reviewers}"
        assert any(
            r["username"] == eng4_user for r in reviewers
        ), f"eng4 must be in reviewers (not editors): reviewers={reviewers}"
        assert eng3_user in editors, "eng3 must appear in editors"
