"""CheckPoint Rule Manager for CRUD operations on firewall rules.

This module provides a high-level interface for managing Check Point firewall
rules including access rules, NAT rules, threat prevention rules, and HTTPS rules.
It abstracts the complexity of the Check Point Management API and provides consistent
error handling and positioning support.
"""

from __future__ import annotations

from typing import Any

from cpaiops import CPAIOPSClient

from cpcrud.position_helper import PositionHelper

logger = __import__("logging").getLogger(__name__)


class CheckPointRuleManager:
    """Manages CRUD operations for Check Point firewall rules.

    This class provides a high-level interface for creating, reading, updating,
    and deleting Check Point firewall rules with positioning support and
    consistent error handling.
    """

    # Supported rule types and their configuration
    SUPPORTED_RULE_TYPES: dict[str, dict[str, Any]] = {
        "access-rule": {
            "mandatory_fields": ("name", "layer"),
            "api_command": "add-access-rule",
            "show_command": "show-access-rule",
            "set_command": "set-access-rule",
            "delete_command": "delete-access-rule",
            "container_type": "layer",
        },
        "nat-rule": {
            "mandatory_fields": ("package",),
            "api_command": "add-nat-rule",
            "show_command": "show-nat-rule",
            "set_command": "set-nat-rule",
            "delete_command": "delete-nat-rule",
            "container_type": "package",
        },
        "threat-prevention-rule": {
            "mandatory_fields": ("name", "layer"),
            "api_command": "add-threat-rule",
            "show_command": "show-threat-rule",
            "set_command": "set-threat-rule",
            "delete_command": "delete-threat-rule",
            "container_type": "layer",
        },
        "https-rule": {
            "mandatory_fields": ("name", "layer"),
            "api_command": "add-https-rule",
            "show_command": "show-https-rule",
            "set_command": "set-https-rule",
            "delete_command": "delete-https-rule",
            "container_type": "layer",
        },
    }

    def __init__(self, client: CPAIOPSClient | None):
        """Initialize the CheckPoint Rule Manager.

        Args:
            client: CPAIOPSClient instance for API communication.
        """
        self.client = client
        self.logger = logger

    def _create_operation_result(
        self,
        success: list[dict[str, Any]] | None = None,
        errors: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized operation result dictionary."""
        return {"success": success or [], "errors": errors or [], "warnings": warnings or []}

    def _create_success_result(
        self, operation: str, rule_type: str, **kwargs: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized success result."""
        result_data = {"operation": operation, "rule_type": rule_type, **kwargs}
        return self._create_operation_result(success=[result_data])

    def create_error_result(
        self,
        operation: str,
        rule_type: str,
        error_msg: str,
        error_type: str,
        **kwargs: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized error result for actual API failures."""
        result_data = {
            "operation": operation,
            "rule_type": rule_type,
            "error": error_msg,
            "error_type": error_type,
            **kwargs,
        }
        return self._create_operation_result(errors=[result_data])

    def create_warning_result(
        self,
        operation: str,
        rule_type: str,
        warning_msg: str,
        warning_type: str,
        **kwargs: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized warning result for intentional skips."""
        result_data = {
            "operation": operation,
            "rule_type": rule_type,
            "warning": warning_msg,
            "warning_type": warning_type,
            **kwargs,
        }
        return self._create_operation_result(warnings=[result_data])

    async def add(
        self,
        mgmt_name: str,
        domain: str,
        rule_type: str,
        data: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Add a new firewall rule.

        Args:
            mgmt_name: Management server name
            domain: Domain name (empty string for SMC User domain)
            rule_type: Type of rule (access-rule, nat-rule, etc.)
            data: Rule data including position information

        Returns:
            Operation result with success/errors/warnings lists
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="add",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleType",
            )

        # Check if client is initialized
        if not self.client:
            return self.create_error_result(
                operation="add",
                rule_type=rule_type,
                error_msg="CPAIOPSClient not initialized",
                error_type="ClientNotInitialized",
            )

        rule_config = self.SUPPORTED_RULE_TYPES[rule_type]

        # Validate mandatory fields
        for field in rule_config["mandatory_fields"]:
            if field not in data:
                return self.create_error_result(
                    operation="add",
                    rule_type=rule_type,
                    error_msg=f"Missing mandatory field: {field}",
                    error_type="MissingMandatoryField",
                )

        # Validate position if provided
        if "position" in data:
            try:
                PositionHelper.validate_position(data["position"])
            except ValueError as e:
                return self.create_error_result(
                    operation="add",
                    rule_type=rule_type,
                    error_msg=f"Invalid position: {e}",
                    error_type="InvalidPosition",
                )

        # Prepare payload
        payload = data.copy()

        # Handle SMC User domain for SMS
        api_domain = domain if domain else "SMC User"

        try:
            response = await self.client.api_call(
                mgmt_name=mgmt_name,
                domain=api_domain,
                command=rule_config["api_command"],
                payload=payload,
            )
            if response.success:
                return self._create_success_result(
                    operation="add",
                    rule_type=rule_type,
                    name=data.get("name"),
                    uid=response.data.get("uid") if response.data else None,
                )
            else:
                return self.create_error_result(
                    operation="add",
                    rule_type=rule_type,
                    error_msg=response.message or "API call failed",
                    error_type="APIError",
                    code=response.code,
                )
        except Exception as e:
            return self.create_error_result(
                operation="add",
                rule_type=rule_type,
                error_msg=str(e),
                error_type="Exception",
            )

    async def update(
        self,
        mgmt_name: str,
        domain: str,
        rule_type: str,
        data: dict[str, Any],
        key: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Update an existing firewall rule.

        Args:
            mgmt_name: Management server name
            domain: Domain name (empty string for SMC User domain)
            rule_type: Type of rule (access-rule, nat-rule, etc.)
            data: Rule data to update
            key: Rule identifier (e.g., uid, name, layer/rule number)

        Returns:
            Operation result with success/errors/warnings lists
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="update",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleType",
            )

        # Check if client is initialized
        if not self.client:
            return self.create_error_result(
                operation="update",
                rule_type=rule_type,
                error_msg="CPAIOPSClient not initialized",
                error_type="ClientNotInitialized",
            )

        rule_config = self.SUPPORTED_RULE_TYPES[rule_type]

        # Validate position if provided
        if "position" in data:
            try:
                PositionHelper.validate_position(data["position"])
            except ValueError as e:
                return self.create_error_result(
                    operation="update",
                    rule_type=rule_type,
                    error_msg=f"Invalid position: {e}",
                    error_type="InvalidPosition",
                )

        # Prepare payload
        payload = {**key, **data}

        # Handle SMC User domain for SMS
        api_domain = domain if domain else "SMC User"

        try:
            response = await self.client.api_call(
                mgmt_name=mgmt_name,
                domain=api_domain,
                command=rule_config["set_command"],
                payload=payload,
            )
            if response.success:
                return self._create_success_result(
                    operation="update",
                    rule_type=rule_type,
                    name=key.get("name") or data.get("name"),
                    uid=response.data.get("uid") if response.data else None,
                )
            else:
                return self.create_error_result(
                    operation="update",
                    rule_type=rule_type,
                    error_msg=response.message or "API call failed",
                    error_type="APIError",
                    code=response.code,
                )
        except Exception as e:
            return self.create_error_result(
                operation="update",
                rule_type=rule_type,
                error_msg=str(e),
                error_type="Exception",
            )

    async def delete(
        self,
        mgmt_name: str,
        domain: str,
        rule_type: str,
        key: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Delete a firewall rule.

        Args:
            mgmt_name: Management server name
            domain: Domain name (empty string for SMC User domain)
            rule_type: Type of rule (access-rule, nat-rule, etc.)
            key: Rule identifier (e.g., uid, name, layer/rule number)

        Returns:
            Operation result with success/errors/warnings lists
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="delete",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleType",
            )

        # Check if client is initialized
        if not self.client:
            return self.create_error_result(
                operation="delete",
                rule_type=rule_type,
                error_msg="CPAIOPSClient not initialized",
                error_type="ClientNotInitialized",
            )

        rule_config = self.SUPPORTED_RULE_TYPES[rule_type]

        # Handle SMC User domain for SMS
        api_domain = domain if domain else "SMC User"

        try:
            response = await self.client.api_call(
                mgmt_name=mgmt_name,
                domain=api_domain,
                command=rule_config["delete_command"],
                payload=key,
            )
            if response.success:
                return self._create_success_result(
                    operation="delete",
                    rule_type=rule_type,
                    name=key.get("name"),
                )
            else:
                return self.create_error_result(
                    operation="delete",
                    rule_type=rule_type,
                    error_msg=response.message or "API call failed",
                    error_type="APIError",
                    code=response.code,
                )
        except Exception as e:
            return self.create_error_result(
                operation="delete",
                rule_type=rule_type,
                error_msg=str(e),
                error_type="Exception",
            )

    async def show(
        self,
        mgmt_name: str,
        domain: str,
        rule_type: str,
        key: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Show a firewall rule.

        Args:
            mgmt_name: Management server name
            domain: Domain name (empty string for SMC User domain)
            rule_type: Type of rule (access-rule, nat-rule, etc.)
            key: Rule identifier (e.g., uid, name, layer/rule number)

        Returns:
            Operation result with success/errors/warnings lists
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="show",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleType",
            )

        # Check if client is initialized
        if not self.client:
            return self.create_error_result(
                operation="show",
                rule_type=rule_type,
                error_msg="CPAIOPSClient not initialized",
                error_type="ClientNotInitialized",
            )

        rule_config = self.SUPPORTED_RULE_TYPES[rule_type]

        # Handle SMC User domain for SMS
        api_domain = domain if domain else "SMC User"

        try:
            response = await self.client.api_call(
                mgmt_name=mgmt_name,
                domain=api_domain,
                command=rule_config["show_command"],
                payload=key,
            )
            if response.success:
                return self._create_success_result(
                    operation="show",
                    rule_type=rule_type,
                    name=key.get("name"),
                    data=response.data,
                )
            else:
                return self.create_error_result(
                    operation="show",
                    rule_type=rule_type,
                    error_msg=response.message or "API call failed",
                    error_type="APIError",
                    code=response.code,
                )
        except Exception as e:
            return self.create_error_result(
                operation="show",
                rule_type=rule_type,
                error_msg=str(e),
                error_type="Exception",
            )
