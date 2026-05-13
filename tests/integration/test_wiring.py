"""Verifies test infrastructure is wired up correctly before running scenarios."""

import pytest


@pytest.mark.integration
async def test_eng1_can_reach_fpcr(eng1_client):
    """eng1 is logged in and can call a health endpoint."""
    resp = await eng1_client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.integration
async def test_test_env_has_uids(test_env):
    """TestEnv fixture resolves domain/package/section UIDs."""
    assert test_env.domain_a_uid, "domain_a_uid is empty"
    assert test_env.domain_b_uid, "domain_b_uid is empty"
    assert test_env.package_a_uid, "package_a_uid is empty"
    assert test_env.section_a_uid, "section_a_uid is empty"
    assert test_env.section_b_uid, "section_b_uid is empty"
