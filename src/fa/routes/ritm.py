"""RITM (Requested Item) approval workflow endpoints."""

import logging
import re
from datetime import UTC, datetime, timedelta

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
    ReviewerItem,
    RITMCreateRequest,
    RITMEditor,
    RITMItem,
    RITMListResponse,
    RITMReviewer,
    RITMStatus,
    RITMUpdateRequest,
    RITMWithPolicies,
)
from ..services.ritm_transitions import assert_transition
from ..services.snapshot_service import SnapshotService
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


async def _ritm_to_item(db: AsyncSession, ritm: RITM) -> RITMItem:
    """Convert RITM model to API item, loading editors and reviewers."""
    import json

    editors_result = await db.execute(
        select(RITMEditor).where(col(RITMEditor.ritm_number) == ritm.ritm_number)
    )
    editors = [e.username for e in editors_result.scalars().all()]

    reviewers_result = await db.execute(
        select(RITMReviewer).where(col(RITMReviewer.ritm_number) == ritm.ritm_number)
    )
    reviewers = [
        ReviewerItem(
            username=r.username,
            action=r.action,
            acted_at=r.acted_at.isoformat() if r.acted_at else "",
        )
        for r in reviewers_result.scalars().all()
    ]

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
        editor_locked_by=ritm.editor_locked_by,
        editor_locked_at=ritm.editor_locked_at.isoformat() if ritm.editor_locked_at else None,
        source_ips=json.loads(ritm.source_ips) if ritm.source_ips else None,
        dest_ips=json.loads(ritm.dest_ips) if ritm.dest_ips else None,
        services=json.loads(ritm.services) if ritm.services else None,
        editors=editors,
        reviewers=reviewers,
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


@router.post("/ritm")
async def create_ritm(
    request: RITMCreateRequest,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Create a new RITM. Creator is automatically added to editors list."""
    if not RITM_NUMBER_PATTERN.match(request.ritm_number):
        raise HTTPException(
            status_code=400,
            detail="RITM number must match pattern RITM followed by digits (e.g., RITM1234567)",
        )

    async with AsyncSession(engine) as db:
        existing = await db.execute(
            select(RITM).where(col(RITM.ritm_number) == request.ritm_number)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail=f"RITM {request.ritm_number} already exists"
            )

        ritm = RITM(
            ritm_number=request.ritm_number,
            username_created=session.username,
            date_created=datetime.now(UTC),
            status=RITMStatus.WORK_IN_PROGRESS,
            editor_locked_by=session.username,
            editor_locked_at=datetime.now(UTC),
        )
        db.add(ritm)
        db.add(
            RITMEditor(
                ritm_number=request.ritm_number,
                username=session.username,
                added_at=datetime.now(UTC),
            )
        )
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Created RITM {request.ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)


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

        items = [await _ritm_to_item(db, r) for r in ritms]
        return RITMListResponse(ritms=items)


@router.get("/ritm/{ritm_number}")
async def get_ritm(
    ritm_number: str,
    _session: SessionData = Depends(get_session_data),
) -> RITMWithPolicies:
    """Get a single RITM with its policies."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        policies_result = await db.execute(
            select(Policy).where(col(Policy.ritm_number) == ritm_number)
        )
        policies = list(policies_result.scalars().all())

        return RITMWithPolicies(
            ritm=await _ritm_to_item(db, ritm),
            policies=[_policy_to_item(p) for p in policies],
        )


@router.put("/ritm/{ritm_number}")
async def update_ritm(
    ritm_number: str,
    request: RITMUpdateRequest,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Update RITM status and/or feedback."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if request.status is not None:
            assert_transition(RITMStatus(ritm.status), RITMStatus(request.status))
            if request.status == RITMStatus.READY_FOR_APPROVAL:
                # Must be a registered editor AND currently hold the editor lock
                editor_result = await db.execute(
                    select(RITMEditor).where(
                        col(RITMEditor.ritm_number) == ritm_number,
                        col(RITMEditor.username) == session.username,
                    )
                )
                if not editor_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=400, detail="Only editors can submit for approval"
                    )
                if ritm.editor_locked_by != session.username:
                    raise HTTPException(
                        status_code=400,
                        detail="You must hold the editor lock to submit for approval",
                    )
                ritm.date_updated = datetime.now(UTC)

            elif request.status == RITMStatus.APPROVED:
                # Must NOT be in editors list
                editor_result = await db.execute(
                    select(RITMEditor).where(
                        col(RITMEditor.ritm_number) == ritm_number,
                        col(RITMEditor.username) == session.username,
                    )
                )
                if editor_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=400, detail="Editors cannot approve their own RITM"
                    )
                if ritm.status != RITMStatus.READY_FOR_APPROVAL:
                    raise HTTPException(status_code=400, detail="RITM must be ready for approval")
                ritm.date_approved = datetime.now(UTC)
                ritm.username_approved = session.username
                ritm.approver_locked_by = None
                ritm.approver_locked_at = None
                db.add(
                    RITMReviewer(
                        ritm_number=ritm_number,
                        username=session.username,
                        action="approved",
                        acted_at=datetime.now(UTC),
                    )
                )

            elif request.status == RITMStatus.WORK_IN_PROGRESS:
                if not request.feedback:
                    raise HTTPException(
                        status_code=400, detail="Feedback is required when returning for changes"
                    )
                db.add(
                    RITMReviewer(
                        ritm_number=ritm_number,
                        username=session.username,
                        action="rejected",
                        acted_at=datetime.now(UTC),
                    )
                )
                ritm.editor_locked_by = None
                ritm.editor_locked_at = None

            ritm.status = request.status

        if request.feedback is not None:
            ritm.feedback = request.feedback

        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Updated RITM {ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)


@router.post("/ritm/{ritm_number}/policy")
async def save_policy(
    ritm_number: str,
    policies: list[PolicyItem],
    session: SessionData = Depends(get_session_data),
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

        # If user holds editor lock, record them as a co-editor (ON CONFLICT IGNORE)
        if ritm.editor_locked_by == session.username:
            existing_editor = await db.execute(
                select(RITMEditor).where(
                    col(RITMEditor.ritm_number) == ritm_number,
                    col(RITMEditor.username) == session.username,
                )
            )
            if not existing_editor.scalar_one_or_none():
                db.add(
                    RITMEditor(
                        ritm_number=ritm_number,
                        username=session.username,
                        added_at=datetime.now(UTC),
                    )
                )

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
        return await _ritm_to_item(db, ritm)


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
        return await _ritm_to_item(db, ritm)


@router.post("/ritm/{ritm_number}/editor-lock")
async def acquire_editor_lock(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Acquire editor lock. Fails if user is a reviewer or lock is held by another."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Reviewers cannot become editors
        reviewer_result = await db.execute(
            select(RITMReviewer).where(
                col(RITMReviewer.ritm_number) == ritm_number,
                col(RITMReviewer.username) == session.username,
            )
        )
        if reviewer_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Reviewer cannot acquire editor lock")

        # Check existing lock
        if ritm.editor_locked_by:
            locked_at = ritm.editor_locked_at
            if locked_at:
                if locked_at.tzinfo is None:
                    locked_at = locked_at.replace(tzinfo=UTC)
                if datetime.now(UTC) - locked_at < timedelta(
                    minutes=settings.approval_lock_minutes
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"RITM is locked by {ritm.editor_locked_by}",
                    )
                logger.info(f"Editor lock expired for RITM {ritm_number}")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"RITM is locked by {ritm.editor_locked_by}",
                )

        ritm.editor_locked_by = session.username
        ritm.editor_locked_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Editor lock acquired for RITM {ritm_number} by {session.username}")

    # Snapshot current rules so the upcoming correction attempt can diff against them
    from sqlalchemy import func as sa_func
    from sqlmodel import col as sa_col

    from ..models import RITMPackageAttempt

    async with AsyncSession(engine) as _db:
        attempt_result = await _db.execute(
            select(sa_func.max(RITMPackageAttempt.attempt)).where(
                sa_col(RITMPackageAttempt.ritm_number) == ritm_number
            )
        )
        current_attempt = attempt_result.scalar_one_or_none() or 0
    await SnapshotService().create_or_overwrite(ritm_number=ritm_number, attempt=current_attempt)

    async with AsyncSession(engine) as db:
        result2 = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result2.scalar_one()
        return await _ritm_to_item(db, ritm)


@router.post("/ritm/{ritm_number}/editor-unlock")
async def release_editor_lock(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> RITMItem:
    """Release editor lock. Only the lock holder can release."""
    async with AsyncSession(engine) as db:
        result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        if ritm.editor_locked_by != session.username:
            raise HTTPException(status_code=400, detail="You did not acquire this lock")

        ritm.editor_locked_by = None
        ritm.editor_locked_at = None
        await db.commit()
        await db.refresh(ritm)

        logger.info(f"Editor lock released for RITM {ritm_number} by {session.username}")
        return await _ritm_to_item(db, ritm)
