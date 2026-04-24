"""Configuration constants for CPCRUD module."""

from pathlib import Path

# Default schema path relative to project root
DEFAULT_SCHEMA_PATH = Path("ops/checkpoint_ops_schema.json")

# Cache settings (for future use if needed)
CACHE_ENABLED = False
CACHE_TTL_SECONDS = 3600
