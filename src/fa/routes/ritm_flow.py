"""RITM Create & Verify flow endpoints."""

import json
import re
from collections.abc import Sequence
from typing import Any

from arlogi import get_logger
from cpaiops import CPAIOPSClient
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import settings
from ..db import engine
from ..models import (
    CachedSection,
    EvidenceResponse,
    MatchObjectsRequest,
    MatchObjectsResponse,
    MatchResult,
    PlanYamlResponse,
    RITMVerification,
    TryVerifyResponse,
)
from ..services.evidence_generator import EvidenceGenerator
from ..services.initials_loader import InitialsLoader
from ..services.object_matcher import ObjectMatcher
from ..services.policy_verifier import PolicyVerifier
from ..services.ritm_workflow_service import RITMWorkflowService
from ..services.session_changes_pdf import SessionChangesPDFGenerator
from ..session import SessionData, session_manager

logger = get_logger(__name__)

router = APIRouter(tags=["ritm-flow"])


async def get_session_data(request: Request) -> SessionData:
    """Dependency to get current session."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


# Service singletons
_initials_loader: InitialsLoader | None = None
_evidence_generator: EvidenceGenerator | None = None
_pdf_generator: SessionChangesPDFGenerator | None = None


def get_initials_loader() -> InitialsLoader:
    """Get or create InitialsLoader singleton."""
    global _initials_loader
    if _initials_loader is None:
        _initials_loader = InitialsLoader(settings.initials_csv_path)
    return _initials_loader


def get_evidence_generator() -> EvidenceGenerator:
    """Get or create EvidenceGenerator singleton."""
    global _evidence_generator
    if _evidence_generator is None:
        _evidence_generator = EvidenceGenerator(settings.evidence_template_dir)
    return _evidence_generator


def get_pdf_generator() -> SessionChangesPDFGenerator:
    """Get or create SessionChangesPDFGenerator singleton."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = SessionChangesPDFGenerator()
    return _pdf_generator


def _as_list(raw: object) -> list[str]:
    """Decode a DB field that may be a list or a JSON-encoded string."""
    if isinstance(raw, list):
        return [str(v) for v in raw]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            return [raw]
    return []


def _build_plan_yaml_from_policies(policies: Sequence[Any]) -> tuple[str, dict[str, int]]:
    """Build plan-only CPCRUD YAML from persisted policies."""
    ipv4_re = re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
    )
    cidr_re = re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)/(\d|[12]\d|3[0-2])$"
    )
    range_re = re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\s*-\s*"
        r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
    )

    def quote(value: str) -> str:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    def indent(level: int, text: str) -> str:
        return f"{'  ' * level}{text}"

    object_ops: list[str] = []
    rule_ops: list[str] = []
    seen_object_keys: set[str] = set()

    def add_object_plan(domain_name: str, value: str) -> None:
        trimmed = value.strip()
        if not trimmed or trimmed.lower() == "any":
            return

        if ipv4_re.match(trimmed):
            name = f"Host_{trimmed}"
            key = f"{domain_name}|host|{name}"
            if key in seen_object_keys:
                return
            seen_object_keys.add(key)
            object_ops.extend(
                [
                    indent(2, "- operation: add"),
                    indent(3, "type: host"),
                    indent(3, f"domain: {quote(domain_name)}"),
                    indent(3, "data:"),
                    indent(4, f"name: {quote(name)}"),
                    indent(4, f"ip-address: {quote(trimmed)}"),
                ]
            )
            return

        cidr_match = cidr_re.match(trimmed)
        if cidr_match:
            subnet, mask = trimmed.split("/")
            name = f"Net_{subnet}_{mask}"
            key = f"{domain_name}|network|{name}"
            if key in seen_object_keys:
                return
            seen_object_keys.add(key)
            object_ops.extend(
                [
                    indent(2, "- operation: add"),
                    indent(3, "type: network"),
                    indent(3, f"domain: {quote(domain_name)}"),
                    indent(3, "data:"),
                    indent(4, f"name: {quote(name)}"),
                    indent(4, f"subnet: {quote(subnet)}"),
                    indent(4, f"mask-length: {mask}"),
                ]
            )
            return

        if range_re.match(trimmed):
            first, last = [part.strip() for part in trimmed.split("-")]
            name = f"IPR_{first.replace('.', '_')}_{last.replace('.', '_')}"
            key = f"{domain_name}|address-range|{name}"
            if key in seen_object_keys:
                return
            seen_object_keys.add(key)
            object_ops.extend(
                [
                    indent(2, "- operation: add"),
                    indent(3, "type: address-range"),
                    indent(3, f"domain: {quote(domain_name)}"),
                    indent(3, "data:"),
                    indent(4, f"name: {quote(name)}"),
                    indent(4, f"ipv4-address-first: {quote(first)}"),
                    indent(4, f"ipv4-address-last: {quote(last)}"),
                ]
            )

    for policy in policies:
        domain_name = getattr(policy, "domain_name", "")
        package_name = getattr(policy, "package_name", "")

        source_values = [
            v.strip() for v in _as_list(getattr(policy, "source_ips", [])) if v.strip()
        ]
        dest_values = [v.strip() for v in _as_list(getattr(policy, "dest_ips", [])) if v.strip()]
        service_values = [v.strip() for v in _as_list(getattr(policy, "services", [])) if v.strip()]

        for value in source_values:
            add_object_plan(domain_name, value)
        for value in dest_values:
            add_object_plan(domain_name, value)

        rule_name = getattr(policy, "rule_name", "")
        comments = getattr(policy, "comments", "")
        action = getattr(policy, "action", "accept")
        track = getattr(policy, "track", "log")
        section_name = getattr(policy, "section_name", None)
        position_type = getattr(policy, "position_type", "bottom")
        position_number = getattr(policy, "position_number", None)

        rule_ops.extend(
            [
                indent(2, "- operation: add"),
                indent(3, "type: access-rule"),
                indent(3, f"domain: {quote(domain_name)}"),
                indent(3, f"package: {quote(package_name)}"),
            ]
        )
        if section_name:
            rule_ops.append(indent(3, f"section: {quote(section_name)}"))
        if position_type == "custom" and position_number is not None:
            rule_ops.append(indent(3, f"position: {position_number}"))
        else:
            rule_ops.append(indent(3, f"position: {quote(position_type)}"))

        rule_ops.extend(
            [
                indent(3, "data:"),
                indent(4, f"name: {quote(rule_name)}"),
                indent(4, f"comments: {quote(comments)}"),
                indent(4, "source:"),
            ]
        )
        for value in source_values:
            rule_ops.append(indent(5, f"- {quote(value)}"))

        rule_ops.append(indent(4, "destination:"))
        for value in dest_values:
            rule_ops.append(indent(5, f"- {quote(value)}"))

        rule_ops.append(indent(4, "service:"))
        if service_values:
            for value in service_values:
                rule_ops.append(indent(5, f"- {quote(value)}"))
        else:
            rule_ops.append(indent(5, "- 'any'"))

        rule_ops.extend(
            [
                indent(4, f"action: {quote(action)}"),
                indent(4, f"track: {quote(track)}"),
            ]
        )

    lines = ["planned_operations:"]
    if not object_ops and not rule_ops:
        lines.append(indent(1, "[]"))
    else:
        lines.extend(object_ops)
        lines.extend(rule_ops)

    return "\n".join(lines), {
        "planned_objects": len(seen_object_keys),
        "planned_rules": len(policies),
    }


@router.post("/ritm/{ritm_number}/plan-yaml")
async def plan_yaml(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> PlanYamlResponse:
    """Generate plan-only CPCRUD YAML from stored RITM policies."""
    async with AsyncSession(engine) as db:
        from sqlalchemy import select

        from ..models import RITM, Policy

        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        policy_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = policy_result.scalars().all()

    if not policies:
        raise HTTPException(status_code=400, detail="No policies found for RITM")

    yaml, changes = _build_plan_yaml_from_policies(policies)
    return PlanYamlResponse(yaml=yaml, changes=changes)


@router.post("/ritm/{ritm_number}/try-verify")
async def try_verify_ritm(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> TryVerifyResponse:
    """Execute Try & Verify workflow with automatic rollback and disable.

    Workflow for each package:
    1. Verify policy (pre-check) - skip package on failure
    2. Create objects and rules - skip package on failure
    3. Verify policy again (post-creation)
    4. On verify failure: rollback rules, continue
    5. On verify success: capture evidence, disable rules

    After all packages:
    - Combine evidence into single PDF/HTML
    - Store session UIDs for evidence re-creation
    - Publish if any packages succeeded
    """
    async with AsyncSession(engine) as db:
        from ..models import RITM

        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            workflow = RITMWorkflowService(
                client=client,
                ritm_number=ritm_number,
                username=session.username,
            )
            result = await workflow.try_verify()
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in try_verify for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ritm/{ritm_number}/recreate-evidence")
async def recreate_evidence(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> EvidenceResponse:
    """Re-generate evidence from stored session UIDs.

    Fetches fresh show-changes from Check Point to capture any manual changes
    made after the original Try & Verify.
    """
    from ..models import RITM, RITMSession

    logger.info(f"Recreating evidence for RITM {ritm_number} by user {session.username}")

    # Use single database session throughout
    async with AsyncSession(engine) as db:
        # Get RITM
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Get stored session UIDs for this RITM
        sessions_result = await db.execute(
            select(RITMSession).where(col(RITMSession.ritm_number) == ritm_number)
        )
        ritm_sessions = sessions_result.scalars().all()

        if not ritm_sessions:
            raise HTTPException(
                status_code=400,
                detail="No session UIDs found for this RITM. Run Try & Verify first.",
            )

        logger.info(f"Found {len(ritm_sessions)} sessions for RITM {ritm_number}")

        try:
            async with CPAIOPSClient(
                engine=engine,
                username=session.username,
                password=session.password,
                mgmt_ip=settings.api_mgmt,
            ) as client:
                mgmt_name = client.get_mgmt_names()[0]
                pdf_generator = SessionChangesPDFGenerator()

                # Combine fresh show-changes from all stored sessions
                combined_session_changes: dict[str, Any] = {
                    "apply_sessions": {},
                    "apply_session_trace": [],
                    "domain_changes": {},
                    "show_changes_requests": {},
                    "errors": [],
                }

                # Track valid sessions for apply_session_trace
                valid_sessions_count = 0

                for ritm_session in ritm_sessions:
                    # Skip sessions without session_uid
                    if not ritm_session.session_uid:
                        logger.warning(
                            f"Skipping session for domain {ritm_session.domain_name}: no session_uid"
                        )
                        continue

                    valid_sessions_count += 1

                    # Build apply_session_trace entry
                    combined_session_changes["apply_session_trace"].append(
                        {
                            "domain": ritm_session.domain_name,
                            "domain_uid": ritm_session.domain_uid,
                            "session_uid": ritm_session.session_uid,
                            "sid": ritm_session.sid,
                        }
                    )

                    # Call show-changes with stored session UID
                    sc_payload: dict[str, Any] = {"to-session": ritm_session.session_uid}

                    sc_result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=ritm_session.domain_name,
                        command="show-changes",
                        details_level="full",
                        payload=sc_payload,
                    )

                    if sc_result.success and sc_result.data:
                        domain_data = sc_result.data
                        combined_session_changes["domain_changes"].update(
                            domain_data.get("domain_changes", {})
                        )
                        combined_session_changes["apply_sessions"].update(
                            domain_data.get("apply_sessions", {})
                        )
                    else:
                        logger.warning(
                            f"show-changes failed for domain {ritm_session.domain_name}: "
                            f"{sc_result.message or sc_result.code or 'unknown error'}"
                        )
                        combined_session_changes["errors"].append(
                            f"show-changes failed for domain {ritm_session.domain_name}: "
                            f"{sc_result.message or sc_result.code or 'unknown error'}"
                        )

                logger.info(
                    f"Processed {valid_sessions_count} valid sessions for RITM {ritm_number}"
                )

                # Build UID-to-name mapping for both sections and access layers
                section_uid_to_name: dict[str, str] = {}

                # 1. Fetch cached sections
                sections_result = await db.execute(select(CachedSection))
                sections = sections_result.scalars().all()
                logger.debug(f"Loaded {len(sections)} cached sections from database")
                for s in sections:
                    section_uid_to_name[s.uid] = s.name

                # 2. Fetch access layers for each domain in the sessions
                # Access layers are different from sections - rules reference layer UIDs directly
                for ritm_session in ritm_sessions:
                    domain_name = ritm_session.domain_name
                    layers_result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=domain_name,
                        command="show-access-layers",
                        payload={},
                    )
                    if layers_result.success and layers_result.data:
                        for layer in layers_result.data.get("access-layers", []):
                            layer_uid = layer.get("uid")
                            layer_name = layer.get("name")
                            if layer_uid and layer_name:
                                section_uid_to_name[layer_uid] = layer_name
                    else:
                        logger.warning(
                            f"Failed to fetch layers for {domain_name}: {layers_result.message or layers_result.code}"
                        )

                logger.debug(
                    f"Built UID-to-name mapping: {len(section_uid_to_name)} entries (sections + layers)"
                )

                # Generate HTML
                html = pdf_generator.generate_html(
                    ritm_number=ritm_number,
                    evidence_number=1,
                    username=session.username,
                    session_changes=combined_session_changes,
                    section_uid_to_name=section_uid_to_name,
                )

                # Check if we got meaningful changes (session wasn't published)
                has_changes = any(
                    dc.get("tasks", []) and dc["tasks"][0].get("task-details", [])
                    for dc in combined_session_changes.get("domain_changes", {}).values()
                )

                if not has_changes and ritm.session_changes_evidence1:
                    # Session was published, show-changes returns empty - use original evidence
                    logger.info(
                        f"Session for RITM {ritm_number} was published, using original evidence"
                    )
                    try:
                        original_evidence = json.loads(ritm.session_changes_evidence1)
                        html = pdf_generator.generate_html(
                            ritm_number=ritm_number,
                            evidence_number=1,
                            username=session.username,
                            session_changes=original_evidence,
                            section_uid_to_name=section_uid_to_name,
                        )
                        return EvidenceResponse(
                            html=html,
                            yaml="",
                            changes=original_evidence.get("domain_changes", {}),
                        )
                    except json.JSONDecodeError:
                        logger.warning(
                            "Failed to parse original evidence, returning empty evidence"
                        )

                # Update stored evidence using the same db session
                ritm.session_changes_evidence1 = json.dumps(combined_session_changes)
                await db.commit()

                logger.info(f"Successfully recreated evidence for RITM {ritm_number}")

                return EvidenceResponse(
                    html=html,
                    yaml="",  # Not applicable for re-created evidence
                    changes=combined_session_changes.get("domain_changes", {}),
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in recreate_evidence for RITM {ritm_number}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e


# DEPRECATED: Use /try-verify instead
# @router.post("/ritm/{ritm_number}/apply")
# async def apply_ritm(
#     ritm_number: str,
#     session: SessionData = Depends(get_session_data),
# ) -> ApplyResponse:
#     """Create objects and access rules for all RITM policies."""
#     ...


# DEPRECATED: Verification now internal to /try-verify
# @router.post("/ritm/{ritm_number}/verify")
# async def verify_ritm(
#     ritm_number: str,
#     session: SessionData = Depends(get_session_data),
# ) -> VerifyResponse:
#     """Verify policy for every unique domain/package combo in this RITM."""
#     ...


@router.post("/ritm/{ritm_number}/match-objects")
async def match_objects(
    ritm_number: str,
    request: MatchObjectsRequest,
    session: SessionData = Depends(get_session_data),
) -> MatchObjectsResponse:
    """Match or create objects for IPs and services.

    Args:
        ritm_number: RITM number
        request: Match request with source/dest/services
        session: Current session

    Returns:
        Matched/created objects
    """
    try:
        logger.debug(
            "match_objects request: ritm='%s' user='%s' domain_uid='%s' source_count=%s dest_count=%s svc_count=%s",
            ritm_number,
            session.username,
            request.domain_uid,
            len(request.source_ips),
            len(request.dest_ips),
            len(request.services),
        )
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            # Get domain info from cache
            mgmt_name = client.get_mgmt_names()[0]
            domains = await client.get_domains(mgmt_names=[mgmt_name])

            # Find domain by UID
            domain_name = None
            for domain in domains:
                if domain.uid == request.domain_uid:
                    domain_name = domain.name
                    break

            logger.debug(
                "Resolved domain for match_objects: domain_uid='%s' domain_name='%s' domains_cached=%s",
                request.domain_uid,
                domain_name,
                len(domains),
            )

            # Fallback to system domain if not found
            if not domain_name:
                domain_name = ""  # Empty string for system domain
                logger.warning(
                    f"Domain UID {request.domain_uid} not found in cache, using system domain"
                )

            matcher = ObjectMatcher(client)

            # Match source IPs
            source_results = await matcher.match_and_create_objects(
                inputs=request.source_ips,
                domain_uid=request.domain_uid,
                domain_name=domain_name,
                create_missing=settings.object_create_missing,
            )

            # Match dest IPs
            dest_results = await matcher.match_and_create_objects(
                inputs=request.dest_ips,
                domain_uid=request.domain_uid,
                domain_name=domain_name,
                create_missing=settings.object_create_missing,
            )

            # Match services (simplified - services are pre-defined)
            services_results = [
                MatchResult(
                    input=svc,
                    object_uid=svc,
                    object_name=svc,
                    object_type="service",
                    created=False,
                    matches_convention=True,
                    usage_count=None,
                )
                for svc in request.services
            ]

            created_count = sum(1 for r in source_results if r["created"]) + sum(
                1 for r in dest_results if r["created"]
            )

            logger.debug(
                "match_objects result: ritm='%s' created_count=%s source_results=%s dest_results=%s",
                ritm_number,
                created_count,
                source_results,
                dest_results,
            )

            return MatchObjectsResponse(
                source=[MatchResult(**r) for r in source_results],
                dest=[MatchResult(**r) for r in dest_results],
                services=services_results,
                created_count=created_count,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in match_objects for RITM {ritm_number}: {e}", exc_info=True)
        logger.debug("match_objects exception detail repr: %r", e)
        # Check for read-only mode error
        if "read only mode" in str(e).lower():
            raise HTTPException(
                status_code=500,
                detail="Check Point API is in read-only mode. Cannot create objects or rules. Please ensure the API account has write permissions.",
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ritm/{ritm_number}/verify-policy")
async def verify_policy(
    ritm_number: str,
    domain_uid: str,
    package_uid: str,
    session: SessionData = Depends(get_session_data),
) -> dict[str, object]:
    """Verify policy before creating rules.

    Args:
        ritm_number: RITM number
        domain_uid: Domain UID
        package_uid: Package UID
        session: Current session

    Returns:
        Verification result
    """
    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            # Get domain info from cache
            mgmt_name = client.get_mgmt_names()[0]
            domains = await client.get_domains(mgmt_names=[mgmt_name])

            # Find domain by UID
            domain_name = None
            for domain in domains:
                if domain.uid == domain_uid:
                    domain_name = domain.name
                    break

            # Fallback to system domain if not found
            if not domain_name:
                domain_name = ""  # Empty string for system domain
                logger.warning(f"Domain UID {domain_uid} not found in cache, using system domain")

            # TODO: Lookup package name from cache
            package_name = package_uid

            verifier = PolicyVerifier(client)
            result = await verifier.verify_policy(
                domain_name=domain_name, package_name=package_name
            )

            return {"verified": result.success, "errors": result.errors}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in verify_policy for RITM {ritm_number}: {e}", exc_info=True)
        # Check for read-only mode error
        if "read only mode" in str(e).lower():
            raise HTTPException(
                status_code=500,
                detail="Check Point API is in read-only mode. Cannot create objects or rules. Please ensure the API account has write permissions.",
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ritm/debug/show-changes")
async def debug_show_changes(
    domain_uid: str,
    session: SessionData = Depends(get_session_data),
) -> dict[str, Any]:
    """Debug endpoint to check what show-changes returns.

    Args:
        domain_uid: Domain UID to check changes for
        session: Current session

    Returns:
        Raw show-changes API response
    """
    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            # Get domain info from cache
            mgmt_name = client.get_mgmt_names()[0]
            domains = await client.get_domains(mgmt_names=[mgmt_name])

            # Find domain by UID
            domain_name = None
            for domain in domains:
                if domain.uid == domain_uid:
                    domain_name = domain.name
                    break

            if not domain_name:
                domain_name = ""

            # Get current session UID via show-session
            session_result = await client.api_call(
                mgmt_name=mgmt_name,
                domain=domain_name,
                command="show-session",
                payload={},
            )

            current_session_uid = None
            if session_result.success and session_result.data:
                current_session_uid = session_result.data.get("uid") or session_result.data.get(
                    "session-uid"
                )

            # Call show-changes WITHOUT to-session
            sc_result_all = await client.api_call(
                mgmt_name=mgmt_name,
                domain=domain_name,
                command="show-changes",
                details_level="full",
                payload={},
            )

            # Call show-changes WITH to-session
            sc_result_session = None
            if current_session_uid:
                sc_result_session = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="show-changes",
                    details_level="full",
                    payload={"to-session": current_session_uid},
                )

            return {
                "domain_name": domain_name,
                "domain_uid": domain_uid,
                "current_session_uid": current_session_uid,
                "show_changes_all": {
                    "success": sc_result_all.success,
                    "data": sc_result_all.data,
                    "message": sc_result_all.message,
                },
                "show_changes_to_session": {
                    "success": sc_result_session.success if sc_result_session else None,
                    "data": sc_result_session.data if sc_result_session else None,
                    "message": sc_result_session.message if sc_result_session else None,
                }
                if sc_result_session
                else None,
            }
    except Exception as e:
        logger.error(f"Error in debug_show_changes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ritm/{ritm_number}/generate-evidence")
async def generate_evidence(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> EvidenceResponse:
    """Generate evidence artifacts for RITM.

    Args:
        ritm_number: RITM number
        session: Current session

    Returns:
        HTML, YAML, and changes data
    """
    try:
        async with AsyncSession(engine) as db:
            from sqlalchemy import select

            from ..models import RITM, RITMCreatedObject, RITMCreatedRule

            # Get RITM data
            ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
            ritm = ritm_result.scalar_one_or_none()

            if not ritm:
                raise HTTPException(status_code=404, detail="RITM not found")

            # Get created objects
            objects_result = await db.execute(
                select(RITMCreatedObject).where(col(RITMCreatedObject.ritm_number) == ritm_number)
            )
            created_objects = objects_result.scalars().all()

            # Get created rules
            rules_result = await db.execute(
                select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
            )
            created_rules = rules_result.scalars().all()

            # Get verification results
            verification_result = await db.execute(
                select(RITMVerification).where(col(RITMVerification.ritm_number) == ritm_number)
            )
            verifications = verification_result.scalars().all()

        # Get initials
        initials_loader = get_initials_loader()
        initials = initials_loader.get_initials(session.username)

        # Build changes_by_domain from created objects and rules
        changes_by_domain: list[dict[str, Any]] = []
        errors_list: list[str] = []

        for verif in verifications:
            if verif.errors:
                import json

                errors_list.extend(json.loads(verif.errors) if verif.errors else [])

        # Convert created objects to dict format
        created_objects_dict = [
            {
                "object_type": obj.object_type,
                "object_name": obj.object_name,
                "object_uid": obj.object_uid,
                "domain_uid": obj.domain_uid,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
            }
            for obj in created_objects
        ]

        # Convert created rules to dict format
        created_rules_dict = [
            {
                "rule_uid": rule.rule_uid,
                "rule_number": rule.rule_number,
                "package_uid": rule.package_uid,
                "domain_uid": rule.domain_uid,
                "verification_status": rule.verification_status,
                "disabled": rule.disabled,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
            }
            for rule in created_rules
        ]

        # Generate HTML
        evidence_generator = get_evidence_generator()
        html = evidence_generator.generate_html(
            ritm_number=ritm_number,
            created_at=ritm.date_created,
            engineer=session.username,
            initials=initials,
            changes_by_domain=changes_by_domain,
            errors=errors_list if errors_list else None,
        )

        # Get management server info
        mgmt_name = settings.api_mgmt  # Use IP as mgmt_name for now

        # Get domain name from first created object or from rule
        domain_name = "Global"
        domain_uid = None

        # Try to get domain from created objects first
        if created_objects_dict:
            domain_uid = created_objects_dict[0].get("domain_uid")
            logger.debug(f"Found domain_uid from created objects: {domain_uid}")

        # If no created objects, try to get from policies
        if not domain_uid:
            async with AsyncSession(engine) as db:
                from sqlalchemy import select

                from ..models import Policy

                policy_result = await db.execute(
                    select(Policy).where(col(Policy.ritm_number) == ritm_number).limit(1)
                )
                first_policy = policy_result.scalar_one_or_none()
                if first_policy:
                    domain_uid = first_policy.domain_uid
                    domain_name = first_policy.domain_name
                    logger.debug(f"Found domain from policy: {domain_name} ({domain_uid})")

        # Lookup domain name from cache if we have domain_uid
        if domain_uid and not created_objects_dict:
            try:
                async with CPAIOPSClient(
                    engine=engine,
                    username=session.username,
                    password=session.password,
                    mgmt_ip=settings.api_mgmt,
                ) as client:
                    mgmt = client.get_mgmt_names()[0]
                    domains = await client.get_domains(mgmt_names=[mgmt])
                    for domain in domains:
                        if domain.uid == domain_uid:
                            domain_name = domain.name
                            logger.debug(f"Resolved domain name from cache: {domain_name}")
                            break
            except Exception as e:
                logger.warning(f"Failed to lookup domain name from cache: {e}")

        logger.debug(f"Using domain_name: {domain_name} for evidence generation")

        # Generate YAML
        yaml_str = evidence_generator.generate_yaml(
            mgmt_name=mgmt_name,
            domain_name=domain_name,
            created_objects=created_objects_dict,
            created_rules=created_rules_dict,
        )

        return EvidenceResponse(
            html=html,
            yaml=yaml_str,
            changes={
                "created_objects": created_objects_dict,
                "created_rules": created_rules_dict,
                "errors": errors_list,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_evidence for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ritm/{ritm_number}/export-errors")
async def export_errors(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> PlainTextResponse:
    """Export errors as text file.

    Args:
        ritm_number: RITM number
        _session: Current session

    Returns:
        Plain text error log
    """
    async with AsyncSession(engine) as db:
        from sqlalchemy import select

        from ..models import RITM, RITMVerification

        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()

        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Get verification results
        verification_result = await db.execute(
            select(RITMVerification).where(col(RITMVerification.ritm_number) == ritm_number)
        )
        verifications = verification_result.scalars().all()

    # Build error text
    lines = [
        f"RITM: {ritm_number}",
        f"Date: {ritm.date_created.isoformat() if ritm.date_created else 'N/A'}",
        f"Engineer: {ritm.username_created}",
        "",
    ]

    for verif in verifications:
        if verif.errors:
            import json

            errors = json.loads(verif.errors) if verif.errors else []

            lines.extend(
                [
                    f"=== Package: {verif.package_uid} ===",
                    f"Domain: {verif.domain_uid}",
                    f"Verified: {'FAILED' if not verif.verified else 'PASSED'}",
                    "",
                ]
            )

            if errors:
                lines.append("Errors:")
                for error in errors:
                    lines.append(f"  - {error}")
                lines.append("")

    return PlainTextResponse(
        content="\n".join(lines),
        headers={"Content-Disposition": f"attachment; filename={ritm_number}_errors.txt"},
    )


@router.get("/ritm/{ritm_number}/session-pdf")
async def get_session_pdf(
    ritm_number: str,
    evidence: int = 1,
    session: SessionData = Depends(get_session_data),
) -> Response:
    """Generate PDF from stored session changes.

    Args:
        ritm_number: RITM number
        evidence: Evidence number (1 or 2)
        session: Current session

    Returns:
        PDF file
    """
    from sqlalchemy import select

    from ..models import RITM

    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(
            select(RITM).where(RITM.ritm_number == ritm_number)  # type: ignore[arg-type]
        )
        ritm = ritm_result.scalar_one_or_none()

        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Get the appropriate evidence column
        if evidence == 1:
            session_changes_json = ritm.session_changes_evidence1
        elif evidence == 2:
            session_changes_json = ritm.session_changes_evidence2
        else:
            raise HTTPException(status_code=400, detail="Evidence number must be 1 or 2")

        if not session_changes_json:
            raise HTTPException(
                status_code=400,
                detail=f"Evidence #{evidence} not available for this RITM",
            )

        try:
            session_changes = json.loads(session_changes_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse session_changes JSON for RITM {ritm_number}: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to parse session changes data"
            ) from e

    # Generate PDF
    try:
        pdf_generator = get_pdf_generator()

        # Build UID-to-name mapping for section name resolution
        section_uid_to_name: dict[str, str] = {}

        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]

            async with AsyncSession(engine) as db:
                # Fetch cached sections
                sections_result = await db.execute(select(CachedSection))
                sections = sections_result.scalars().all()
                for s in sections:
                    section_uid_to_name[s.uid] = s.name

                # Fetch RITM sessions to determine which domains to query
                from ..models import RITMSession

                sessions_result = await db.execute(
                    select(RITMSession).where(col(RITMSession.ritm_number) == ritm_number)
                )
                ritm_sessions = sessions_result.scalars().all()

                # Fetch access layers for each domain in the sessions
                for ritm_session in ritm_sessions:
                    domain_name = ritm_session.domain_name
                    layers_result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=domain_name,
                        command="show-access-layers",
                        payload={},
                    )
                    if layers_result.success and layers_result.data:
                        for layer in layers_result.data.get("access-layers", []):
                            layer_uid = layer.get("uid")
                            layer_name = layer.get("name")
                            if layer_uid and layer_name:
                                section_uid_to_name[layer_uid] = layer_name

        pdf_bytes = pdf_generator.generate_pdf(
            ritm_number=ritm_number,
            evidence_number=evidence,
            username=session.username,
            session_changes=session_changes,
            section_uid_to_name=section_uid_to_name,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{ritm_number}_evidence{evidence}.pdf"'
            },
        )
    except Exception as e:
        logger.error(f"PDF generation failed for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}") from e


@router.get("/ritm/{ritm_number}/session-html")
async def get_session_html(
    ritm_number: str,
    evidence: int = 1,
    session: SessionData = Depends(get_session_data),
) -> HTMLResponse:
    """Render HTML evidence from stored session changes.

    Args:
        ritm_number: RITM number
        evidence: Evidence number (1 or 2)
        session: Current session

    Returns:
        Rendered HTML
    """
    from sqlalchemy import select

    from ..models import RITM

    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(
            select(RITM).where(RITM.ritm_number == ritm_number)  # type: ignore[arg-type]
        )
        ritm = ritm_result.scalar_one_or_none()

        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if evidence == 1:
            session_changes_json = ritm.session_changes_evidence1
        elif evidence == 2:
            session_changes_json = ritm.session_changes_evidence2
        else:
            raise HTTPException(status_code=400, detail="Evidence number must be 1 or 2")

        if not session_changes_json:
            raise HTTPException(
                status_code=400,
                detail=f"Evidence #{evidence} not available for this RITM",
            )

        try:
            session_changes = json.loads(session_changes_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse session_changes JSON for RITM {ritm_number}: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to parse session changes data"
            ) from e

    try:
        pdf_generator = get_pdf_generator()

        # Build UID-to-name mapping for section name resolution
        section_uid_to_name: dict[str, str] = {}

        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]

            async with AsyncSession(engine) as db:
                # Fetch cached sections
                sections_result = await db.execute(select(CachedSection))
                sections = sections_result.scalars().all()
                for s in sections:
                    section_uid_to_name[s.uid] = s.name

                # Fetch RITM sessions to determine which domains to query
                from ..models import RITMSession

                sessions_result = await db.execute(
                    select(RITMSession).where(col(RITMSession.ritm_number) == ritm_number)
                )
                ritm_sessions = sessions_result.scalars().all()

                # Fetch access layers for each domain in the sessions
                for ritm_session in ritm_sessions:
                    domain_name = ritm_session.domain_name
                    layers_result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=domain_name,
                        command="show-access-layers",
                        payload={},
                    )
                    if layers_result.success and layers_result.data:
                        for layer in layers_result.data.get("access-layers", []):
                            layer_uid = layer.get("uid")
                            layer_name = layer.get("name")
                            if layer_uid and layer_name:
                                section_uid_to_name[layer_uid] = layer_name

        html = pdf_generator.generate_html(
            ritm_number=ritm_number,
            evidence_number=evidence,
            username=session.username,
            session_changes=session_changes,
            section_uid_to_name=section_uid_to_name,
        )
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error(f"HTML evidence generation failed for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"HTML evidence generation failed: {e}") from e
