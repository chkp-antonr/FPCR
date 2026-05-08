"""Tests for RITM status transition table."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from fa.models import RITMStatus, TryVerifyRequest
from fa.services.ritm_transitions import ALLOWED_TRANSITIONS, assert_transition

WIP = RITMStatus.WORK_IN_PROGRESS
RFA = RITMStatus.READY_FOR_APPROVAL
APP = RITMStatus.APPROVED
COM = RITMStatus.COMPLETED


def test_allowed_transitions_covers_all_states():
    """Every RITMStatus value must appear as a key in the table."""
    for status in RITMStatus:
        assert status in ALLOWED_TRANSITIONS, f"{status} missing from ALLOWED_TRANSITIONS"


def test_valid_transitions_do_not_raise():
    valid = [
        (WIP, RFA),
        (RFA, APP),
        (RFA, WIP),
        (APP, COM),
    ]
    for current, target in valid:
        assert_transition(current, target)  # must not raise


def test_invalid_transition_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        assert_transition(WIP, APP)  # cannot skip READY_FOR_APPROVAL
    assert exc_info.value.status_code == 400


def test_completed_is_terminal():
    for target in RITMStatus:
        with pytest.raises(HTTPException):
            assert_transition(COM, target)


def test_approved_cannot_go_to_wip():
    with pytest.raises(HTTPException):
        assert_transition(APP, WIP)


def test_wip_cannot_go_to_completed():
    with pytest.raises(HTTPException):
        assert_transition(WIP, COM)


def test_try_verify_request_rejects_force_continue():
    """force_continue must not be accepted — removed in favour of All-or-No policy."""
    with pytest.raises(ValidationError):
        TryVerifyRequest(force_continue=True)


def test_try_verify_request_defaults_valid():
    req = TryVerifyRequest()
    assert req.skip_package_uids == []
