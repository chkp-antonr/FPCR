"""Correction diff service – compares current rule set against the edit snapshot."""

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ..db import engine
from ..models import RITMCreatedRule, RITMEditSnapshot

logger = logging.getLogger(__name__)


@dataclass
class RuleDiff:
    """Diff result between snapshot and current rule set."""

    ritm_number: str
    snapshot_attempt: int | None
    added_rule_uids: list[str] = field(default_factory=list)
    removed_rule_uids: list[str] = field(default_factory=list)
    unchanged_rule_uids: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """True if the rule set has changed since the snapshot was taken."""
        return bool(self.added_rule_uids or self.removed_rule_uids)


class CorrectionDiffService:
    """Compare the current persisted rule set against the stored edit snapshot.

    Used during correction workflows to produce a plan that only processes
    rules added or removed since the snapshot was taken.
    """

    async def get_diff(self, ritm_number: str) -> RuleDiff:
        """Return the diff between the current rules and the latest snapshot.

        Args:
            ritm_number: The RITM to diff.

        Returns:
            A ``RuleDiff`` describing added, removed, and unchanged rules.
            If no snapshot exists all current rules are reported as *added*.
        """
        async with AsyncSession(engine) as db:
            # Load snapshot
            snap_result = await db.execute(
                select(RITMEditSnapshot).where(col(RITMEditSnapshot.ritm_number) == ritm_number)
            )
            snapshot = snap_result.scalar_one_or_none()

            # Load current rules
            rules_result = await db.execute(
                select(RITMCreatedRule).where(col(RITMCreatedRule.ritm_number) == ritm_number)
            )
            current_rules = list(rules_result.scalars().all())

        current_uids: set[str] = {r.rule_uid for r in current_rules}

        if snapshot is None or not snapshot.rules_json:
            logger.warning(
                f"[CorrectionDiffService] No snapshot for {ritm_number}; "
                "treating all current rules as added"
            )
            return RuleDiff(
                ritm_number=ritm_number,
                snapshot_attempt=None,
                added_rule_uids=sorted(current_uids),
            )

        try:
            snapshot_entries: list[dict[str, object]] = json.loads(snapshot.rules_json)
        except (json.JSONDecodeError, ValueError):
            logger.error(
                f"[CorrectionDiffService] Corrupt rules_json for {ritm_number}; "
                "treating all current rules as added"
            )
            return RuleDiff(
                ritm_number=ritm_number,
                snapshot_attempt=snapshot.snapshot_attempt,
                added_rule_uids=sorted(current_uids),
            )

        snapshot_uids: set[str] = {str(e["rule_uid"]) for e in snapshot_entries if "rule_uid" in e}

        added = sorted(current_uids - snapshot_uids)
        removed = sorted(snapshot_uids - current_uids)
        unchanged = sorted(current_uids & snapshot_uids)

        logger.info(
            f"[CorrectionDiffService] Diff for {ritm_number}: "
            f"+{len(added)} added, -{len(removed)} removed, "
            f"{len(unchanged)} unchanged"
        )

        return RuleDiff(
            ritm_number=ritm_number,
            snapshot_attempt=snapshot.snapshot_attempt,
            added_rule_uids=added,
            removed_rule_uids=removed,
            unchanged_rule_uids=unchanged,
        )
