"""Tests for ObjectMatcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from fa.services.object_matcher import ObjectMatcher


@pytest.fixture
def mock_client():
    """Create mock CPAIOPS client."""
    client = MagicMock()
    client.get_mgmt_names.return_value = ["mgmt1"]
    return client


def test_scoring_with_convention_match(mock_client):
    """Test that convention match gets higher score."""
    matcher = ObjectMatcher(mock_client)

    obj_convention = {"name": "Host_10.0.0.1", "uid": "1", "usage-count": 5}
    obj_high_usage = {"name": "web-server", "uid": "2", "usage-count": 50}

    score_conv = matcher._score_object(obj_convention, pattern_match=True)
    score_usage = matcher._score_object(obj_high_usage, pattern_match=False)

    assert score_conv == (100, 5)
    assert score_usage == (0, 50)
    # Convention match wins (100 + 5 > 0 + 50)
    assert score_conv > score_usage


def test_matches_convention_host(mock_client):
    """Test host convention matching."""
    matcher = ObjectMatcher(mock_client)

    assert matcher._matches_convention({"name": "Host_10.0.0.1"}, "host") is True
    assert matcher._matches_convention({"name": "global_Host_10.0.0.1"}, "host") is True
    assert matcher._matches_convention({"name": "web-server"}, "host") is False


def test_generate_host_name(mock_client):
    """Test host name generation."""
    matcher = ObjectMatcher(mock_client)

    assert matcher._generate_object_name("host", "10.0.0.1", is_global=False) == "Host_10.0.0.1"
    assert (
        matcher._generate_object_name("host", "10.0.0.1", is_global=True) == "global_Host_10.0.0.1"
    )


def test_generate_network_name(mock_client):
    """Test network name generation."""
    matcher = ObjectMatcher(mock_client)

    result = matcher._generate_object_name("network", "192.168.1.0/24", is_global=False)
    assert result == "Net_192.168.1.0_24"

    result_global = matcher._generate_object_name("network", "192.168.1.0/24", is_global=True)
    assert result_global == "global_Net_192.168.1.0_24"


@pytest.mark.asyncio
async def test_create_host_object(mock_client):
    """Test creating a host object."""
    matcher = ObjectMatcher(mock_client)

    # Mock the API call
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.data = {"uid": "new-uid-123"}
    mock_client.api_call = AsyncMock(return_value=mock_result)

    result = await matcher._create_object(
        obj_type="host",
        name="Host_10.0.0.1",
        value="10.0.0.1",
        _domain_uid="dm1",
        domain_name="Domain1",
    )

    assert result["uid"] == "new-uid-123"
    mock_client.api_call.assert_called_once_with(
        "mgmt1",
        "add-host",
        domain="Domain1",
        payload={"name": "Host_10.0.0.1", "ip-address": "10.0.0.1"},
    )


@pytest.mark.asyncio
async def test_match_reuses_existing_host_without_create(mock_client):
    """When host exists in domain, matcher should not call add-host."""
    matcher = ObjectMatcher(mock_client)

    async def fake_api_query(mgmt_name, command, domain=None, payload=None):
        result = MagicMock()
        if command == "show-hosts" and payload == {"filter": "1.1.1.1"}:
            result.success = True
            result.objects = [
                {
                    "uid": "uid-existing-host",
                    "name": "Host_1.1.1.1",
                    "ipv4-address": "1.1.1.1",
                    "used-by": {"total": 7},
                    "domain": {"name": domain or "(system)"},
                }
            ]
            return result

        result.success = True
        result.objects = []
        return result

    mock_client.api_query = AsyncMock(side_effect=fake_api_query)
    mock_client.api_call = AsyncMock()

    results = await matcher.match_and_create_objects(
        inputs=["1.1.1.1"],
        domain_uid="domain-uid-1",
        domain_name="CPCodeOps",
        create_missing=True,
    )

    assert len(results) == 1
    assert results[0]["object_uid"] == "uid-existing-host"
    assert results[0]["created"] is False
    mock_client.api_call.assert_not_called()
