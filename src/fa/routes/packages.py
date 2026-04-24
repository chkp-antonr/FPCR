"""Package and section endpoints."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..cache_service import cache_service
from ..mock_source import MockDataSource
from ..session import SessionData, session_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["packages"])


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


@router.get("/domains/{domain_uid}/packages")
async def list_packages(
    domain_uid: str, session: SessionData | None = Depends(get_session_data_optional)
) -> dict[str, Any]:
    """
    List all policy packages for a domain.

    Returns cached data. Refreshes domain cache if empty.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        packages = mock.get_packages(domain_uid)
        return {
            "packages": [
                {"name": p.name, "uid": p.uid, "access_layer": p.access_layer} for p in packages
            ]
        }

    await cache_service.wait_for_core_refresh()
    logger.info("Packages request waited for core cache refresh to complete")

    # Try cache first
    cached = await cache_service.get_cached_packages(domain_uid)

    if cached:
        return {
            "packages": [
                {"name": p.name, "uid": p.uid, "access_layer": p.access_layer} for p in cached
            ]
        }

    # Cache empty for this domain - check if refresh is in progress
    cache_status = await cache_service.get_status()
    if cache_status.get("refreshing"):
        raise HTTPException(
            status_code=503, detail="Cache is being refreshed. Please try again in a moment."
        )

    # Cache empty and no refresh in progress - trigger refresh
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_all(session.username, session.password, mgmt_ip)

    # Now return from freshly populated cache
    cached = await cache_service.get_cached_packages(domain_uid)
    return {
        "packages": [{"name": p.name, "uid": p.uid, "access_layer": p.access_layer} for p in cached]
    }


@router.get("/domains/{domain_uid}/packages/{pkg_uid}/sections")
async def list_sections(
    domain_uid: str,
    pkg_uid: str,
    session: SessionData | None = Depends(get_session_data_optional),
) -> dict[str, Any]:
    """
    List all sections for a policy package with rule ranges.

    Returns cached data. Refreshes the selected package sections on demand if needed.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        sections, total = mock.get_sections(domain_uid, pkg_uid)
        return {
            "sections": [
                {
                    "name": s.name,
                    "uid": s.uid,
                    "rulebase_range": s.rulebase_range,
                    "rule_count": s.rule_count,
                }
                for s in sections
            ],
            "total_rules": total,
        }

    # Try cache first
    cached = await cache_service.get_cached_sections(domain_uid, pkg_uid)
    if cached:
        total_rules = sum(s.rule_count for s in cached)
        return {
            "sections": [
                {
                    "name": s.name,
                    "uid": s.uid,
                    "rulebase_range": s.rulebase_range,
                    "rule_count": s.rule_count,
                }
                for s in cached
            ],
            "total_rules": total_rules,
        }

    # Cache empty for this package - refresh it immediately and let the rest continue in background.
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_sections_for_package(
        session.username,
        session.password,
        mgmt_ip,
        domain_uid,
        pkg_uid,
    )

    cached = await cache_service.get_cached_sections(domain_uid, pkg_uid)
    total_rules = sum(s.rule_count for s in cached)
    return {
        "sections": [
            {
                "name": s.name,
                "uid": s.uid,
                "rulebase_range": s.rulebase_range,
                "rule_count": s.rule_count,
            }
            for s in cached
        ],
        "total_rules": total_rules,
    }
