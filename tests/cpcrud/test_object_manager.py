"""Tests for CheckPointObjectManager."""

import pytest

from cpcrud.object_manager import CheckPointObjectManager


class TestNATSettingsTransformation:
    """Tests for _transform_nat_settings method."""

    def test_transform_nat_settings_host_static_ipv4(self):
        """Test static NAT with ipv4-address for host."""
        manager = CheckPointObjectManager(client=None)
        nat_settings = {
            "method": "static",
            "ip-address": "10.0.0.1"
        }
        result = manager._transform_nat_settings("host", nat_settings)

        assert result is not None
        assert result["nat-settings"]["method"] == "static"
        assert result["nat-settings"]["ipv4-address"] == "10.0.0.1"
        assert result["nat-settings"]["auto-rule"] is True
        assert "ip-address" not in result["nat-settings"]

    def test_transform_nat_settings_network_static(self):
        """Test static NAT with ip-address for network."""
        manager = CheckPointObjectManager(client=None)
        nat_settings = {
            "method": "static",
            "ip-address": "10.0.0.0"
        }
        result = manager._transform_nat_settings("network", nat_settings)

        assert result is not None
        assert result["nat-settings"]["method"] == "static"
        assert result["nat-settings"]["ip-address"] == "10.0.0.0"
        assert result["nat-settings"]["auto-rule"] is True
        assert "ipv4-address" not in result["nat-settings"]

    def test_transform_nat_settings_hide_gateway(self):
        """Test hide NAT with gateway."""
        manager = CheckPointObjectManager(client=None)
        nat_settings = {
            "method": "hide",
            "gateway": "gw-object"
        }
        result = manager._transform_nat_settings("host", nat_settings)

        assert result is not None
        assert result["nat-settings"]["method"] == "hide"
        assert result["nat-settings"]["install-on"] == "gw-object"
        assert result["nat-settings"]["auto-rule"] is True
        assert "gateway" not in result["nat-settings"]

    def test_transform_nat_settings_none(self):
        """Test with None NAT settings."""
        manager = CheckPointObjectManager(client=None)
        result = manager._transform_nat_settings("host", None)
        assert result is None

    def test_transform_nat_settings_preserves_auto_rule_false(self):
        """Test that explicit auto-rule false is preserved."""
        manager = CheckPointObjectManager(client=None)
        nat_settings = {
            "method": "static",
            "ipv4-address": "10.0.0.1",
            "auto-rule": False
        }
        result = manager._transform_nat_settings("host", nat_settings)

        assert result is not None
        assert result["nat-settings"]["auto-rule"] is False


class TestCheckPointRuleManager:
    """Tests for CheckPointRuleManager class."""

    def test_supported_rule_types(self):
        """Test that all expected rule types are supported."""
        from cpcrud.rule_manager import CheckPointRuleManager

        expected_types = ["access-rule", "nat-rule", "threat-prevention-rule", "https-rule"]
        for rule_type in expected_types:
            assert rule_type in CheckPointRuleManager.SUPPORTED_RULE_TYPES

    def test_create_error_result(self):
        """Test error result creation."""
        from cpcrud.rule_manager import CheckPointRuleManager

        manager = CheckPointRuleManager(client=None)
        result = manager.create_error_result(
            operation="add",
            rule_type="access-rule",
            error_msg="Test error",
            error_type="TestError",
        )

        assert "errors" in result
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error"] == "Test error"
        assert result["errors"][0]["error_type"] == "TestError"
