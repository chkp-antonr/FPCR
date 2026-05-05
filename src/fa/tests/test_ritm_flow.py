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
