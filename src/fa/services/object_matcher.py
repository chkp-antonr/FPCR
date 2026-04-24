"""Object matching and creation with naming conventions."""

import logging
import re
from typing import Any

from cpaiops import CPAIOPSClient

from cpsearch import classify_input

logger = logging.getLogger(__name__)


def _classify_input_simple(input_value: str) -> str:
    """Classify input and return type as string.

    Wrapper around cpsearch.classify_input that returns just the type.
    """
    search_type, _ = classify_input(input_value)
    return search_type.value


async def _find_cp_objects_in_domain(
    client: CPAIOPSClient,
    domain_name: str,
    search: str,
    obj_type: str,
) -> list[dict[str, Any]]:
    """Find objects in a specific domain using cpaiops directly.

    Searches only in the specified domain, not across all domains.

    Args:
        client: CPAIOPSClient instance
        domain_name: Domain name (empty string for system domain)
        search: Search string (IP, CIDR, etc.)
        obj_type: Object type filter (host, network, address-range)

    Returns:
        List of object dicts compatible with ObjectMatcher
    """
    mgmt_name = client.get_mgmt_names()[0]
    logger.debug(
        "Searching for %s objects matching '%s' in domain '%s' on mgmt '%s'",
        obj_type,
        search,
        domain_name,
        mgmt_name,
    )

    # Use filter-based queries (same pattern as cpsearch) so existing objects are found reliably.
    if obj_type == "host":
        logger.debug(
            "API query: command=show-hosts domain='%s' payload=%s", domain_name, {"filter": search}
        )
        result = await client.api_query(
            mgmt_name,
            "show-hosts",
            domain=domain_name,
            payload={"filter": search},
        )
    elif obj_type == "network":
        net_filter = search.split("/")[0] if "/" in search else search
        logger.debug(
            "API query: command=show-networks domain='%s' payload=%s",
            domain_name,
            {"filter": net_filter},
        )
        result = await client.api_query(
            mgmt_name,
            "show-networks",
            domain=domain_name,
            payload={"filter": net_filter},
        )
    elif obj_type == "address-range":
        first_ip = search.split("-")[0].strip() if "-" in search else search
        logger.debug(
            "API query: command=show-address-ranges domain='%s' payload=%s",
            domain_name,
            {"filter": first_ip},
        )
        result = await client.api_query(
            mgmt_name,
            "show-address-ranges",
            domain=domain_name,
            payload={"filter": first_ip},
        )
    else:
        logger.warning(f"Unsupported object type: {obj_type}")
        return []

    logger.debug(
        "API query result: success=%s, message=%s, objects_count=%s",
        result.success,
        getattr(result, "message", None),
        len(result.objects) if result.objects else 0,
    )

    if not result.success or not result.objects:
        logger.debug(f"No objects found for {obj_type} '{search}' in domain '{domain_name}'")
        return []

    # Filter objects to the exact requested value where possible.
    filtered = []
    for obj in result.objects:
        if obj_type == "host" and obj.get("ipv4-address") != search:
            logger.debug(
                "Skipping host candidate name='%s' ip='%s' (expected '%s')",
                obj.get("name"),
                obj.get("ipv4-address"),
                search,
            )
            continue

        # Convert to dict format expected by ObjectMatcher
        obj_dict: dict[str, Any] = {
            "uid": obj.get("uid", ""),
            "name": obj.get("name", ""),
            "type": obj_type,
            "ipv4-address": obj.get("ipv4-address", ""),
            "subnet4": obj.get("subnet4", ""),
            "mask-length4": obj.get("mask-length4", None),
            "ipv4-address-first": obj.get("first-address", ""),
            "ipv4-address-last": obj.get("last-address", ""),
            "domain": obj.get("domain", domain_name),
            "usage-count": obj.get("used-by", {}).get("total", 0)
            if isinstance(obj.get("used-by"), dict)
            else 0,
        }
        filtered.append(obj_dict)
        logger.debug(
            "Found object candidate: name='%s' uid='%s' type='%s' usage=%s",
            obj_dict["name"],
            obj_dict["uid"],
            obj_dict["type"],
            obj_dict.get("usage-count", 0),
        )

    logger.debug(
        f"Returning {len(filtered)} objects for {obj_type} '{search}' in domain '{domain_name}'"
    )
    return filtered


class ObjectMatcher:
    """Match existing objects or create new ones following conventions."""

    NAMING_PATTERNS = {
        "host": [
            r"^global_Host_([\d\.]+)$",
            r"^Host_([\d\.]+)$",
            r"^ipr_(.+)$",
        ],
        "network": [
            r"^global_Net_([\d\.]+)_(\d+)$",
            r"^Net_([\d\.]+)_(\d+)$",
        ],
        "address-range": [
            r"^global_IPR_(.+)$",
            r"^IPR_(.+)$",
        ],
    }

    def __init__(self, client: CPAIOPSClient):
        """Initialize with CPAIOPS client."""
        self.client = client

    def _score_object(self, obj: dict[str, Any], pattern_match: bool) -> tuple[int, int]:
        """Score object: (naming_score, usage_score). Higher is better."""
        naming_score = 100 if pattern_match else 0
        usage_count = obj.get("usage-count", 0)
        return (naming_score, usage_count)

    def _matches_convention(self, obj: dict[str, Any], obj_type: str) -> bool:
        """Check if object name matches naming convention."""
        name = obj.get("name", "")
        patterns = self.NAMING_PATTERNS.get(obj_type, [])

        return any(re.match(pattern, name) for pattern in patterns)

    def _generate_object_name(self, obj_type: str, value: str, is_global: bool) -> str:
        """Generate name following convention."""
        prefix = "global_" if is_global else ""

        if obj_type == "host":
            return f"{prefix}Host_{value}"
        elif obj_type == "network":
            subnet, mask = value.split("/")
            return f"{prefix}Net_{subnet}_{mask}"
        elif obj_type == "address-range":
            return f"{prefix}IPR_{value.replace('.', '_')}"

        # Fallback
        return f"{prefix}{obj_type}_{value.replace('.', '_')}"

    async def _create_object(
        self,
        obj_type: str,
        name: str,
        value: str,
        _domain_uid: str,
        domain_name: str,
    ) -> dict[str, Any]:
        """Create object via CPAIOPS."""
        mgmt_name = self.client.get_mgmt_names()[0]
        logger.debug(
            "Creating object: type='%s' name='%s' value='%s' domain='%s' mgmt='%s'",
            obj_type,
            name,
            value,
            domain_name,
            mgmt_name,
        )

        # Build payload based on object type
        payload: dict[str, Any]
        if obj_type == "host":
            payload = {"name": name, "ip-address": value}
            command = "add-host"
        elif obj_type == "network":
            subnet, mask = value.split("/")
            payload = {"name": name, "subnet": subnet, "mask-length": int(mask)}
            command = "add-network"
        else:
            raise ValueError(f"Unsupported object type: {obj_type}")

        logger.debug("API call: command=%s domain='%s' payload=%s", command, domain_name, payload)

        result = await self.client.api_call(mgmt_name, command, domain=domain_name, payload=payload)

        if not result.success:
            details: list[str] = []
            raw_data = getattr(result, "data", None)
            logger.debug(
                "Create API failure raw result: message=%s data=%s",
                getattr(result, "message", None),
                raw_data,
            )
            if isinstance(raw_data, dict):
                if raw_data.get("warnings"):
                    details.append(f"warnings={raw_data.get('warnings')}")
                if raw_data.get("errors"):
                    details.append(f"errors={raw_data.get('errors')}")

            detail_suffix = f" ({'; '.join(details)})" if details else ""
            logger.error(f"Failed to create {obj_type} '{name}': {result.message}{detail_suffix}")
            raise Exception(f"Failed to create {obj_type}: {result.message}{detail_suffix}")

        logger.debug(
            "Create API success: type='%s' name='%s' uid='%s'",
            obj_type,
            name,
            result.data.get("uid") if result.data else "N/A",
        )
        return result.data if result.data is not None else {}

    async def match_and_create_objects(
        self,
        inputs: list[str],
        domain_uid: str,
        domain_name: str,
        create_missing: bool = True,
    ) -> list[dict[str, Any]]:
        """Match existing objects or create new ones.

        Args:
            inputs: List of inputs (IPs, networks, etc.)
            domain_uid: Domain UID
            domain_name: Domain name
            create_missing: Whether to create missing objects

        Returns:
            List of dicts with keys: input, object_uid, object_name,
            object_type, created, matches_convention, usage_count
        """
        logger.info(
            "Processing %s inputs for domain '%s' (UID: %s), create_missing=%s",
            len(inputs),
            domain_name,
            domain_uid,
            create_missing,
        )
        results = []
        is_global = domain_uid == "global" or domain_uid == "0.0.0.0"

        for input_value in inputs:
            logger.debug(f"Processing input: '{input_value}'")
            # 1. Classify input type
            obj_type = _classify_input_simple(input_value)
            logger.debug(f"Classified as: {obj_type}")

            # 2. Search existing objects (only in the specified domain)
            found = await _find_cp_objects_in_domain(
                self.client, domain_name=domain_name, search=input_value, obj_type=obj_type
            )

            if found:
                # 3. Score and select best match
                best = max(
                    found,
                    key=lambda o: self._score_object(o, self._matches_convention(o, obj_type)),
                )
                logger.debug(
                    "Selected existing object for input '%s': name='%s' uid='%s'",
                    input_value,
                    best["name"],
                    best["uid"],
                )

                results.append(
                    {
                        "input": input_value,
                        "object_uid": best["uid"],
                        "object_name": best["name"],
                        "object_type": obj_type,
                        "created": False,
                        "matches_convention": self._matches_convention(best, obj_type),
                        "usage_count": best.get("usage-count", 0),
                    }
                )

            elif create_missing:
                # 4. Create new object
                new_name = self._generate_object_name(obj_type, input_value, is_global)
                logger.debug(
                    "No existing object found for input '%s', creating '%s'",
                    input_value,
                    new_name,
                )

                try:
                    created = await self._create_object(
                        obj_type=obj_type,
                        name=new_name,
                        value=input_value,
                        _domain_uid=domain_uid,
                        domain_name=domain_name,
                    )

                    results.append(
                        {
                            "input": input_value,
                            "object_uid": created["uid"],
                            "object_name": new_name,
                            "object_type": obj_type,
                            "created": True,
                            "matches_convention": True,
                            "usage_count": 0,
                        }
                    )
                except Exception as e:
                    # Check if object already exists
                    error_msg = str(e)
                    logger.debug("Create exception for input '%s': %s", input_value, error_msg)
                    if (
                        "already exists" in error_msg.lower()
                        or "object of the same name" in error_msg.lower()
                    ):
                        logger.warning(
                            f"Object '{new_name}' already exists, searching for existing object"
                        )
                        # Try to find the existing object
                        existing = await _find_cp_objects_in_domain(
                            self.client,
                            domain_name=domain_name,
                            search=input_value,
                            obj_type=obj_type,
                        )
                        if existing:
                            best = existing[0]
                            results.append(
                                {
                                    "input": input_value,
                                    "object_uid": best["uid"],
                                    "object_name": best["name"],
                                    "object_type": obj_type,
                                    "created": False,
                                    "matches_convention": self._matches_convention(best, obj_type),
                                    "usage_count": best.get("usage-count", 0),
                                }
                            )
                            logger.info(
                                f"Using existing object '{best['name']}' instead of creating new one"
                            )
                        else:
                            # Re-raise the original error if we can't find an existing object
                            raise
                    else:
                        # Re-raise other errors
                        raise

        return results
