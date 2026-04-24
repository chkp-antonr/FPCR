"""CheckPoint Object Manager for CRUD operations on Check Point objects.

This module provides a high-level interface for managing Check Point objects
including hosts, networks, address ranges, and network groups. It abstracts
the complexity of the Check Point Management API and provides consistent
error handling and duplicate resolution strategies.
"""

from __future__ import annotations

from typing import Any

from cpaiops import CPAIOPSClient

logger = __import__("logging").getLogger(__name__)


class CheckPointObjectManager:
    """Manages CRUD operations for Check Point objects in a specific domain.

    This class provides a high-level interface for creating, reading, updating,
    and deleting Check Point objects with sophisticated duplicate handling and
    conflict resolution strategies.
    """

    # Supported object types and their mandatory fields
    SUPPORTED_OBJECT_TYPES: dict[str, dict[str, Any]] = {
        "host": {
            "mandatory_fields": ("name", "ip-address"),
            "api_command": "add-host",
            "show_command": "show-host",
            "set_command": "set-host",
            "delete_command": "delete-host",
        },
        "network": {
            "mandatory_fields": ("name", "subnet", "mask-length"),
            "api_command": "add-network",
            "show_command": "show-network",
            "set_command": "set-network",
            "delete_command": "delete-network",
        },
        "address-range": {
            "mandatory_fields": ("name", "ip-address-first", "ip-address-last"),
            "api_command": "add-address-range",
            "show_command": "show-address-range",
            "set_command": "set-address-range",
            "delete_command": "delete-address-range",
        },
        "network-group": {
            "mandatory_fields": ("name",),
            "api_command": "add-group",
            "show_command": "show-group",
            "set_command": "set-group",
            "delete_command": "delete-group",
        },
    }

    def __init__(self, client: CPAIOPSClient | None):
        """Initialize the CheckPoint Object Manager.

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
        self, operation: str, object_type: str, **kwargs: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized success result."""
        result_data = {"operation": operation, "object_type": object_type, **kwargs}
        return self._create_operation_result(success=[result_data])

    def create_error_result(
        self,
        operation: str,
        object_type: str,
        error_msg: str,
        error_type: str,
        **kwargs: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized error result for actual API failures."""
        result_data = {
            "operation": operation,
            "object_type": object_type,
            "error": error_msg,
            "error_type": error_type,
            **kwargs,
        }
        return self._create_operation_result(errors=[result_data])

    def create_warning_result(
        self,
        operation: str,
        object_type: str,
        warning_msg: str,
        warning_type: str,
        **kwargs: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        """Create a standardized warning result for intentional skips."""
        result_data = {
            "operation": operation,
            "object_type": object_type,
            "warning": warning_msg,
            "warning_type": warning_type,
            **kwargs,
        }
        return self._create_operation_result(warnings=[result_data])

    def _transform_nat_settings(
        self, object_type: str, nat_settings: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Transform NAT settings for Check Point API.

        Handles field name inconsistencies between object types.
        - host/address-range: expect 'ipv4-address'
        - network: expects 'ip-address'
        - Automatically adds 'auto-rule: true' when method is specified but auto-rule is missing

        Args:
            object_type: Type of object (host, network, address-range)
            nat_settings: NAT settings from template/user input

        Returns:
            Transformed NAT settings for API, or None if not provided
        """
        if not nat_settings:
            return None

        # Create a copy to avoid mutating input
        transformed = nat_settings.copy()

        # Map 'gateway' to 'install-on' for hide NAT
        if "gateway" in transformed:
            transformed["install-on"] = transformed.pop("gateway")

        # Add 'auto-rule: true' if method is specified but auto-rule is missing
        # Check Point API requires explicit auto-rule when using NAT methods
        if "method" in transformed and "auto-rule" not in transformed:
            transformed["auto-rule"] = True

        # Handle field name inconsistency based on object type
        # Host and address-range use 'ipv4-address', network uses 'ip-address'
        if (
            object_type in ["host", "address-range"]
            and "ip-address" in transformed
            and "ipv4-address" not in transformed
        ):
            val = transformed.pop("ip-address")
            transformed["ipv4-address"] = val
        elif (
            object_type == "network"
            and "ipv4-address" in transformed
            and "ip-address" not in transformed
        ):
            val = transformed.pop("ipv4-address")
            transformed["ip-address"] = val

        return {"nat-settings": transformed}

    async def execute(
        self,
        mgmt_name: str,
        domain: str,
        operation: str,
        obj_type: str,
        data: dict[str, Any] | None = None,
        key: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Execute a CRUD operation on a Check Point object.

        Args:
            mgmt_name: Management server name
            domain: Domain name (empty string for SMC User domain)
            operation: Operation type (add, update, delete, show)
            obj_type: Object type (host, network, address-range, network-group)
            data: Object data (for add/update operations)
            key: Object identifier (for update/delete/show operations)

        Returns:
            Operation result with success/errors/warnings lists
        """
        if obj_type not in self.SUPPORTED_OBJECT_TYPES:
            return self.create_error_result(
                operation=operation,
                object_type=obj_type,
                error_msg=f"Unsupported object type: {obj_type}",
                error_type="UnsupportedObjectType",
            )

        # Check if client is initialized
        if not self.client:
            return self.create_error_result(
                operation=operation,
                object_type=obj_type,
                error_msg="CPAIOPSClient not initialized",
                error_type="ClientNotInitialized",
            )

        commands = self.SUPPORTED_OBJECT_TYPES[obj_type]
        cmd = None
        payload = {}

        if operation == "add":
            cmd = commands["api_command"]
            if not data:
                return self.create_error_result(
                    operation=operation,
                    object_type=obj_type,
                    error_msg="Missing 'data' field for add operation",
                    error_type="MissingData",
                )
            payload = data.copy()

            # Transform NAT settings if present
            if "nat-settings" in payload:
                transformed = self._transform_nat_settings(obj_type, payload["nat-settings"])
                if transformed:
                    payload.update(transformed)
                    del payload["nat-settings"]

        elif operation == "update":
            cmd = commands["set_command"]
            if not data:
                return self.create_error_result(
                    operation=operation,
                    object_type=obj_type,
                    error_msg="Missing 'data' field for update operation",
                    error_type="MissingData",
                )
            payload = {**(key or {}), **data}

            # Transform NAT settings if present
            if "nat-settings" in payload:
                transformed = self._transform_nat_settings(obj_type, payload["nat-settings"])
                if transformed:
                    payload.update(transformed)
                    del payload["nat-settings"]

        elif operation == "delete":
            cmd = commands["delete_command"]
            payload = key or {}
        elif operation == "show":
            cmd = commands["show_command"]
            payload = key or {}
        else:
            return self.create_error_result(
                operation=operation,
                object_type=obj_type,
                error_msg=f"Unsupported operation: {operation}",
                error_type="UnsupportedOperation",
            )

        # Handle SMC User domain for SMS
        api_domain = domain if domain else "SMC User"

        try:
            response = await self.client.api_call(
                mgmt_name=mgmt_name, domain=api_domain, command=cmd, payload=payload
            )
            if response.success:
                return self._create_success_result(
                    operation=operation,
                    object_type=obj_type,
                    name=data.get("name") if data else key.get("name") if key else None,
                    uid=response.data.get("uid") if response.data else None,
                )
            else:
                return self.create_error_result(
                    operation=operation,
                    object_type=obj_type,
                    error_msg=response.message or "API call failed",
                    error_type="APIError",
                    code=response.code,
                )
        except Exception as e:
            return self.create_error_result(
                operation=operation,
                object_type=obj_type,
                error_msg=str(e),
                error_type="Exception",
            )
