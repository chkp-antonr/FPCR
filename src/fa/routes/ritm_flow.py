"""RITM Create & Verify flow endpoints."""

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from arlogi import get_logger
from cpaiops import CPAIOPSClient
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import settings
from ..db import engine
from ..models import (
    RITM,
    CachedSection,
    DomainEvidenceItem,
    EvidenceHistoryResponse,
    EvidenceResponse,
    EvidenceSessionItem,
    MatchObjectsRequest,
    MatchObjectsResponse,
    MatchResult,
    PackageEvidenceItem,
    PlanYamlResponse,
    Policy,
    PublishResponse,
    RITMCreatedRule,
    RITMEvidenceSession,
    RITMStatus,
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


_ATTEMPT_TYPE_LABELS: dict[str, str] = {
    "initial": "Initial",
    "correction": "Correction",
    "approval": "Approval",
}


def _group_rows_by_attempt(rows: Sequence[RITMEvidenceSession]) -> list[dict[str, Any]]:
    """Group evidence session rows by attempt number into attempt_data dicts."""
    bucket: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.attempt not in bucket:
            bucket[row.attempt] = {
                "attempt_num": row.attempt,
                "session_type": row.session_type,
                "session_changes": {"domain_changes": {}, "apply_session_trace": [], "errors": []},
            }
        att = bucket[row.attempt]
        sc: dict[str, Any] = {}
        if row.session_changes:
            try:
                sc = json.loads(row.session_changes)
            except Exception:
                pass
        dc = att["session_changes"]["domain_changes"]
        if row.domain_name not in dc:
            dc[row.domain_name] = {}
        dc[row.domain_name].update(sc)
        if row.session_uid:
            att["session_changes"]["apply_session_trace"].append(
                {
                    "domain": row.domain_name,
                    "attempt": row.attempt,
                    "session_uid": row.session_uid,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
            )

    result: list[dict[str, Any]] = []
    for attempt_num in sorted(bucket.keys()):
        att = bucket[attempt_num]
        stype = att["session_type"]
        label = _ATTEMPT_TYPE_LABELS.get(stype, stype.capitalize())
        result.append(
            {
                "attempt_num": attempt_num,
                "label": label,
                "session_changes": att["session_changes"],
            }
        )
    return result


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


@router.post("/ritm/{ritm_number}/submit-for-approval")
async def submit_for_approval(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> PublishResponse:
    """Disable enabled rules, publish session, then mark RITM as Ready for Approval.

    1. Disable rules from ritm_created_rules (they were created enabled during Try & Verify)
    2. Publish — commits disabled rules to Check Point
    3. Update RITM status to READY_FOR_APPROVAL
    """
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")
        if ritm.editor_locked_by != session.username:
            raise HTTPException(status_code=400, detail="You must hold the editor lock to submit for approval")

        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = list(policies_result.scalars().all())

        rules_result = await db.execute(
            select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
        )
        created_rules = list(rules_result.scalars().all())

    # Build per-package metadata from policies
    pkg_meta: dict[tuple[str, str], tuple[str, str]] = {}
    for policy in policies:
        pkg_meta[(policy.domain_uid, policy.package_uid)] = (policy.domain_name, policy.package_name)

    rules_by_pkg: dict[tuple[str, str], list[RITMCreatedRule]] = {}
    for rule in created_rules:
        rules_by_pkg.setdefault((rule.domain_uid, rule.package_uid), []).append(rule)

    errors: list[str] = []
    success_count = 0

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]

            for (domain_uid, package_uid), (domain_name, _package_name) in pkg_meta.items():
                pkg_rules = rules_by_pkg.get((domain_uid, package_uid), [])

                # Disable all rules created during Try & Verify
                for rule in pkg_rules:
                    result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=domain_name,
                        command="set-access-rule",
                        payload={"uid": rule.rule_uid, "enabled": False},
                    )
                    if not result.success:
                        errors.append(
                            f"Failed to disable rule {rule.rule_uid} in {domain_name}: "
                            f"{result.message or result.code}"
                        )

                # Publish with disabled rules
                pub_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="publish",
                    payload={},
                )
                if pub_result.success:
                    success_count += 1
                else:
                    errors.append(
                        f"Publish failed for {domain_name}: {pub_result.message or pub_result.code}"
                    )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in submit_for_approval for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if errors and success_count == 0:
        raise HTTPException(
            status_code=500,
            detail=f"Submit failed: {'; '.join(errors)}",
        )

    # Update RITM status to READY_FOR_APPROVAL
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one()
        ritm.status = RITMStatus.READY_FOR_APPROVAL
        ritm.date_updated = datetime.now(UTC)
        await db.commit()

    return PublishResponse(
        success=True,
        message=f"Rules disabled and published for RITM {ritm_number}. Ready for approval.",
        created=success_count,
        errors=errors,
    )



@router.post("/ritm/{ritm_number}/publish")
async def publish_ritm(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> PublishResponse:
    """Enable disabled rules, verify, capture approval evidence, and publish.

    Per domain/package:
    1. Enable disabled rules from ritm_created_rules
    2. Verify policy – on failure re-disable rules, continue
    3. Capture show-changes (approval evidence)
    4. Publish with rules enabled

    On all packages succeeding: status → COMPLETED
    """
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if ritm.status != RITMStatus.APPROVED:
            raise HTTPException(status_code=400, detail="RITM must be approved before publishing")

        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = list(policies_result.scalars().all())
        if not policies:
            raise HTTPException(status_code=400, detail="RITM has no policies to publish")

        rules_result = await db.execute(
            select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
        )
        created_rules = list(rules_result.scalars().all())

        # Compute approval attempt number
        attempt_result = await db.execute(
            select(func.max(RITMEvidenceSession.attempt)).where(
                col(RITMEvidenceSession.ritm_number) == ritm_number
            )
        )
        max_attempt = attempt_result.scalar_one_or_none()
        attempt = (max_attempt or 0) + 1

    # Build per-package rule lists
    rules_by_pkg: dict[tuple[str, str], list[RITMCreatedRule]] = {}
    for rule in created_rules:
        rules_by_pkg.setdefault((rule.domain_uid, rule.package_uid), []).append(rule)

    # Build domain/package name lookup from policies
    pkg_meta: dict[tuple[str, str], tuple[str, str]] = {}  # (domain_uid, pkg_uid) -> (domain_name, pkg_name)
    for policy in policies:
        pkg_meta[(policy.domain_uid, policy.package_uid)] = (policy.domain_name, policy.package_name)

    errors: list[str] = []
    success_count = 0

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]
            verifier = PolicyVerifier(client)

            for (domain_uid, package_uid), (domain_name, package_name) in pkg_meta.items():
                pkg_rules = rules_by_pkg.get((domain_uid, package_uid), [])
                enabled_uids: list[str] = []

                # 1. Enable disabled rules
                for rule in pkg_rules:
                    result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=domain_name,
                        command="set-access-rule",
                        payload={"uid": rule.rule_uid, "enabled": True},
                    )
                    if result.success:
                        enabled_uids.append(rule.rule_uid)
                    else:
                        errors.append(
                            f"Failed to enable rule {rule.rule_uid} in {domain_name}: "
                            f"{result.message or result.code}"
                        )

                # 2. Verify policy
                verify_result = await verifier.verify_policy(
                    domain_name=domain_name, package_name=package_name
                )
                if not verify_result.success:
                    for uid in enabled_uids:
                        await client.api_call(
                            mgmt_name=mgmt_name,
                            domain=domain_name,
                            command="set-access-rule",
                            payload={"uid": uid, "enabled": False},
                        )
                    errors.extend(verify_result.errors)
                    continue

                # 3. Capture show-changes for approval evidence
                session_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="show-session",
                    payload={},
                )
                session_uid: str | None = None
                if session_result.success and session_result.data:
                    session_uid = session_result.data.get("uid") or session_result.data.get("session-uid")

                sc_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="show-changes",
                    details_level="full",
                    payload={"to-session": session_uid} if session_uid else {},
                )
                session_changes = sc_result.data if sc_result.success and sc_result.data else {}

                # 4. Publish
                pub_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=domain_name,
                    command="publish",
                    payload={},
                )

                if pub_result.success:
                    success_count += 1
                    async with AsyncSession(engine) as db:
                        db.add(
                            RITMEvidenceSession(
                                ritm_number=ritm_number,
                                attempt=attempt,
                                domain_name=domain_name,
                                domain_uid=domain_uid,
                                package_name=package_name,
                                package_uid=package_uid,
                                session_uid=session_uid,
                                sid="",
                                session_type="approval",
                                session_changes=json.dumps(session_changes) if session_changes else None,
                                created_at=datetime.now(UTC),
                            )
                        )
                        await db.commit()
                else:
                    errors.append(
                        f"Publish failed for {domain_name}: {pub_result.message or pub_result.code}"
                    )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in publish_ritm for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if success_count == 0 and errors:
        raise HTTPException(
            status_code=500,
            detail=f"Publish failed for all packages: {'; '.join(errors)}",
        )

    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one()
        ritm.status = RITMStatus.COMPLETED
        await db.commit()

    return PublishResponse(
        success=True,
        message=f"Published {success_count} package(s) for RITM {ritm_number}",
        created=success_count,
        errors=errors,
    )


@router.post("/ritm/{ritm_number}/recreate-evidence")
async def recreate_evidence(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> EvidenceResponse:
    """Re-fetch show-changes for all stored sessions and update evidence in DB."""
    logger.info(f"Recreating evidence for RITM {ritm_number} by user {session.username}")

    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        sessions_result = await db.execute(
            select(RITMEvidenceSession).where(
                col(RITMEvidenceSession.ritm_number) == ritm_number
            )
        )
        evidence_rows = sessions_result.scalars().all()

    if not evidence_rows:
        raise HTTPException(
            status_code=400, detail="No session UIDs found for this RITM. Run Try & Verify first."
        )

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]

            async with AsyncSession(engine) as db:
                for row in evidence_rows:
                    if not row.session_uid:
                        continue

                    sc_result = await client.api_call(
                        mgmt_name=mgmt_name,
                        domain=row.domain_name,
                        command="show-changes",
                        details_level="full",
                        payload={"to-session": row.session_uid},
                    )

                    if sc_result.success and sc_result.data:
                        fresh = await db.get(RITMEvidenceSession, row.id)
                        if fresh:
                            fresh.session_changes = json.dumps(sc_result.data)
                    else:
                        logger.warning(
                            f"show-changes failed for {row.domain_name} session {row.session_uid}: "
                            f"{sc_result.message or sc_result.code}"
                        )

                await db.commit()

            # Build combined for response
            combined: dict[str, Any] = {"domain_changes": {}, "errors": []}
            async with AsyncSession(engine) as db:
                refreshed_result = await db.execute(
                    select(RITMEvidenceSession).where(
                        col(RITMEvidenceSession.ritm_number) == ritm_number
                    )
                )
                for row in refreshed_result.scalars().all():
                    sc: dict[str, Any] = {}
                    if row.session_changes:
                        try:
                            sc = json.loads(row.session_changes)
                        except Exception:
                            pass
                    if row.domain_name not in combined["domain_changes"]:
                        combined["domain_changes"][row.domain_name] = {}
                    combined["domain_changes"][row.domain_name].update(sc)

            pdf_generator = get_pdf_generator()
            html = pdf_generator.generate_html(
                ritm_number=ritm_number,
                evidence_number=1,
                username=session.username,
                session_changes=combined,
                section_uid_to_name={},
            )

            return EvidenceResponse(
                html=html,
                yaml="",
                changes=combined.get("domain_changes", {}),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in recreate_evidence for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ritm/{ritm_number}/evidence-history")
async def get_evidence_history(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> EvidenceHistoryResponse:
    """Return full cumulative evidence history grouped as Domain -> Package -> Sessions."""
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        evidence_result = await db.execute(
            select(RITMEvidenceSession)
            .where(col(RITMEvidenceSession.ritm_number) == ritm_number)
            .order_by(
                col(RITMEvidenceSession.domain_name).asc(),
                col(RITMEvidenceSession.package_name).asc(),
                col(RITMEvidenceSession.attempt).asc(),
            )
        )
        rows = evidence_result.scalars().all()

    # Build domain -> package -> sessions hierarchy
    domains_map: dict[str, dict[str, list[EvidenceSessionItem]]] = {}
    domain_uids: dict[str, str] = {}
    package_uids: dict[tuple[str, str], str] = {}

    for row in rows:
        if row.domain_name not in domains_map:
            domains_map[row.domain_name] = {}
            domain_uids[row.domain_name] = row.domain_uid

        if row.package_name not in domains_map[row.domain_name]:
            domains_map[row.domain_name][row.package_name] = []
            package_uids[(row.domain_name, row.package_name)] = row.package_uid

        sc: dict | None = None
        if row.session_changes:
            try:
                sc = json.loads(row.session_changes)
            except Exception:
                pass

        domains_map[row.domain_name][row.package_name].append(
            EvidenceSessionItem(
                id=row.id or 0,
                attempt=row.attempt,
                session_type=row.session_type,
                session_uid=row.session_uid,
                sid=row.sid,
                created_at=row.created_at.isoformat() if row.created_at else "",
                session_changes=sc,
            )
        )

    domains = [
        DomainEvidenceItem(
            domain_name=domain_name,
            domain_uid=domain_uids[domain_name],
            packages=[
                PackageEvidenceItem(
                    package_name=package_name,
                    package_uid=package_uids[(domain_name, package_name)],
                    sessions=sessions,
                )
                for package_name, sessions in packages_map.items()
            ],
        )
        for domain_name, packages_map in domains_map.items()
    ]

    return EvidenceHistoryResponse(domains=domains)


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
    attempt: int | None = None,
    session: SessionData = Depends(get_session_data),
) -> Response:
    """Generate PDF evidence. Without attempt: all sessions. With attempt: that attempt only."""
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        query = select(RITMEvidenceSession).where(
            col(RITMEvidenceSession.ritm_number) == ritm_number
        )
        if attempt is not None:
            query = query.where(col(RITMEvidenceSession.attempt) == attempt)
        query = query.order_by(
            col(RITMEvidenceSession.domain_name).asc(),
            col(RITMEvidenceSession.attempt).asc(),
        )
        rows_result = await db.execute(query)
        rows = rows_result.scalars().all()

    if not rows:
        raise HTTPException(status_code=400, detail="No evidence sessions found for this RITM")

    attempt_data = _group_rows_by_attempt(rows)

    try:
        pdf_generator = get_pdf_generator()
        pdf_bytes = pdf_generator.generate_pdf_multi_attempt(
            ritm_number=ritm_number,
            username=session.username,
            attempt_data=attempt_data,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{ritm_number}_evidence.pdf"'
            },
        )
    except Exception as e:
        logger.error(f"PDF generation failed for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}") from e


@router.get("/ritm/{ritm_number}/session-html")
async def get_session_html(
    ritm_number: str,
    attempt: int | None = None,
    session: SessionData = Depends(get_session_data),
) -> HTMLResponse:
    """Render HTML evidence. Without attempt: all sessions. With attempt: that attempt only."""
    async with AsyncSession(engine) as db:
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        if not ritm_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="RITM not found")

        query = select(RITMEvidenceSession).where(
            col(RITMEvidenceSession.ritm_number) == ritm_number
        )
        if attempt is not None:
            query = query.where(col(RITMEvidenceSession.attempt) == attempt)
        query = query.order_by(
            col(RITMEvidenceSession.domain_name).asc(),
            col(RITMEvidenceSession.attempt).asc(),
        )
        rows_result = await db.execute(query)
        rows = rows_result.scalars().all()

    if not rows:
        raise HTTPException(status_code=400, detail="No evidence sessions found for this RITM")

    attempt_data = _group_rows_by_attempt(rows)

    try:
        pdf_generator = get_pdf_generator()
        html = pdf_generator.generate_html_multi_attempt(
            ritm_number=ritm_number,
            username=session.username,
            attempt_data=attempt_data,
        )
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error(f"HTML evidence generation failed for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"HTML evidence generation failed: {e}") from e
