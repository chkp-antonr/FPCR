"""Domain endpoints."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..cache_service import cache_service
from ..mock_source import MockDataSource
from ..models import (
    CreateRuleRequest,
    Domains2BatchRequest,
)
from ..session import SessionData, session_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["domains"])


async def get_session_data_optional(request: Request) -> SessionData | None:
    """Dependency to get current session, returns None for mock mode."""
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        logger.info("Mock mode enabled - skipping authentication")
        return None

    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


async def get_session_data(request: Request) -> SessionData:
    """Dependency to get current session."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


@router.get("/domains")
async def list_domains(
    session: SessionData | None = Depends(get_session_data_optional),
) -> dict[str, Any]:
    """
    List all Check Point domains.

    Returns cached data. Refreshes cache if empty.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        logger.warning(f"MOCK_DATA env var: {mock_data_path}")

    if mock_data_path:
        logger.info(f"Using mock data source: {mock_data_path}")
        mock = MockDataSource(mock_data_path)
        domains = mock.get_domains()
        return {"domains": [{"name": d.name, "uid": d.uid} for d in domains]}

    waited_for_refresh = await cache_service.wait_for_core_refresh()
    if waited_for_refresh:
        logger.info("Domains request waited for core cache refresh to complete")

    # Try cache first
    cached = await cache_service.get_cached_domains()
    if cached:
        logger.info(f"Returning {len(cached)} cached domains")
        return {"domains": [{"name": d.name, "uid": d.uid} for d in cached]}

    # Cache empty - refresh first, then return from cache
    logger.info("Cache empty, refreshing from Check Point API")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_all(session.username, session.password, mgmt_ip)

    # Now return from freshly populated cache
    cached = await cache_service.get_cached_domains()
    return {"domains": [{"name": d.name, "uid": d.uid} for d in cached]}


@router.post("/domains/rules/batch")
async def create_rules_batch(
    rules: list[CreateRuleRequest],
    _session: SessionData | None = Depends(get_session_data_optional),
) -> dict[str, Any]:
    """
    MOCK: Create multiple firewall rules across domains.
    TODO: Implement actual Check Point API calls.
    """
    logger.info(f"Received batch rules request: {len(rules)} rules")

    for i, rule in enumerate(rules):
        if not rule.source.domain_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: Source domain_uid is required")
        if not rule.source.package_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: Source package_uid is required")
        if not rule.destination.domain_uid:
            raise HTTPException(
                status_code=400, detail=f"Rule {i}: Destination domain_uid is required"
            )
        if not rule.destination.package_uid:
            raise HTTPException(
                status_code=400, detail=f"Rule {i}: Destination package_uid is required"
            )

        for line_name, line in [("source", rule.source), ("destination", rule.destination)]:
            if line.position.type == "custom" and line.position.custom_number is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rule {i} {line_name}: Custom position requires custom_number",
                )

    return {"success": True, "created": len(rules) * 2, "failed": 0, "errors": []}


@router.get("/domains/topology")
async def get_topology(
    session: SessionData | None = Depends(get_session_data_optional),
) -> dict[str, Any]:
    """
    Return subnet topology for prediction engine.
    MOCK: Returns mock_data.yaml structure.
    Production: Query Check Point API for network topology.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    logger.info(f"Topology request, MOCK_DATA: {mock_data_path}")

    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        topology = mock.get_topology()
        return {"topology": topology}

    # Production implementation
    logger.info("Using live Check Point API for topology")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # TODO: Implement live topology query
    return {"topology": []}


@router.post("/domains2/rules/batch")
async def create_rules_domains2_batch(
    request: Domains2BatchRequest, _session: SessionData | None = Depends(get_session_data_optional)
) -> dict[str, Any]:
    """
    Create rules with multiple source/dest IPs per rule.
    MOCK: Validates and returns success.
    Production: Creates actual Check Point firewall rules.
    """
    logger.info(f"Domains_2 batch request: {len(request.rules)} rules")

    # Validate
    for i, rule in enumerate(request.rules):
        if not rule.domain_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: domain_uid is required")
        if not rule.package_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: package_uid is required")
        if len(rule.source_ips) == 0:
            raise HTTPException(
                status_code=400, detail=f"Rule {i}: At least one source IP required"
            )
        if len(rule.dest_ips) == 0:
            raise HTTPException(status_code=400, detail=f"Rule {i}: At least one dest IP required")

        if rule.position.type == "custom" and rule.position.custom_number is None:
            raise HTTPException(
                status_code=400, detail=f"Rule {i}: Custom position requires custom_number"
            )

    # TODO: Production - create actual Check Point rules
    # For now, just validate and return success
    total_rules = sum(len(r.source_ips) * len(r.dest_ips) for r in request.rules)

    return {"success": True, "created": total_rules, "failed": 0, "errors": []}


@router.get("/cache/status")
async def get_cache_status() -> dict[str, Any]:
    """Return cache status with timestamps."""
    return await cache_service.get_status()


@router.post("/cache/refresh")
async def refresh_cache(session: SessionData = Depends(get_session_data)) -> dict[str, str]:
    """Refresh domains and packages, then continue section warmup in the background."""
    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_all(session.username, session.password, mgmt_ip)

    return {"message": "Domains and packages refreshed. Sections are warming in the background."}
