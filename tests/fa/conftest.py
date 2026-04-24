"""Pytest configuration for fa tests."""
import sys
from pathlib import Path

# Ensure src is in path BEFORE pytest imports any test modules
# This needs to be at module level, not in a hook
src_path = Path(__file__).parent.parent.parent / "src"
# Remove any existing 'tests' or 'src' entries first
sys.path = [p for p in sys.path if 'tests' not in p and 'src' not in p]
# Insert src at the beginning
sys.path.insert(0, str(src_path))


def pytest_configure(config):
    """Configure pytest - this runs before collection."""
    # Double-check that src is at the beginning of the path
    if sys.path[0] != str(src_path):
        sys.path.insert(0, str(src_path))
