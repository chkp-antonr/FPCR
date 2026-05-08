"""Snapshot service – persists the current rule set for correction diff calculations."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ..db import engine
from ..models import RITMCreatedRule, RITMEditSnapshot

logger = logging.getLogger(__name__)


class SnapshotService:
    """Create or overwrite the edit snapshot for a RITM.

    The snapshot captures the current set of created rule UIDs and associated
    metadata so that a subsequent correction attempt can diff against it.
    """

    async def create_or_overwrite(
        self,
        ritm_number: str,
        attempt: int,
    ) -> RITMEditSnapshot:
        """Persist a snapshot of the current rule set for *ritm_number*.

        If a snapshot already exists for this RITM it is overwritten in place
        (updated_at is refreshed, content replaced).

        Args:
            ritm_number: The RITM being snapshotted.
            attempt: The current attempt number (stored for audit purposes).

        Returns:
            The created or updated ``RITMEditSnapshot`` row.
        """
        async with AsyncSession(engine) as db:
            # Load current created rules
            rules_result = await db.execute(
                select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
            )
            rules = list(rules_result.scalars().all())

            rules_json = json.dumps(
                [
                    {
                        "rule_uid": r.rule_uid,
                        "domain_uid": r.domain_uid,
                        "package_uid": r.package_uid,
                        "disabled": r.disabled,
                        "verification_status": r.verification_status,
                    }
                    for r in rules
                ]
            )

            # Upsert: overwrite if exists, create otherwise
            existing_result = await db.execute(
                select(RITMEditSnapshot).where(col(RITMEditSnapshot.ritm_number) == ritm_number)
            )
            snapshot = existing_result.scalar_one_or_none()

            now = datetime.now(UTC)
            if snapshot is None:
                snapshot = RITMEditSnapshot(
                    ritm_number=ritm_number,
                    snapshot_attempt=attempt,
                    rules_json=rules_json,
                    objects_json=None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(snapshot)
                logger.info(
                    f"[SnapshotService] Created snapshot for {ritm_number} "
                    f"(attempt={attempt}, rules={len(rules)})"
                )
            else:
                snapshot.snapshot_attempt = attempt
                snapshot.rules_json = rules_json
                snapshot.objects_json = None
                snapshot.updated_at = now
                db.add(snapshot)
                logger.info(
                    f"[SnapshotService] Overwrote snapshot for {ritm_number} "
                    f"(attempt={attempt}, rules={len(rules)})"
                )

            await db.commit()
            await db.refresh(snapshot)
            return snapshot
