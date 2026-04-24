"""Tests for PolicyVerifier."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cpaiops import ApiCallResult
from fa.services.policy_verifier import PolicyVerifier, VerificationResult


@pytest.fixture
def mock_client():
    """Create mock CPAIOPS client."""
    client = MagicMock()
    client.get_mgmt_names.return_value = ["mgmt1"]
    return client


@pytest.mark.asyncio
async def test_verify_policy_success(mock_client):
    """Test successful policy verification."""
    mock_result = ApiCallResult(success=True, data={}, message="", errors=[])
    mock_client.api_call = AsyncMock(return_value=mock_result)

    verifier = PolicyVerifier(mock_client)
    result = await verifier.verify_policy("Global", "Standard_Policy")

    assert result.success is True
    assert result.errors == []


@pytest.mark.asyncio
async def test_verify_policy_failure(mock_client):
    """Test failed policy verification."""
    mock_result = ApiCallResult(
        success=False,
        data=None,
        message="Service tcp-8080-custom not found",
        code="NOT_FOUND"
    )
    mock_client.api_call = AsyncMock(return_value=mock_result)

    verifier = PolicyVerifier(mock_client)
    result = await verifier.verify_policy("Global", "Standard_Policy")

    assert result.success is False
    assert len(result.errors) == 1
    assert "Service tcp-8080-custom not found" in result.errors[0]


@pytest.mark.asyncio
async def test_verify_policy_with_session_name(mock_client):
    """Test that session name is included in payload."""
    mock_result = ApiCallResult(success=True, data={}, message="", errors=[])
    mock_client.api_call = AsyncMock(return_value=mock_result)

    verifier = PolicyVerifier(mock_client)
    await verifier.verify_policy(
        "Global",
        "Standard_Policy",
        session_name="RITM1234567 verify"
    )

    mock_client.api_call.assert_called_once()
    call_args = mock_client.api_call.call_args
    payload = call_args[1]["payload"]
    assert payload["session-name"] == "RITM1234567 verify"