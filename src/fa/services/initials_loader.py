"""Load engineer initials from CSV file."""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class InitialsLoader:
    """Load and cache engineer initials from CSV file."""

    def __init__(self, csv_path: str):
        """Initialize with CSV file path.

        CSV format: Name,Email,A-account,Short Name
        Example: "Doe, John",john.doe@example.com,a-johndoe,JD
        """
        self._initials_map: dict[str, str] = {}
        self._load_csv(csv_path)

    def _load_csv(self, csv_path: str) -> None:
        """Load CSV file and build initials mapping."""
        path = Path(csv_path)
        if not path.exists():
            logger.warning(f"Initials CSV not found: {csv_path}")
            return

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Column 3: A-account, Column 4: Short Name
                    a_account = row.get("A-account", "")
                    short_name = row.get("Short Name", "")

                    if a_account and short_name:
                        self._initials_map[a_account] = short_name

            logger.info(f"Loaded {len(self._initials_map)} initials mappings")

        except Exception as e:
            logger.error(f"Failed to load initials CSV: {e}")

    def get_initials(self, username: str) -> str:
        """Get initials for username (A-account format).

        Args:
            username: A-account username (e.g., "a-johndoe")

        Returns:
            Initials (e.g., "JD") or "XX" if not found
        """
        return self._initials_map.get(username, "XX")
