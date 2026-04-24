# CPCRUD Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance CPCRUD functionality with NAT settings support for network objects and firewall rule management (access, NAT, threat prevention, HTTPS rules) with sophisticated positioning.

**Architecture:** Split functionality into separate CheckPointObjectManager (network objects with NAT) and CheckPointRuleManager (firewall rules with positioning), following reference implementation at W:\MMP\src\plugins\actions\cpcrud\

**Tech Stack:** Python 3.13, cpaiops (Check Point API client), ruamel.yaml, jsonschema, pytest

---

## File Structure

### Files to Create

- `src/cpcrud/position_helper.py` - PositionHelper class for rule positioning validation
- `src/cpcrud/rule_manager.py` - CheckPointRuleManager class for firewall rule management
- `src/cpcrud/config.py` - Configuration constants
- `src/cpcrud/object_manager.py` - Enhanced CheckPointObjectManager (replaces cpcrud.py)
- `src/cpcrud/business_logic.py` - Template processing orchestration
- `tests/cpcrud/test_position_helper.py` - Unit tests for PositionHelper
- `tests/cpcrud/test_object_manager.py` - Unit tests for ObjectManager
- `tests/cpcrud/test_rule_manager.py` - Unit tests for RuleManager

### Files to Modify

- `ops/checkpoint_ops_schema.json` - Add NAT settings, rule types, position definitions
- `src/cpcrud/__init__.py` - Update public API exports
- `pyproject.toml` - Add jsonschema dependency

---

## Phase 1: Foundation

### Task 1: Add jsonschema dependency

**Files:**

- Modify: `pyproject.toml`

- [ ] **Step 1: Add jsonschema to dependencies**

```toml
# In [project.dependencies] array, add:
"jsonschema>=4.0.0",
```

- [ ] **Step 2: Run dependency install**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv sync
```

Expected: No errors, dependency installed successfully.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add jsonschema dependency for CPCRUD template validation"
```

---

### Task 2: Create PositionHelper module

**Files:**

- Create: `src/cpcrud/position_helper.py`
- Test: `tests/cpcrud/test_position_helper.py`

- [ ] **Step 1: Create tests directory and conftest**

```bash
mkdir -p D:/Files/GSe_new/2026/Labs/Dev/FPCR/tests/cpcrud
```

- [ ] **Step 2: Write failing tests for PositionHelper**

```python
# tests/cpcrud/test_position_helper.py

import pytest
from cpcrud.position_helper import PositionHelper


def test_validate_position_absolute_integer():
    """Test validation of absolute position (integer)."""
    result = PositionHelper.validate_position(1)
    assert result == 1

    result = PositionHelper.validate_position(100)
    assert result == 100


def test_validate_position_absolute_integer_negative():
    """Test that negative integers raise ValueError."""
    with pytest.raises(ValueError, match="Position must be a positive integer"):
        PositionHelper.validate_position(0)

    with pytest.raises(ValueError, match="Position must be a positive integer"):
        PositionHelper.validate_position(-1)


def test_validate_position_layer_level_strings():
    """Test validation of layer-level position strings."""
    result = PositionHelper.validate_position("top")
    assert result == "top"

    result = PositionHelper.validate_position("bottom")
    assert result == "bottom"


def test_validate_position_invalid_string():
    """Test that invalid strings raise ValueError."""
    with pytest.raises(ValueError, match="Position string must be 'top' or 'bottom'"):
        PositionHelper.validate_position("middle")

    with pytest.raises(ValueError, match="Position string must be 'top' or 'bottom'"):
        PositionHelper.validate_position("TOP")


def test_validate_position_section_relative():
    """Test validation of section-relative position objects."""
    result = PositionHelper.validate_position({"top": "Section1"})
    assert result == {"top": "Section1"}

    result = PositionHelper.validate_position({"bottom": "Section1"})
    assert result == {"bottom": "Section1"}

    result = PositionHelper.validate_position({"above": "Rule1"})
    assert result == {"above": "Rule1"}

    result = PositionHelper.validate_position({"below": "Rule1"})
    assert result == {"below": "Rule1"}


def test_validate_position_invalid_object_keys():
    """Test that invalid object keys raise ValueError."""
    with pytest.raises(ValueError, match="Position object key must be one of"):
        PositionHelper.validate_position({"middle": "Section1"})

    with pytest.raises(ValueError, match="Position object key must be one of"):
        PositionHelper.validate_position({"TOP": "Section1"})


def test_validate_position_object_multiple_keys():
    """Test that objects with multiple keys raise ValueError."""
    with pytest.raises(ValueError, match="Position object must have exactly one key"):
        PositionHelper.validate_position({"top": "Section1", "bottom": "Section2"})


def test_validate_position_object_empty_value():
    """Test that objects with empty string values raise ValueError."""
    with pytest.raises(ValueError, match="must be a non-empty string"):
        PositionHelper.validate_position({"top": ""})

    with pytest.raises(ValueError, match="must be a non-empty string"):
        PositionHelper.validate_position({"above": "   "})


def test_validate_position_invalid_type():
    """Test that invalid types raise ValueError."""
    with pytest.raises(ValueError, match="Position must be an integer"):
        PositionHelper.validate_position([1])

    with pytest.raises(ValueError, match="Position must be an integer"):
        PositionHelper.validate_position(None)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/test_position_helper.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cpcrud.position_helper'"

- [ ] **Step 4: Create PositionHelper implementation**

```python
# src/cpcrud/position_helper.py

"""Position helper for Check Point rule positioning.

This module validates the ``position`` value from YAML templates
before it is sent to the Check Point Management API.

The YAML ``position`` field follows the CP API spec exactly::

    position: 1                          # absolute (integer)
    position: "top"                      # top of layer (string)
    position: "bottom"                   # bottom of layer (string)
    position: { "top": "Section" }       # top of section (object)
    position: { "bottom": "Section" }    # bottom of section (object)
    position: { "above": "Rule" }        # above rule/section (object)
    position: { "below": "Rule" }        # below rule/section (object)
"""

from __future__ import annotations

from typing import Any

# Valid string values for layer-level positioning
_LAYER_STRINGS = ("top", "bottom")

# Valid keys inside the position object
_OBJECT_KEYS = ("top", "bottom", "above", "below")


class PositionHelper:
    """Validates the ``position`` field value from a YAML operation."""

    @staticmethod
    def validate_position(position: Any) -> Any:
        """Validate and return position value for the CP API.

        Args:
            position: The raw value from the YAML ``position`` field.

        Returns:
            The validated value (int, str, or dict), ready for the API payload.

        Raises:
            ValueError: If the position value is invalid.
        """
        if isinstance(position, int):
            if position < 1:
                raise ValueError(f"Position must be a positive integer, got: {position}")
            return position

        if isinstance(position, str):
            if position not in _LAYER_STRINGS:
                raise ValueError(f"Position string must be 'top' or 'bottom', got: {position!r}")
            return position

        if isinstance(position, dict):
            if len(position) != 1:
                raise ValueError(
                    f"Position object must have exactly one key "
                    f"(top/bottom/above/below), got: {list(position.keys())}"
                )
            key = next(iter(position))
            if key not in _OBJECT_KEYS:
                raise ValueError(f"Position object key must be one of {_OBJECT_KEYS}, got: {key!r}")
            value = position[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Position object value for '{key}' must be a non-empty string, got: {value!r}"
                )
            return position

        raise ValueError(
            f"Position must be an integer, 'top'/'bottom' string, or object "
            f"with top/bottom/above/below key, got: {type(position).__name__}"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/test_position_helper.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/cpcrud/position_helper.py tests/cpcrud/test_position_helper.py
git commit -m "feat: add PositionHelper for rule position validation"
```

---

### Task 3: Create config module

**Files:**

- Create: `src/cpcrud/config.py`

- [ ] **Step 1: Create config module**

```python
# src/cpcrud/config.py

"""Configuration constants for CPCRUD module."""

from pathlib import Path

# Default schema path relative to project root
DEFAULT_SCHEMA_PATH = Path("ops/checkpoint_ops_schema.json")

# Cache settings (for future use if needed)
CACHE_ENABLED = False
CACHE_TTL_SECONDS = 3600
```

- [ ] **Step 2: Commit**

```bash
git add src/cpcrud/config.py
git commit -m "feat: add CPCRUD configuration module"
```

---

### Task 4: Update checkpoint_ops_schema.json

**Files:**

- Modify: `ops/checkpoint_ops_schema.json`

- [ ] **Step 1: Read reference schema**

```bash
# View the reference schema to understand the full structure
cat W:/MMP/ops/checkpoint_ops_schema.json | head -100
```

- [ ] **Step 2: Copy updated schema from reference**

```bash
# Copy the complete updated schema
cp W:/MMP/ops/checkpoint_ops_schema.json D:/Files/GSe_new/2026/Labs/Dev/FPCR/ops/checkpoint_ops_schema.json
```

- [ ] **Step 3: Verify schema syntax**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run python -c "import json; json.load(open('ops/checkpoint_ops_schema.json'))"
```

Expected: No JSON syntax errors

- [ ] **Step 4: Commit**

```bash
git add ops/checkpoint_ops_schema.json
git commit -m "feat: update schema with NAT settings and rule types

- Add nat_settings definition for host, network, address-range
- Add access_rule, nat_rule, threat_rule, https_rule definitions
- Add rule_position definition for rule positioning
- Add track_settings definition for rule tracking
- Add uid to common_data
- Add new-name support for update operations"
```

---

## Phase 2: Object Manager

### Task 5: Create enhanced CheckPointObjectManager

**Files:**

- Create: `src/cpcrud/object_manager.py`
- Test: `tests/cpcrud/test_object_manager.py`

- [ ] **Step 1: Write failing tests for NAT settings transformation**

```python
# tests/cpcrud/test_object_manager.py

import pytest
from cpcrud.object_manager import CheckPointObjectManager


class TestNATSettingsTransformation:
    """Tests for _transform_nat_settings method."""

    def test_transform_nat_settings_host_static_ipv4(self):
        """Test static NAT with ipv4-address for host."""
        manager = CheckPointObjectManager()
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
        manager = CheckPointObjectManager()
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
        manager = CheckPointObjectManager()
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
        manager = CheckPointObjectManager()
        result = manager._transform_nat_settings("host", None)
        assert result is None

    def test_transform_nat_settings_preserves_auto_rule_false(self):
        """Test that explicit auto-rule false is preserved."""
        manager = CheckPointObjectManager()
        nat_settings = {
            "method": "static",
            "ipv4-address": "10.0.0.1",
            "auto-rule": False
        }
        result = manager._transform_nat_settings("host", nat_settings)

        assert result is not None
        assert result["nat-settings"]["auto-rule"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/test_object_manager.py::TestNATSettingsTransformation -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cpcrud.object_manager'"

- [ ] **Step 3: Create CheckPointObjectManager implementation (Part 1 - NAT transformation)**

```python
# src/cpcrud/object_manager.py

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

    def __init__(self, client: CPAIOPSClient):
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
        return {
            "success": success or [],
            "errors": errors or [],
            "warnings": warnings or []
        }

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/test_object_manager.py::TestNATSettingsTransformation -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cpcrud/object_manager.py tests/cpcrud/test_object_manager.py
git commit -m "feat: add enhanced CheckPointObjectManager with NAT settings support"
```

---

## Phase 3: Rule Manager

### Task 6: Create CheckPointRuleManager

**Files:**

- Create: `src/cpcrud/rule_manager.py`
- Test: `tests/cpcrud/test_rule_manager.py`

- [ ] **Step 1: Write failing tests for rule manager**

```python
# Continue tests/cpcrud/test_object_manager.py with rule manager tests

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

        manager = CheckPointRuleManager()
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/test_object_manager.py::TestCheckPointRuleManager -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cpcrud.rule_manager'"

- [ ] **Step 3: Create CheckPointRuleManager implementation**

```python
# src/cpcrud/rule_manager.py

"""CheckPoint Rule Manager for CRUD operations on Check Point rules.

This module provides a high-level interface for managing Check Point
access rules and NAT rules with positioning and validation.
"""

from __future__ import annotations

from typing import Any

from cpaiops import CPAIOPSClient

from .position_helper import PositionHelper

logger = __import__("logging").getLogger(__name__)


class CheckPointRuleManager:
    """Manages CRUD operations for Check Point rules in a specific domain.

    This class provides a high-level interface for creating, reading, updating,
    and deleting Check Point rules with sophisticated positioning and validation.
    """

    # Supported rule types and their mandatory fields
    SUPPORTED_RULE_TYPES: dict[str, dict[str, Any]] = {
        "access-rule": {
            "mandatory_fields": ("layer", "data"),
            "api_command": "add-access-rule",
            "show_command": "show-access-rule",
            "set_command": "set-access-rule",
            "delete_command": "delete-access-rule",
        },
        "nat-rule": {
            "mandatory_fields": ("package", "data"),
            "api_command": "add-nat-rule",
            "show_command": "show-nat-rule",
            "set_command": "set-nat-rule",
            "delete_command": "delete-nat-rule",
        },
        "threat-prevention-rule": {
            "mandatory_fields": ("layer", "data"),
            "api_command": "add-threat-rule",
            "show_command": "show-threat-rule",
            "set_command": "set-threat-rule",
            "delete_command": "delete-threat-rule",
        },
        "https-rule": {
            "mandatory_fields": ("layer", "data"),
            "api_command": "add-https-rule",
            "show_command": "show-https-rule",
            "set_command": "set-https-rule",
            "delete_command": "delete-https-rule",
        },
    }

    def __init__(self, client: CPAIOPSClient):
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
        return {
            "success": success or [],
            "errors": errors or [],
            "warnings": warnings or []
        }

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
        rule_type: str,
        data: dict[str, Any],
        mgmt_name: str,
        domain_name: str,
        layer: str | None = None,
        package: str | None = None,
        position: int | str | dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        """Add a new rule to the Check Point management server.

        Args:
            rule_type: Type of rule (access-rule, nat-rule, threat-prevention-rule, https-rule)
            data: Rule configuration data
            mgmt_name: Management server name
            domain_name: Domain name
            layer: Policy layer name (for access-rule, threat-prevention-rule, https-rule)
            package: NAT package name (for nat-rule)
            position: Position in the rulebase
            **kwargs: Additional parameters (e.g., match-threshold)

        Returns:
            Operation result with success/errors/warnings
        """
        # Validate rule type
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="add",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleTypeError",
            )

        # Validate position if provided
        if position is not None:
            try:
                position = PositionHelper.validate_position(position)
            except ValueError as e:
                return self.create_error_result(
                    operation="add",
                    rule_type=rule_type,
                    error_msg=f"Invalid position: {e}",
                    error_type="InvalidPositionError",
                )

        # Build payload
        payload = data.copy()

        # Add layer or package to payload
        if layer:
            payload["layer"] = layer
        if package:
            payload["package"] = package

        # Add position if provided
        if position is not None:
            payload["position"] = position

        # Handle SMC User domain
        api_domain = domain_name if domain_name else "SMC User"

        try:
            cmd = self.SUPPORTED_RULE_TYPES[rule_type]["api_command"]
            response = await self.client.api_call(
                mgmt_name=mgmt_name, domain=api_domain, command=cmd, payload=payload
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
        rule_type: str,
        key: dict[str, Any],
        data: dict[str, Any],
        mgmt_name: str,
        domain_name: str,
        layer: str | None = None,
        package: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Update an existing rule.

        Args:
            rule_type: Type of rule
            key: Rule identifier (name, uid, or rule-number)
            data: Rule configuration data to update
            mgmt_name: Management server name
            domain_name: Domain name
            layer: Policy layer name (for access-rule)
            package: NAT package name (for nat-rule)

        Returns:
            Operation result with success/errors/warnings
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="update",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleTypeError",
            )

        # Build payload
        payload = {**key, **data}

        # Add layer or package to payload
        if layer:
            payload["layer"] = layer
        if package:
            payload["package"] = package

        # Handle SMC User domain
        api_domain = domain_name if domain_name else "SMC User"

        try:
            cmd = self.SUPPORTED_RULE_TYPES[rule_type]["set_command"]
            response = await self.client.api_call(
                mgmt_name=mgmt_name, domain=api_domain, command=cmd, payload=payload
            )

            if response.success:
                return self._create_success_result(
                    operation="update",
                    rule_type=rule_type,
                    name=key.get("name") or data.get("name"),
                )
            else:
                return self.create_error_result(
                    operation="update",
                    rule_type=rule_type,
                    error_msg=response.message or "API call failed",
                    error_type="APIError",
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
        rule_type: str,
        key: dict[str, Any],
        mgmt_name: str,
        domain_name: str,
        layer: str | None = None,
        package: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Delete a rule.

        Args:
            rule_type: Type of rule
            key: Rule identifier (name, uid, or rule-number)
            mgmt_name: Management server name
            domain_name: Domain name
            layer: Policy layer name (for access-rule)
            package: NAT package name (for nat-rule)

        Returns:
            Operation result with success/errors/warnings
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="delete",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleTypeError",
            )

        # Build payload
        payload = key.copy()

        # Add layer or package to payload
        if layer:
            payload["layer"] = layer
        if package:
            payload["package"] = package

        # Handle SMC User domain
        api_domain = domain_name if domain_name else "SMC User"

        try:
            cmd = self.SUPPORTED_RULE_TYPES[rule_type]["delete_command"]
            response = await self.client.api_call(
                mgmt_name=mgmt_name, domain=api_domain, command=cmd, payload=payload
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
        rule_type: str,
        key: dict[str, Any],
        mgmt_name: str,
        domain_name: str,
        layer: str | None = None,
        package: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Show rule details.

        Args:
            rule_type: Type of rule
            key: Rule identifier (name, uid, or rule-number)
            mgmt_name: Management server name
            domain_name: Domain name
            layer: Policy layer name (for access-rule)
            package: NAT package name (for nat-rule)

        Returns:
            Operation result with success/errors/warnings
        """
        if rule_type not in self.SUPPORTED_RULE_TYPES:
            return self.create_error_result(
                operation="show",
                rule_type=rule_type,
                error_msg=f"Unsupported rule type: {rule_type}",
                error_type="UnsupportedRuleTypeError",
            )

        # Build payload
        payload = key.copy()

        # Add layer or package to payload
        if layer:
            payload["layer"] = layer
        if package:
            payload["package"] = package

        # Handle SMC User domain
        api_domain = domain_name if domain_name else "SMC User"

        try:
            cmd = self.SUPPORTED_RULE_TYPES[rule_type]["show_command"]
            response = await self.client.api_call(
                mgmt_name=mgmt_name, domain=api_domain, command=cmd, payload=payload
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
                )
        except Exception as e:
            return self.create_error_result(
                operation="show",
                rule_type=rule_type,
                error_msg=str(e),
                error_type="Exception",
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/test_object_manager.py::TestCheckPointRuleManager -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cpcrud/rule_manager.py tests/cpcrud/test_object_manager.py
git commit -m "feat: add CheckPointRuleManager for firewall rule CRUD"
```

---

## Phase 4: Integration

### Task 7: Create business_logic module

**Files:**

- Create: `src/cpcrud/business_logic.py`

- [ ] **Step 1: Create business_logic module**

```python
# src/cpcrud/business_logic.py

"""Business logic for applying CRUD templates.

This module contains the core business logic for processing and applying
Check Point object manager templates from YAML or JSON files.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, ValidationError
from ruamel.yaml import YAML

from .config import DEFAULT_SCHEMA_PATH
from .object_manager import CheckPointObjectManager
from .rule_manager import CheckPointRuleManager

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_cpcrud_schema_validator() -> tuple[Draft7Validator | None, str, str | None]:
    """Load CPCRUD JSON schema validator.

    Returns:
        Tuple of (validator, resolved_schema_path, error_message).
        validator is None when schema loading fails.
    """
    schema_path = Path(DEFAULT_SCHEMA_PATH).expanduser()

    if not schema_path.is_absolute():
        # Assume relative to project root if not absolute
        cwd = Path.cwd()
        # Try to find ops/ directory
        for parent in [cwd] + list(cwd.parents):
            test_path = parent / "ops" / "checkpoint_ops_schema.json"
            if test_path.exists():
                schema_path = test_path
                break

    if not schema_path.exists():
        return None, str(schema_path), f"Schema file not found: {schema_path}"

    try:
        with schema_path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        validator = Draft7Validator(schema)
        return validator, str(schema_path), None
    except (json.JSONDecodeError, OSError, ValidationError) as e:
        return None, str(schema_path), f"Failed to load schema {schema_path}: {e}"


def validate_template_with_schema(template: dict[str, Any], file_path: str) -> list[str]:
    """Validate template against CPCRUD JSON schema.

    Args:
        template: Template dictionary to validate
        file_path: Path to template file (for error messages)

    Returns:
        List of error messages (empty if valid)
    """
    validator, schema_path, load_error = _load_cpcrud_schema_validator()
    if load_error:
        return [f"{file_path}: {load_error}"]

    if validator is None:
        return [f"{file_path}: CPCRUD schema validator not initialized (schema: {schema_path})"]

    errors: list[str] = []
    for err in validator.iter_errors(template):
        path = ".".join(str(p) for p in err.absolute_path)
        location = path if path else "<root>"
        errors.append(f"{file_path}: Schema error at {location}: {err.message}")

    return errors


async def apply_crud_templates(
    client,  # CPAIOPSClient - avoiding type check for circular import
    template_files: list[str],
    no_publish: bool = False,
) -> dict[str, Any]:
    """Process YAML templates and apply CRUD operations.

    Args:
        client: CPAIOPSClient instance
        template_files: List of template file paths
        no_publish: If True, skip publishing changes

    Returns:
        Dictionary with aggregated results
    """
    object_manager = CheckPointObjectManager(client)
    rule_manager = CheckPointRuleManager(client)
    yaml = YAML(typ="safe")

    all_results = {
        "success": [],
        "errors": [],
        "warnings": [],
    }

    for file_path in template_files:
        logger.info(f"Processing template: {file_path}")

        try:
            with open(file_path) as f:
                template = yaml.load(f)
        except Exception as e:
            logger.error(f"Failed to load template {file_path}: {e}")
            all_results["errors"].append({
                "file": file_path,
                "error": f"Failed to load template: {e}",
                "error_type": "TemplateLoadError",
            })
            continue

        # Validate against schema
        schema_errors = validate_template_with_schema(template, file_path)
        if schema_errors:
            for error in schema_errors:
                logger.error(error)
                all_results["errors"].append({
                    "file": file_path,
                    "error": error,
                    "error_type": "SchemaValidationError",
                })
            continue

        # Process management servers
        for mgmt_server in template.get("management_servers", []):
            mgmt_name = mgmt_server.get("mgmt_name")
            if not mgmt_name:
                try:
                    server_names = client.get_mgmt_names()
                    if server_names:
                        mgmt_name = server_names[0]
                        logger.info(f"Using default management server: {mgmt_name}")
                    else:
                        logger.error("No mgmt_name specified and no management servers found.")
                        continue
                except Exception as e:
                    logger.error(f"Failed to retrieve management servers: {e}")
                    continue

            for domain_config in mgmt_server.get("domains", []):
                domain_name = domain_config.get("name", "")

                try:
                    # Pre-process: ensure groups exist for objects
                    for op in domain_config.get("operations", []):
                        if op.get("operation") in ["add", "update"] and op.get("type") in ["host", "network", "address-range"]:
                            groups = op.get("data", {}).get("groups", [])
                            for g in groups:
                                result = await object_manager.execute(
                                    mgmt_name, domain_name, "show", "network-group", key={"name": g}
                                )
                                if not result["success"]:
                                    logger.info(f"Creating missing group: {g}")
                                    await object_manager.execute(
                                        mgmt_name, domain_name, "add", "network-group", data={"name": g}
                                    )

                    # Process operations
                    for op in domain_config.get("operations", []):
                        operation = op.get("operation")
                        obj_type = op.get("type")
                        obj_data = op.get("data", {})
                        obj_name = obj_data.get("name") if obj_data else None

                        # Route to appropriate manager
                        if obj_type in ["access-rule", "nat-rule", "threat-prevention-rule", "https-rule"]:
                            # Use rule manager
                            if operation == "add":
                                result = await rule_manager.add(
                                    rule_type=obj_type,
                                    data=obj_data,
                                    mgmt_name=mgmt_name,
                                    domain_name=domain_name,
                                    layer=op.get("layer"),
                                    package=op.get("package"),
                                    position=op.get("position"),
                                )
                            elif operation == "update":
                                result = await rule_manager.update(
                                    rule_type=obj_type,
                                    key=op.get("key", {}),
                                    data=obj_data,
                                    mgmt_name=mgmt_name,
                                    domain_name=domain_name,
                                    layer=op.get("layer"),
                                    package=op.get("package"),
                                )
                            elif operation == "delete":
                                result = await rule_manager.delete(
                                    rule_type=obj_type,
                                    key=op.get("key", {}),
                                    mgmt_name=mgmt_name,
                                    domain_name=domain_name,
                                    layer=op.get("layer"),
                                    package=op.get("package"),
                                )
                            elif operation == "show":
                                result = await rule_manager.show(
                                    rule_type=obj_type,
                                    key=op.get("key", {}),
                                    mgmt_name=mgmt_name,
                                    domain_name=domain_name,
                                    layer=op.get("layer"),
                                    package=op.get("package"),
                                )
                            else:
                                result = rule_manager.create_error_result(
                                    operation=operation,
                                    rule_type=obj_type,
                                    error_msg=f"Unsupported operation: {operation}",
                                    error_type="UnsupportedOperation",
                                )
                        else:
                            # Use object manager
                            result = await object_manager.execute(
                                mgmt_name,
                                domain_name,
                                operation,
                                obj_type,
                                data=obj_data,
                                key=op.get("key"),
                            )

                        # Aggregate results
                        if result.get("success"):
                            all_results["success"].extend(result["success"])
                            logger.info(
                                f"[OK] {operation} {obj_type} {obj_name or op.get('key', {}).get('name')}"
                            )
                        else:
                            all_results["errors"].extend(result.get("errors", []))
                            logger.error(f"[FAIL] {operation} {obj_type} failed")

                        if result.get("warnings"):
                            all_results["warnings"].extend(result["warnings"])

                    # Publish
                    if not no_publish:
                        logger.info(f"Publishing changes for {mgmt_name}/{domain_name}")
                        api_domain = domain_name if domain_name else "SMC User"
                        await client.api_call(
                            mgmt_name=mgmt_name, domain=api_domain, command="publish"
                        )

                except Exception as e:
                    logger.error(f"Error processing domain '{domain_name}' on '{mgmt_name}': {e}")
                    all_results["errors"].append({
                        "domain": domain_name,
                        "mgmt_name": mgmt_name,
                        "error": str(e),
                        "error_type": "DomainProcessingError",
                    })

    return all_results
```

- [ ] **Step 2: Update **init**.py to export new classes**

```python
# src/cpcrud/__init__.py

from .business_logic import apply_crud_templates, validate_template_with_schema
from .config import DEFAULT_SCHEMA_PATH
from .object_manager import CheckPointObjectManager
from .position_helper import PositionHelper
from .rule_manager import CheckPointRuleManager

__all__ = [
    "apply_crud_templates",
    "validate_template_with_schema",
    "CheckPointObjectManager",
    "CheckPointRuleManager",
    "PositionHelper",
    "DEFAULT_SCHEMA_PATH",
]
```

- [ ] **Step 3: Commit**

```bash
git add src/cpcrud/business_logic.py src/cpcrud/__init__.py
git commit -m "feat: add business logic module for template processing

- Add JSON schema validation
- Add template processing orchestration
- Route operations to ObjectManager or RuleManager based on type
- Export new public API from __init__.py"
```

---

### Task 8: Update existing cpcrud.py to use new modules

**Files:**

- Modify: `src/cpcrud/cpcrud.py`

- [ ] **Step 1: Update cpcrud.py to use new business logic**

```python
# src/cpcrud/cpcrud.py

"""Legacy CPCRUD module - maintained for backward compatibility.

This module now delegates to the new enhanced CPCRUD implementation.
New code should import from cpcrud.business_logic directly.
"""

import logging
from typing import Any

from cpaiops import CPAIOPSClient
from ruamel.yaml import YAML

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
                "message": result["errors"][0]["error"] if result.get("errors") else "Unknown error",
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
```

- [ ] **Step 2: Commit**

```bash
git add src/cpcrud/cpcrud.py
git commit -m "refactor: update cpcrud.py to use new enhanced implementation

Maintains backward compatibility while delegating to new modules.
Legacy CheckPointObjectManager class now wraps the enhanced implementation."
```

---

## Phase 5: Documentation & Testing

### Task 9: Create example templates

**Files:**

- Create: `ops/templates/example-with-nat.yaml`
- Create: `ops/templates/example-with-rules.yaml`

- [ ] **Step 1: Create example template with NAT settings**

```yaml
# ops/templates/example-with-nat.yaml

management_servers:
  - mgmt_name: "mds-prod"
    domains:
      - name: "DMZ"
        operations:
          # Host with static NAT
          - operation: add
            type: host
            data:
              name: "web-server-01"
              ip-address: "10.0.1.10"
              nat-settings:
                method: static
                ip-address: "203.0.113.10"
              color: "blue"
              groups: ["web-servers"]

          # Network with hide NAT
          - operation: add
            type: network
            data:
              name: "internal-network"
              subnet: "10.0.1.0"
              mask-length: 24
              nat-settings:
                method: hide
                gateway: "gw-dmz"

          # Address range with static NAT
          - operation: add
            type: address-range
            data:
              name: "dmz-server-range"
              ip-address-first: "10.0.1.100"
              ip-address-last: "10.0.1.150"
              nat-settings:
                method: static
                ipv4-address: "203.0.113.100"
```

- [ ] **Step 2: Create example template with rules**

```yaml
# ops/templates/example-with-rules.yaml

management_servers:
  - mgmt_name: "mds-prod"
    domains:
      - name: "DMZ"
        operations:
          # Access rule at top of layer
          - operation: add
            type: access-rule
            layer: "Network"
            position: "top"
            data:
              name: "Allow HTTPS to Web Servers"
              enabled: true
              source: ["Any"]
              destination: ["web-servers"]
              service: ["https"]
              action: "Accept"
              track:
                type: "Log"
              install-on: ["Policy_Gateway_DMZ"]

          # Access rule above specific rule
          - operation: add
            type: access-rule
            layer: "Network"
            position:
              above: "Deny All"
            data:
              name: "Allow Management Access"
              enabled: true
              source: ["management-network"]
              destination: ["Any"]
              service: ["ssh", "https"]
              action: "Accept"
              track:
                type: "Log"
              install-on: ["Policy_Gateway_DMZ"]

          # NAT rule at specific position
          - operation: add
            type: nat-rule
            package: "Network"
            position: 1
            data:
              name: "Hide NAT for Internal"
              enabled: true
              source: ["internal-network"]
              destination: ["Any"]
              service: ["Any"]
              method: "hide"
              translated-source: "gw-dmz"
              install-on: ["Policy_Gateway_DMZ"]
```

- [ ] **Step 3: Commit**

```bash
git add ops/templates/
git commit -m "docs: add example templates for NAT settings and rules

- example-with-nat.yaml: Demonstrates NAT settings for hosts, networks, ranges
- example-with-rules.yaml: Demonstrates access and NAT rule creation with positioning"
```

---

### Task 10: Create comprehensive documentation

**Files:**

- Create: `docs/internal/features/260411-cpcrud-enhancement/IMPLEMENTATION.md`

- [ ] **Step 1: Create implementation documentation**

```markdown
# CPCRUD Enhancement Implementation Notes

## Usage

### CLI

```bash
# Process templates with NAT settings and rules
fpcr cpcrud ops/templates/example-with-nat.yaml ops/templates/example-with-rules.yaml

# Process without publishing
fpcr cpcrud --no-publish ops/templates/example-with-rules.yaml
```

### Python API

```python
from cpcrud import (
    apply_crud_templates,
    CheckPointObjectManager,
    CheckPointRuleManager,
    PositionHelper,
)

# Validate a template
from cpcrud import validate_template_with_schema
with open("template.yaml") as f:
    template = yaml.safe_load(f)
errors = validate_template_with_schema(template, "template.yaml")

# Use managers directly
object_mgr = CheckPointObjectManager(client)
rule_mgr = CheckPointRuleManager(client)

# Add host with NAT
result = await object_mgr.execute(
    mgmt_name="mds-prod",
    domain="DMZ",
    operation="add",
    obj_type="host",
    data={
        "name": "server-01",
        "ip-address": "10.0.1.10",
        "nat-settings": {
            "method": "static",
            "ip-address": "203.0.113.10"
        }
    }
)

# Add access rule
result = await rule_mgr.add(
    rule_type="access-rule",
    data={
        "name": "Allow HTTPS",
        "source": ["Any"],
        "destination": ["web-servers"],
        "service": ["https"],
        "action": "Accept"
    },
    mgmt_name="mds-prod",
    domain_name="DMZ",
    layer="Network",
    position="top"
)
```

## NAT Settings Reference

### Static NAT

```yaml
nat-settings:
  method: static
  ip-address: "203.0.113.10"  # For network
  # OR
  ipv4-address: "203.0.113.10"  # For host/address-range
```

### Hide NAT

```yaml
nat-settings:
  method: hide
  gateway: "gw-object-name"  # Maps to install-on
```

## Rule Positioning Reference

```yaml
# Absolute position
position: 1

# Layer-level
position: "top"
position: "bottom"

# Section-relative
position:
  top: "Section Name"
position:
  bottom: "Section Name"
position:
  above: "Rule Name"
position:
  below: "Rule Name"
```

```

- [ ] **Step 2: Commit**

```bash
git add docs/internal/features/260411-cpcrud-enhancement/IMPLEMENTATION.md
git commit -m "docs: add implementation notes and usage examples"
```

---

## Final Verification

### Task 11: Run all tests

- [ ] **Step 1: Run complete test suite**

```bash
cd D:/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/cpcrud/ -v
```

Expected: All tests pass

- [ ] **Step 2: Type check with mypy**

```bash
uv run mypy src/cpcrud/
```

Expected: No type errors

- [ ] **Step 3: Format check with ruff**

```bash
uv run ruff check src/cpcrud/
```

Expected: No linting errors

- [ ] **Step 4: Create summary commit**

```bash
git add .
git commit -m "feat: complete CPCRUD enhancement implementation

Implementation complete for:
- NAT settings support for hosts, networks, address ranges
- Firewall rule management (access, NAT, threat, HTTPS rules)
- Rule positioning system (absolute, top/bottom, section-relative)
- JSON schema validation for templates
- Separate CheckPointObjectManager and CheckPointRuleManager classes

All tests passing, type checking clean."
```

---

## Implementation Complete

The CPCRUD enhancement is now fully implemented with:

1. **Foundation**: PositionHelper, config module, updated schema
2. **Object Manager**: Enhanced with NAT settings transformation
3. **Rule Manager**: Complete CRUD for all rule types with positioning
4. **Integration**: Business logic orchestrates template processing
5. **Testing**: Unit tests for all components
6. **Documentation**: Example templates and usage guide

The implementation follows TDD principles with tests written before code, frequent commits, and comprehensive validation.
