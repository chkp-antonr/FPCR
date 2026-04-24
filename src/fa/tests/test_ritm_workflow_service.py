"""Tests for RITMWorkflowService."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from fa.models import EvidenceData
from fa.services.ritm_workflow_service import RITMWorkflowService


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.api_call = AsyncMock()
    client.cache = MagicMock()
    client.get_mgmt_names = Mock(return_value=["test-mgmt"])
    return client


@pytest.mark.asyncio
async def test_combine_evidence_empty(mock_client):
    """Test _combine_evidence with empty list."""
    service = RITMWorkflowService(
        client=mock_client,
        ritm_number="RITM123",
        username="testuser",
    )
    result = service._combine_evidence([])
    assert result["domain_changes"] == {}
    assert result["apply_sessions"] == {}
    assert result["apply_session_trace"] == []


@pytest.mark.asyncio
async def test_combine_evidence_with_data(mock_client):
    """Test _combine_evidence merges multiple evidence items."""
    service = RITMWorkflowService(
        client=mock_client,
        ritm_number="RITM123",
        username="testuser",
    )

    evidence1 = EvidenceData(
        domain_name="Domain1",
        package_name="Package1",
        package_uid="p1-uid",
        domain_uid="d1-uid",
        session_changes={
            "domain_changes": {"Domain1": {"tasks": []}},
            "apply_sessions": {"Domain1": "sid1"},
        },
        session_uid="session-1",
        sid="sid1",
    )

    evidence2 = EvidenceData(
        domain_name="Domain2",
        package_name="Package2",
        package_uid="p2-uid",
        domain_uid="d2-uid",
        session_changes={
            "domain_changes": {"Domain2": {"tasks": []}},
            "apply_sessions": {"Domain2": "sid2"},
        },
        session_uid="session-2",
        sid="sid2",
    )

    result = service._combine_evidence([evidence1, evidence2])

    assert "Domain1" in result["domain_changes"]
    assert "Domain2" in result["domain_changes"]
    assert "Domain1" in result["apply_sessions"]
    assert "Domain2" in result["apply_sessions"]
    assert len(result["apply_session_trace"]) == 2
