"""Tests for InitialsLoader."""

import tempfile
from pathlib import Path

from fa.services.initials_loader import InitialsLoader


def test_loads_csv_successfully():
    """Test that CSV is loaded correctly."""
    csv_content = '''Name,Email,A-account,Short Name
"Doe, John",john.doe@example.com,a-johndoe,JD
"Smith, Jane",jane.smith@example.com,a-janesmith,JS'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        loader = InitialsLoader(temp_path)
        assert loader.get_initials("a-johndoe") == "JD"
        assert loader.get_initials("a-janesmith") == "JS"
    finally:
        Path(temp_path).unlink()


def test_returns_xx_for_unknown_user():
    """Test that unknown users get 'XX' as initials."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv") as f:
        f.write("Name,Email,A-account,Short Name\n")
        temp_path = f.name

    loader = InitialsLoader(temp_path)
    assert loader.get_initials("unknown") == "XX"


def test_handles_missing_csv():
    """Test that missing CSV is handled gracefully."""
    loader = InitialsLoader("nonexistent.csv")
    assert loader.get_initials("anyone") == "XX"
