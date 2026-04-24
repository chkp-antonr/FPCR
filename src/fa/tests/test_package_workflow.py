"""Tests for PackageWorkflowService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fa.services.package_workflow import PackageInfo, PackageWorkflowService


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.api_call = AsyncMock()
    client.cache = MagicMock()
    client.cache.get_sid = AsyncMock()
    client.cache.get_uid_by_sid = AsyncMock(return_value="test-session-uid")
    return client


@pytest.fixture
def package_info():
    return PackageInfo(
        domain_name="TestDomain",
        domain_uid="test-domain-uid",
        package_name="TestPackage",
        package_uid="test-package-uid",
        policies=[],
    )


@pytest.mark.asyncio
async def test_verify_first_success(mock_client, package_info):
    """Test verify_first returns success when policy verification passes."""
    from fa.services.policy_verifier import VerificationResult

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Mock PolicyVerifier to return success
    with patch("fa.services.package_workflow.PolicyVerifier") as mock_verifier_class:
        mock_verifier = AsyncMock()
        mock_verifier.verify_policy = AsyncMock(
            return_value=VerificationResult(success=True, errors=[], warnings=None)
        )
        mock_verifier_class.return_value = mock_verifier

        result = await service.verify_first()

        assert result.success is True
        assert result.errors == []
        mock_verifier.verify_policy.assert_called_once_with(
            domain_name="TestDomain",
            package_name="TestPackage",
        )


@pytest.mark.asyncio
async def test_verify_first_failure(mock_client, package_info):
    """Test verify_first returns failure when policy verification fails."""
    from fa.services.policy_verifier import VerificationResult

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Mock PolicyVerifier to return failure
    with patch("fa.services.package_workflow.PolicyVerifier") as mock_verifier_class:
        mock_verifier = AsyncMock()
        mock_verifier.verify_policy = AsyncMock(
            return_value=VerificationResult(
                success=False, errors=["Verification failed"], warnings=None
            )
        )
        mock_verifier_class.return_value = mock_verifier

        result = await service.verify_first()

        assert result.success is False
        assert result.errors == ["Verification failed"]


@pytest.mark.asyncio
async def test_verify_again_success(mock_client, package_info):
    """Test verify_again returns success when policy verification passes."""
    from fa.services.policy_verifier import VerificationResult

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Mock PolicyVerifier to return success
    with patch("fa.services.package_workflow.PolicyVerifier") as mock_verifier_class:
        mock_verifier = AsyncMock()
        mock_verifier.verify_policy = AsyncMock(
            return_value=VerificationResult(success=True, errors=[], warnings=None)
        )
        mock_verifier_class.return_value = mock_verifier

        result = await service.verify_again()

        assert result.success is True
        assert result.errors == []


@pytest.mark.asyncio
async def test_rollback_rules(mock_client, package_info):
    """Test rollback_rules deletes rules via CheckPointRuleManager."""
    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Mock CheckPointRuleManager.delete
    with patch("fa.services.package_workflow.CheckPointRuleManager") as mock_mgr_class:
        mock_mgr = AsyncMock()
        mock_mgr.delete = AsyncMock()
        mock_mgr_class.return_value = mock_mgr

        await service.rollback_rules(["rule1", "rule2"])

        assert mock_mgr.delete.call_count == 2


@pytest.mark.asyncio
async def test_disable_rules(mock_client, package_info):
    """Test disable_rules calls set-access-rule for each rule."""
    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    await service.disable_rules(["rule1", "rule2"])

    assert mock_client.api_call.call_count == 2
    # Verify the calls were made with correct parameters
    calls = mock_client.api_call.call_args_list
    assert calls[0][1]["payload"] == {"uid": "rule1", "enabled": False}
    assert calls[1][1]["payload"] == {"uid": "rule2", "enabled": False}


@pytest.mark.asyncio
async def test_capture_evidence(mock_client, package_info):
    """Test capture_evidence returns session changes."""
    # Mock cache responses
    mock_sid_record = MagicMock()
    mock_sid_record.sid = "test-sid"
    mock_client.cache.get_sid = AsyncMock(return_value=mock_sid_record)

    # Mock show-changes response
    mock_changes = {"changes": "test"}
    mock_api_result = MagicMock()
    mock_api_result.success = True
    mock_api_result.data = mock_changes
    mock_client.api_call = AsyncMock(return_value=mock_api_result)

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Set the current session UID (simulating it was captured after creating changes)
    service.current_session_uid = "test-session-uid"

    result = await service.capture_evidence()

    assert result.domain_name == "TestDomain"
    assert result.package_name == "TestPackage"
    assert result.session_changes == mock_changes
    assert result.session_uid == "test-session-uid"
    assert result.sid == "test-sid"


@pytest.mark.asyncio
async def test_capture_evidence_no_sid(mock_client, package_info):
    """Test capture_evidence returns empty evidence when no SID found."""
    # Mock cache to return None
    mock_client.cache.get_sid = AsyncMock(return_value=None)

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    result = await service.capture_evidence()

    assert result.session_changes == {}
    assert result.session_uid is None


def test_extract_list_from_list():
    """Test _extract_list with list input."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._extract_list(["a", "b", "c"])
    assert result == ["a", "b", "c"]


def test_extract_list_from_json_string():
    """Test _extract_list with JSON string input."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._extract_list('["a", "b", "c"]')
    assert result == ["a", "b", "c"]


def test_extract_list_from_empty_string():
    """Test _extract_list with empty string."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._extract_list("")
    assert result == []


def test_build_position_custom():
    """Test _build_position with custom position."""
    mock_policy = MagicMock()
    mock_policy.position_type = "custom"
    mock_policy.position_number = 5
    mock_policy.section_name = None

    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._build_position(mock_policy)
    assert result == 5


def test_build_position_with_section():
    """Test _build_position with section."""
    mock_policy = MagicMock()
    mock_policy.position_type = "top"
    mock_policy.position_number = None
    mock_policy.section_name = "MySection"

    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._build_position(mock_policy)
    assert result == {"top": "MySection"}


def test_build_position_simple():
    """Test _build_position with simple position type."""
    mock_policy = MagicMock()
    mock_policy.position_type = "bottom"
    mock_policy.position_number = None
    mock_policy.section_name = None

    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._build_position(mock_policy)
    assert result == "bottom"


def test_resolve_access_layer_from_layers():
    """Test _resolve_access_layer extracts layer UID from access-layers list."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )

    package_data = {
        "access-layers": [
            {"name": "GlobalLayer", "uid": "global-layer-uid", "domain": {"uid": "other-domain"}},
            {"name": "DomainLayer", "uid": "domain-layer-uid", "domain": {"uid": "duid"}},
        ]
    }

    result = service._resolve_access_layer(package_data)
    assert result == "domain-layer-uid"


def test_resolve_access_layer_fallback():
    """Test _resolve_access_layer falls back to access-layer field."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )

    package_data = {"access-layer": {"name": "FallbackLayer", "uid": "fallback-uid"}}

    result = service._resolve_access_layer(package_data)
    assert result == "fallback-uid"


def test_resolve_access_layer_string_fallback():
    """Test _resolve_access_layer handles string access-layer."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )

    package_data = {"access-layer": "string-layer-name"}

    result = service._resolve_access_layer(package_data)
    assert result == "string-layer-name"


def test_resolve_access_layer_none():
    """Test _resolve_access_layer returns None when no layer found."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d",
            domain_uid="duid",
            package_name="p",
            package_uid="puid",
            policies=[],
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )

    package_data = {}

    result = service._resolve_access_layer(package_data)
    assert result is None
