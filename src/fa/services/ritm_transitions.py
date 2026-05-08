"""Explicit RITM status transition topology.

The table here owns *which* transitions are valid.
Guards (who is allowed) and side-effects (what happens) stay in the callers.
"""

from fastapi import HTTPException

from fa.models import RITMStatus

ALLOWED_TRANSITIONS: dict[RITMStatus, set[RITMStatus]] = {
    RITMStatus.WORK_IN_PROGRESS: {RITMStatus.READY_FOR_APPROVAL},
    RITMStatus.READY_FOR_APPROVAL: {RITMStatus.APPROVED, RITMStatus.WORK_IN_PROGRESS},
    RITMStatus.APPROVED: {RITMStatus.COMPLETED},
    RITMStatus.COMPLETED: set(),
}


def assert_transition(current: RITMStatus, target: RITMStatus) -> None:
    """Raise HTTP 400 if target is not a legal successor of current."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition RITM from '{current.name}' to '{target.name}'",
        )
