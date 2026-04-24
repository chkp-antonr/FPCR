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
