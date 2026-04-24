"""Generate HTML evidence cards, YAML exports, and PDFs."""

import logging
from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class EvidenceGenerator:
    """Generate evidence artifacts for RITM workflow."""

    def __init__(self, template_dir: str = "src/fa/templates"):
        """Initialize with template directory.

        Args:
            template_dir: Path to Jinja2 templates directory
        """
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def generate_html(
        self,
        ritm_number: str,
        created_at: datetime,
        engineer: str,
        initials: str,
        changes_by_domain: list[dict[str, Any]],
        errors: list[str] | None = None,
    ) -> str:
        """Generate Smart Console-style HTML evidence card.

        Args:
            ritm_number: RITM number
            created_at: Creation timestamp
            engineer: Engineer username
            initials: Engineer initials
            changes_by_domain: Changes grouped by domain > package > section
            errors: Optional list of error messages

        Returns:
            Rendered HTML string
        """
        template = self.env.get_template("evidence_card.html")

        return template.render(
            ritm_number=ritm_number,
            created_at=created_at.strftime("%Y-%m-%d %H:%M:%S"),
            engineer=engineer,
            initials=initials,
            changes_by_domain=changes_by_domain,
            errors=errors,
        )

    def generate_yaml(
        self,
        mgmt_name: str,
        domain_name: str,
        created_objects: list[dict[str, Any]],
        created_rules: list[dict[str, Any]],
    ) -> str:
        """Generate CPCRUD-compatible YAML export.

        Args:
            mgmt_name: Management server name
            domain_name: Domain name
            created_objects: List of created object dicts
            created_rules: List of created rule dicts (excluding deleted)

        Returns:
            YAML string
        """
        logger.debug(
            f"Generating YAML for {len(created_objects)} objects, {len(created_rules)} rules in domain {domain_name}"
        )

        # Build operations list
        operations = []

        # Add objects
        for obj in created_objects:
            obj_type = obj["object_type"]
            name = obj["object_name"]

            if obj_type == "host":
                op = {
                    "operation": "add",
                    "type": "host",
                    "data": {"name": name, "ip-address": obj.get("input", name)},
                }
            elif obj_type == "network":
                # Handle network format
                ip_value = obj.get("input", "")
                if "/" in ip_value:
                    subnet, mask = ip_value.split("/")
                    op = {
                        "operation": "add",
                        "type": "network",
                        "data": {"name": name, "subnet": subnet, "mask-length": int(mask)},
                    }
                else:
                    logger.warning(f"Skipping network object {name} with invalid IP: {ip_value}")
                    continue
            else:
                logger.warning(f"Skipping unsupported object type: {obj_type}")
                continue

            operations.append(op)
            logger.debug(f"Added operation for {obj_type}: {name}")

        # Add rules (simplified - full implementation would include all rule fields)
        for rule in created_rules:
            if rule.get("deleted"):
                logger.debug(f"Skipping deleted rule: {rule.get('name')}")
                continue

            op = {
                "operation": "add",
                "type": "access-rule",
                "layer": rule.get("layer_name", "Network"),
                "position": rule.get("position", "top"),
                "data": {
                    "name": rule.get("name", ""),
                    "enabled": False,
                    "source": rule.get("source_ips", []),
                    "destination": rule.get("dest_ips", []),
                    "service": rule.get("services", []),
                    "action": rule.get("action", "Accept"),
                },
            }
            operations.append(op)
            logger.debug(f"Added operation for rule: {rule.get('name')}")

        logger.debug(f"Total operations: {len(operations)}")

        # Build YAML structure
        yaml_dict = {
            "management_servers": [
                {
                    "mgmt_name": mgmt_name,
                    "domains": [{"name": domain_name, "operations": operations}],
                }
            ]
        }

        # Convert to YAML-like string (simple implementation)
        return self._dict_to_yaml(yaml_dict)

    def _dict_to_yaml(self, data: dict[str, Any], indent: int = 0) -> str:
        """Convert dict to YAML string (simple implementation).

        In production, use yaml.dump() from PyYAML.
        """
        lines = []
        prefix = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        lines.append(self._dict_to_yaml(item, indent + 2))
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")

        return "\n".join(lines)
