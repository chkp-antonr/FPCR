"""Legacy CPCRUD module - maintained for backward compatibility.

This module now delegates to the new enhanced CPCRUD implementation.
New code should import from cpcrud.business_logic directly.
"""

import logging
from typing import Any

from cpaiops import CPAIOPSClient

from .business_logic import apply_crud_templates as new_apply_crud_templates

logger = logging.getLogger(__name__)


class CheckPointObjectManager:
    """Simplified Object Manager for CRUD operations.

    This is now a thin wrapper around the enhanced implementation.
    """

    SUPPORTED_TYPES = {
        "host": {"add": "add-host", "set": "set-host", "del": "delete-host", "show": "show-host"},
        "network": {
            "add": "add-network",
            "set": "set-network",
            "del": "delete-network",
            "show": "show-network",
        },
        "address-range": {
            "add": "add-address-range",
            "set": "set-address-range",
            "del": "delete-address-range",
            "show": "show-address-range",
        },
        "network-group": {
            "add": "add-group",
            "set": "set-group",
            "del": "delete-group",
            "show": "show-group",
        },
    }

    def __init__(self, client: CPAIOPSClient):
        self.client = client

    async def execute(
        self,
        mgmt_name: str,
        domain: str,
        operation: str,
        obj_type: str,
        data: dict[str, Any] | None = None,
        key: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Delegate to new implementation
        from .object_manager import CheckPointObjectManager as NewObjectManager

        new_manager = NewObjectManager(self.client)
        result = await new_manager.execute(mgmt_name, domain, operation, obj_type, data, key)

        # Convert new format to legacy format for backward compatibility
        if result.get("success"):
            return {
                "success": True,
                "data": result["success"][0] if result["success"] else None,
                "message": f"Successfully performed {operation} on {obj_type}",
            }
        else:
            return {
                "success": False,
                "message": result["errors"][0]["error"]
                if result.get("errors")
                else "Unknown error",
                "data": None,
            }


async def ensure_group_exists(
    manager: CheckPointObjectManager, mgmt_name: str, domain: str, group_name: str
) -> None:
    """Ensure a network group exists, create if not."""
    res = await manager.execute(
        mgmt_name, domain, "show", "network-group", key={"name": group_name}
    )
    if not res["success"]:
        logger.info(f"Creating missing group: {group_name}")
        await manager.execute(mgmt_name, domain, "add", "network-group", data={"name": group_name})


# Re-export apply_crud_templates from new implementation
apply_crud_templates = new_apply_crud_templates
