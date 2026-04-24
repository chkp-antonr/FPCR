"""RITM (Requested Item) approval workflow endpoints."""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import settings
from ..db import engine
from ..models import (
    RITM,
    Policy,
    PolicyItem,
    PublishResponse,
    RITMCreatedRule,
    RITMCreateRequest,
    RITMItem,
    RITMListResponse,
    RITMStatus,
    RITMUpdateRequest,
    RITMWithPolicies,
)
from ..session import SessionData, session_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ritm"])

# RITM number pattern: RITM followed by digits
RITM_NUMBER_PATTERN = re.compile(r"^RITM\d+$")


async def get_session_data(request: Request) -> SessionData:
    """Dependency to get current session."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


def _ritm_to_item(ritm: RITM) -> RITMItem:
    """Convert RITM model to API item."""
    import json

    return RITMItem(
        ritm_number=ritm.ritm_number,
        username_created=ritm.username_created,
        date_created=ritm.date_created.isoformat() if ritm.date_created else "",
        date_updated=ritm.date_updated.isoformat() if ritm.date_updated else None,
        date_approved=ritm.date_approved.isoformat() if ritm.date_approved else None,
        username_approved=ritm.username_approved,
        feedback=ritm.feedback,
        status=ritm.status,
        approver_locked_by=ritm.approver_locked_by,
        approver_locked_at=ritm.approver_locked_at.isoformat() if ritm.approver_locked_at else None,
        source_ips=json.loads(ritm.source_ips) if ritm.source_ips else None,
        dest_ips=json.loads(ritm.dest_ips) if ritm.dest_ips else None,
        services=json.loads(ritm.services) if ritm.services else None,
        session_changes_evidence1=ritm.session_changes_evidence1,
    )


def _policy_to_item(policy: Policy) -> PolicyItem:
    """Convert Policy model to API item."""
    import json

    return PolicyItem(
        id=policy.id,
        ritm_number=policy.ritm_number,
        comments=policy.comments,
        rule_name=policy.rule_name,
        domain_uid=policy.domain_uid,
        domain_name=policy.domain_name,
        package_uid=policy.package_uid,
        package_name=policy.package_name,
        section_uid=policy.section_uid,
        section_name=policy.section_name,
        position_type=policy.position_type,
        position_number=policy.position_number,
        action=policy.action,
        track=policy.track,
        source_ips=json.loads(policy.source_ips),
        dest_ips=json.loads(policy.dest_ips),
        services=json.loads(policy.services),
    )


def _is_uuid_like(value: str) -> bool:
    return bool(
        re.match(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
            value,
        )
    )


def _normalize_session_changes_evidence(
    session_changes_json: str | None,
    policies: list[Policy],
    created_rules: list[RITMCreatedRule],
) -> str | None:
    """Backfill section/rule metadata for older stored session_changes payloads."""
    if not session_changes_json:
        return session_changes_json

    import json

    try:
        data: dict[str, Any] = json.loads(session_changes_json)
    except Exception:
        return session_changes_json

    domain_changes = data.get("domain_changes")
    if not isinstance(domain_changes, dict):
        return session_changes_json

    rules_by_uid = {r.rule_uid: r for r in created_rules if r.rule_uid}

    policies_by_combo: dict[tuple[str, str], list[Policy]] = {}
    for policy in policies:
        key = (policy.domain_uid, policy.package_uid)
        policies_by_combo.setdefault(key, []).append(policy)

    changed = False

    for domain_data in domain_changes.values():
        if not isinstance(domain_data, dict):
            continue
        tasks = domain_data.get("tasks", [])
        if not isinstance(tasks, list):
            continue

        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_details = task.get("task-details", [])
            if not isinstance(task_details, list):
                continue

            for detail in task_details:
                if not isinstance(detail, dict):
                    continue
                changes = detail.get("changes", [])
                if not isinstance(changes, list):
                    continue

                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    operations = change.get("operations", {})
                    if not isinstance(operations, dict):
                        continue

                    for bucket in ("added-objects", "modified-objects", "deleted-objects"):
                        entries = operations.get(bucket, [])
                        if not isinstance(entries, list):
                            continue

                        for obj in entries:
                            if not isinstance(obj, dict) or obj.get("type") != "access-rule":
                                continue

                            rule_uid = obj.get("uid")
                            rule_name = obj.get("name")

                            current_section = (
                                obj.get("section-name")
                                or obj.get("section_name")
                                or obj.get("access-section-name")
                                or obj.get("layer-name")
                                or obj.get("layer_name")
                                or obj.get("layer")
                            )
                            section_is_missing_or_uid = not (
                                isinstance(current_section, str)
                                and current_section.strip()
                                and not _is_uuid_like(current_section.strip())
                            )

                            if isinstance(rule_uid, str) and rule_uid in rules_by_uid:
                                created_meta = rules_by_uid[rule_uid]

                                if (
                                    obj.get("rule-number") is None
                                    and created_meta.rule_number is not None
                                ):
                                    obj["rule-number"] = created_meta.rule_number
                                    changed = True

                                combo = (created_meta.domain_uid, created_meta.package_uid)
                                combo_policies = policies_by_combo.get(combo, [])
                                selected_policy: Policy | None = None

                                if isinstance(rule_name, str) and rule_name.strip():
                                    for p in combo_policies:
                                        if p.rule_name == rule_name:
                                            selected_policy = p
                                            break

                                if selected_policy is None and len(combo_policies) == 1:
                                    selected_policy = combo_policies[0]

                                if selected_policy is not None:
                                    if (
                                        section_is_missing_or_uid
                                        and selected_policy.section_name
                                        and selected_policy.section_name.strip()
                                    ):
                                        obj["section-name"] = selected_policy.section_name.strip()
                                        changed = True
                                        section_is_missing_or_uid = False

                                    if (
                                        selected_policy.package_name
                                        and selected_policy.package_name.strip()
                                        and (
                                            not isinstance(obj.get("package-name"), str)
                                            or not obj.get("package-name", "").strip()
                                        )
                                    ):
                                        obj["package-name"] = selected_policy.package_name.strip()
                                        changed = True

                            if section_is_missing_or_uid:
                                layer_name = obj.get("layer-name") or obj.get("layer_name")
                                if (
                                    isinstance(layer_name, str)
                                    and layer_name.strip()
                                    and not _is_uuid_like(layer_name.strip())
                                ):
                                    obj["section-name"] = layer_name.strip()
                                    changed = True

    if not changed:
        return session_changes_json

    return json.dumps(data)


@router.post("/ritm")
async def create_ritm(
    request: RITMCreateRequest,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Create a new RITM."""
    # Validate RITM number format
    if not RITM_NUMBER_PATTERN.match(request.ritm_number):
        raise HTTPException(
            status_code=400,
            detail="RITM number must match pattern RITM followed by digits (e.g., RITM1234567)",
        )

    async with AsyncSession(engine) as db:
        # Check for duplicate
        existing = await db.execute(
            select(RITM).where(col(RITM.ritm_number) == request.ritm_number)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail=f"RITM {request.ritm_number} already exists"
            )

        # Create new RITM
        ritm = RITM(
            ritm_number=request.ritm_number,
            username_created=session.username,
            date_created=datetime.now(UTC),
            status=RITMStatus.WORK_IN_PROGRESS,
        )
        db.add(ritm)
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Created RITM {request.ritm_number} by {session.username}")
        return _ritm_to_item(ritm)


@router.get("/ritm")
async def list_ritms(
    status: int | None = None,
    username: str | None = None,
    _session: SessionData = Depends(get_session_data),
) -> RITMListResponse:
    """List all RITMs with optional filtering."""
    async with AsyncSession(engine) as db:
        query = select(RITM)

        if status is not None:
            query = query.where(col(RITM.status) == status)
        if username is not None:
            query = query.where(col(RITM.username_created) == username)

        query = query.order_by(col(RITM.date_created).desc())

        result = await db.execute(query)
        ritms = result.scalars().all()

        return RITMListResponse(ritms=[_ritm_to_item(r) for r in ritms])


@router.get("/ritm/{ritm_number}")
async def get_ritm(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> RITMWithPolicies:
    """Get a single RITM with its policies."""
    async with AsyncSession(engine) as db:
        # Get RITM
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Get policies
        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = list(policies_result.scalars().all())

        created_rules_result = await db.execute(
            select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
        )
        created_rules = list(created_rules_result.scalars().all())

        normalized = _normalize_session_changes_evidence(
            ritm.session_changes_evidence1,
            policies,
            created_rules,
        )
        if normalized != ritm.session_changes_evidence1:
            ritm.session_changes_evidence1 = normalized
            await db.commit()

        return RITMWithPolicies(
            ritm=_ritm_to_item(ritm), policies=[_policy_to_item(p) for p in policies]
        )


@router.put("/ritm/{ritm_number}")
async def update_ritm(
    ritm_number: str,
    request: RITMUpdateRequest,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Update RITM status and/or feedback."""
    async with AsyncSession(engine) as db:
        # Get RITM
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Handle status changes
        if request.status is not None:
            # Validate status transition
            if request.status == RITMStatus.APPROVED:
                # Cannot approve own RITM
                if ritm.username_created == session.username:
                    raise HTTPException(status_code=400, detail="You cannot approve your own RITM")
                # Must be in ready state
                if ritm.status != RITMStatus.READY_FOR_APPROVAL:
                    raise HTTPException(status_code=400, detail="RITM must be ready for approval")
                ritm.date_approved = datetime.now(UTC)
                ritm.username_approved = session.username
                # Clear approval lock
                ritm.approver_locked_by = None
                ritm.approver_locked_at = None

            elif request.status == RITMStatus.READY_FOR_APPROVAL:
                # Only creator can submit for approval
                if ritm.username_created != session.username:
                    raise HTTPException(
                        status_code=400, detail="Only the creator can submit for approval"
                    )
                ritm.date_updated = datetime.now(UTC)

            elif request.status == RITMStatus.WORK_IN_PROGRESS:
                # Returning for changes - requires feedback
                if not request.feedback:
                    raise HTTPException(
                        status_code=400, detail="Feedback is required when returning for changes"
                    )

            ritm.status = request.status

        # Handle feedback
        if request.feedback is not None:
            ritm.feedback = request.feedback

        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Updated RITM {ritm_number} by {session.username}")
        return _ritm_to_item(ritm)


@router.post("/ritm/{ritm_number}/policy")
async def save_policy(
    ritm_number: str,
    policies: list[PolicyItem],
    _session: SessionData = Depends(get_session_data),
) -> dict[str, str]:
    """Save policy rules for a RITM."""
    import json

    async with AsyncSession(engine) as db:
        # Verify RITM exists
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Delete existing policies for this RITM
        await db.execute(delete(Policy).where(col(Policy.ritm_number) == ritm_number))

        # Insert new policies
        for policy_item in policies:
            policy = Policy(
                ritm_number=ritm_number,
                comments=policy_item.comments,
                rule_name=policy_item.rule_name,
                domain_uid=policy_item.domain_uid,
                domain_name=policy_item.domain_name,
                package_uid=policy_item.package_uid,
                package_name=policy_item.package_name,
                section_uid=policy_item.section_uid,
                section_name=policy_item.section_name,
                position_type=policy_item.position_type,
                position_number=policy_item.position_number,
                action=policy_item.action,
                track=policy_item.track,
                source_ips=json.dumps(policy_item.source_ips),
                dest_ips=json.dumps(policy_item.dest_ips),
                services=json.dumps(policy_item.services),
            )
            db.add(policy)

        await db.commit()

        logger.info(f"Saved {len(policies)} policies for RITM {ritm_number}")
        return {"message": f"Saved {len(policies)} policies"}


class RITMPoolsRequest(BaseModel):
    """Request to save input pools for a RITM."""

    source_ips: list[str]
    dest_ips: list[str]
    services: list[str]


@router.post("/ritm/{ritm_number}/pools")
async def save_pools(
    ritm_number: str,
    pools: RITMPoolsRequest,
    _session: SessionData = Depends(get_session_data),
) -> dict[str, str]:
    """Save input pools (source/dest IPs, services) for a RITM."""
    import json

    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        ritm.source_ips = json.dumps(pools.source_ips)
        ritm.dest_ips = json.dumps(pools.dest_ips)
        ritm.services = json.dumps(pools.services)

        await db.commit()
        await db.refresh(ritm)

        logger.info(
            f"Saved pools for RITM {ritm_number}: {len(pools.source_ips)} source IPs, {len(pools.dest_ips)} dest IPs, {len(pools.services)} services"
        )
        return {"message": "Pools saved successfully"}


@router.post("/ritm/{ritm_number}/lock")
async def acquire_approval_lock(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Acquire approval lock on a RITM."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Check if already locked
        if ritm.approver_locked_by:
            # Check if lock has expired
            if ritm.approver_locked_at:
                # Handle both timezone-aware and naive datetimes from DB
                locked_at = ritm.approver_locked_at
                if locked_at.tzinfo is None:
                    locked_at = locked_at.replace(tzinfo=UTC)
                lock_age = datetime.now(UTC) - locked_at
                if lock_age < timedelta(minutes=settings.approval_lock_minutes):
                    raise HTTPException(
                        status_code=400, detail=f"RITM is locked by {ritm.approver_locked_by}"
                    )
                # Lock expired, clear it
                logger.info(f"Approval lock expired for RITM {ritm_number}")
            else:
                raise HTTPException(
                    status_code=400, detail=f"RITM is locked by {ritm.approver_locked_by}"
                )

        # Acquire lock
        ritm.approver_locked_by = session.username
        ritm.approver_locked_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Approval lock acquired for RITM {ritm_number} by {session.username}")
        return _ritm_to_item(ritm)


@router.post("/ritm/{ritm_number}/unlock")
async def release_approval_lock(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Release approval lock on a RITM."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Only locker can release
        if ritm.approver_locked_by != session.username:
            raise HTTPException(status_code=400, detail="You did not acquire this lock")

        # Release lock
        ritm.approver_locked_by = None
        ritm.approver_locked_at = None

        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Approval lock released for RITM {ritm_number}")
        return _ritm_to_item(ritm)


@router.post("/ritm/{ritm_number}/publish")
async def publish_ritm(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> PublishResponse:
    """Publish an approved RITM to Check Point."""
    import json

    async with AsyncSession(engine) as db:
        # Get RITM
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Must be approved
        if ritm.status != RITMStatus.APPROVED:
            raise HTTPException(status_code=400, detail="RITM must be approved before publishing")

        # Get policies
        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = policies_result.scalars().all()

        if not policies:
            raise HTTPException(status_code=400, detail="RITM has no policies to publish")

        # Convert to domains2 batch format
        rules_to_create = []
        for policy in policies:
            rules_to_create.append(
                {
                    "domain_uid": policy.domain_uid,
                    "package_uid": policy.package_uid,
                    "section_uid": policy.section_uid,
                    "position": {
                        "type": policy.position_type,
                        "custom_number": policy.position_number,
                    },
                    "action": policy.action,
                    "track": policy.track,
                    "source_ips": json.loads(policy.source_ips),
                    "dest_ips": json.loads(policy.dest_ips),
                    "services": json.loads(policy.services),
                }
            )

        # TODO: Call actual Check Point API via domains2 endpoint
        # For now, mock the response
        logger.info(f"Publishing {len(rules_to_create)} rules for RITM {ritm_number}")

        # On success, update status to completed
        ritm.status = RITMStatus.COMPLETED
        await db.commit()
        await db.refresh(ritm)

        return PublishResponse(
            success=True,
            message=f"Published {len(rules_to_create)} rules for RITM {ritm_number}",
            created=len(rules_to_create),
            errors=[],
        )
