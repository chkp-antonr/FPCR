"""Position helper for Check Point rule positioning.

This module validates the ``position`` value from YAML templates
before it is sent to the Check Point Management API.
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
