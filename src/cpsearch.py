"""Check Point object search and group membership discovery.

Searches for hosts, networks, IP ranges, and groups across all domains
on a management server, then recursively traces group memberships.
"""

import asyncio
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from arlogi import get_logger
from cpaiops import CPAIOPSClient

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for input classification
# ---------------------------------------------------------------------------

# x.x.x.x-y.y.y.y
_IP_RANGE_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})\s*-\s*(\d{1,3}(?:\.\d{1,3}){3})$")

# x.x.x.x/N  or  x.x.x.x/y.y.y.y
_NETWORK_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,3}(?:\.\d{1,3}){0,3}|\d{1,2})$")

# plain IPv4
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


class SearchType(StrEnum):
    """Classification of the search input."""

    IP_RANGE = "address-range"
    NETWORK = "network"
    HOST = "host"
    NAME = "name"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FoundObject:
    """A Check Point object returned by a search."""

    uid: str
    name: str
    obj_type: str
    domain: str
    orig_domain: str = ""
    ipv4_address: str = ""
    subnet4: str = ""
    mask_length4: int | None = None
    range_first: str = ""
    range_last: str = ""

    @property
    def is_global(self) -> bool:
        """True when the object originates from a different domain."""
        return bool(self.orig_domain) and self.orig_domain != self.domain

    @property
    def address_display(self) -> str:
        """Human-readable address representation."""
        if self.ipv4_address:
            return self.ipv4_address
        if self.subnet4 and self.mask_length4 is not None:
            return f"{self.subnet4}/{self.mask_length4}"
        if self.range_first and self.range_last:
            return f"{self.range_first}-{self.range_last}"
        return ""


@dataclass
class GroupNode:
    """A node in the group membership tree."""

    uid: str
    name: str
    domain: str
    depth: int
    children: list["GroupNode"] = field(default_factory=list)


@dataclass
class DomainSearchResult:
    """Search results for a single domain."""

    domain_name: str
    objects: list[FoundObject] = field(default_factory=list)
    memberships: dict[str, list[GroupNode]] = field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------


def classify_input(raw: str) -> tuple[SearchType, str]:
    """Classify the user's search string.

    Returns (search_type, cleaned_input).
    """
    text = raw.strip()

    if _IP_RANGE_RE.match(text):
        return SearchType.IP_RANGE, text

    if _NETWORK_RE.match(text):
        return SearchType.NETWORK, text

    if _IPV4_RE.match(text):
        return SearchType.HOST, text

    return SearchType.NAME, text


# ---------------------------------------------------------------------------
# Helper: build FoundObject from raw API dict
# ---------------------------------------------------------------------------


def _obj_from_dict(obj: dict[str, Any], domain_name: str) -> FoundObject:
    """Convert a raw API object dict into a FoundObject."""
    # Extract the object's original domain from the API response
    domain_info = obj.get("domain")
    if isinstance(domain_info, dict):
        orig_domain = domain_info.get("name", "")
    elif isinstance(domain_info, str):
        orig_domain = domain_info
    else:
        orig_domain = ""

    return FoundObject(
        uid=obj.get("uid", ""),
        name=obj.get("name", ""),
        obj_type=obj.get("type", ""),
        domain=domain_name,
        orig_domain=orig_domain,
        ipv4_address=obj.get("ipv4-address", ""),
        subnet4=obj.get("subnet4", ""),
        mask_length4=obj.get("mask-length4"),
        range_first=obj.get("ipv4-address-first", ""),
        range_last=obj.get("ipv4-address-last", ""),
    )


# ---------------------------------------------------------------------------
# Core search helpers
# ---------------------------------------------------------------------------


async def _search_by_type(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    search_type: SearchType,
    search_input: str,
) -> list[FoundObject]:
    """Search for objects of a specific type in a single domain."""
    domain_label = domain or "(system)"

    if search_type == SearchType.HOST:
        return await _search_hosts(client, mgmt_name, domain, domain_label, search_input)
    elif search_type == SearchType.NETWORK:
        return await _search_networks(client, mgmt_name, domain, domain_label, search_input)
    elif search_type == SearchType.IP_RANGE:
        return await _search_ranges(client, mgmt_name, domain, domain_label, search_input)
    else:
        return await _search_by_name(client, mgmt_name, domain, domain_label, search_input)


async def _search_hosts(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    domain_label: str,
    ip: str,
) -> list[FoundObject]:
    """Search for hosts matching an IP address."""
    result = await client.api_query(
        mgmt_name=mgmt_name,
        command="show-hosts",
        domain=domain,
        payload={"filter": ip},
    )
    if not result.success:
        logger.debug(f"show-hosts failed in {domain_label}: {result.message}")
        return []

    return [
        _obj_from_dict(obj, domain_label) for obj in result.objects if obj.get("ipv4-address") == ip
    ]


async def _search_networks(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    domain_label: str,
    cidr: str,
) -> list[FoundObject]:
    """Search for networks matching a CIDR/netmask."""
    # Extract the network address part for the filter
    net_addr = cidr.split("/")[0]
    result = await client.api_query(
        mgmt_name=mgmt_name,
        command="show-networks",
        domain=domain,
        payload={"filter": net_addr},
    )
    if not result.success:
        logger.debug(f"show-networks failed in {domain_label}: {result.message}")
        return []

    return [_obj_from_dict(obj, domain_label) for obj in result.objects]


async def _search_ranges(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    domain_label: str,
    range_str: str,
) -> list[FoundObject]:
    """Search for address-ranges matching a range string."""
    first_ip = range_str.split("-")[0].strip()
    result = await client.api_query(
        mgmt_name=mgmt_name,
        command="show-address-ranges",
        domain=domain,
        payload={"filter": first_ip},
    )
    if not result.success:
        logger.debug(f"show-address-ranges failed in {domain_label}: {result.message}")
        return []

    return [_obj_from_dict(obj, domain_label) for obj in result.objects]


async def _search_by_name(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    domain_label: str,
    name: str,
) -> list[FoundObject]:
    """Search for objects by name across multiple types."""
    types_to_search = ["host", "network", "address-range", "group"]
    found: list[FoundObject] = []

    for obj_type in types_to_search:
        result = await client.api_query(
            mgmt_name=mgmt_name,
            command="show-objects",
            domain=domain,
            payload={"filter": name, "type": obj_type},
        )
        if result.success:
            for obj in result.objects:
                found.append(_obj_from_dict(obj, domain_label))
        else:
            logger.debug(f"show-objects type={obj_type} failed in {domain_label}: {result.message}")

    return found


# ---------------------------------------------------------------------------
# Group membership discovery
# ---------------------------------------------------------------------------


async def _find_parent_groups(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    object_uid: str,
    _domain_label: str,
) -> list[dict[str, Any]]:
    """Find groups that contain a given object uid via where-used."""
    result = await client.api_call(
        mgmt_name=mgmt_name,
        command="where-used",
        domain=domain,
        payload={"uid": object_uid},
    )
    if not result.success or not result.data:
        return []

    used_directly = result.data.get("used-directly", {})
    groups_raw = used_directly.get("objects", [])
    return [g for g in groups_raw if isinstance(g, dict) and g.get("type") == "group"]


async def _resolve_memberships(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    object_uid: str,
    domain_label: str,
    max_depth: int,
    current_depth: int = 1,
    visited: set[str] | None = None,
) -> list[GroupNode]:
    """Recursively resolve parent group memberships up to max_depth."""
    if current_depth > max_depth:
        return []

    if visited is None:
        visited = set()

    parent_groups = await _find_parent_groups(client, mgmt_name, domain, object_uid, domain_label)
    nodes: list[GroupNode] = []

    for grp in parent_groups:
        grp_uid = grp.get("uid", "")
        if grp_uid in visited:
            continue
        visited.add(grp_uid)

        node = GroupNode(
            uid=grp_uid,
            name=grp.get("name", ""),
            domain=domain_label,
            depth=current_depth,
        )
        # Recurse to next level
        node.children = await _resolve_memberships(
            client,
            mgmt_name,
            domain,
            grp_uid,
            domain_label,
            max_depth,
            current_depth + 1,
            visited,
        )
        nodes.append(node)

    return nodes


# ---------------------------------------------------------------------------
# Per-domain search coroutine
# ---------------------------------------------------------------------------


async def _search_domain(
    client: CPAIOPSClient,
    mgmt_name: str,
    domain: str,
    search_type: SearchType,
    search_input: str,
    max_depth: int,
) -> DomainSearchResult:
    """Run full search + membership discovery in a single domain."""
    domain_label = domain or "(system)"
    result = DomainSearchResult(domain_name=domain_label)

    try:
        objects = await _search_by_type(client, mgmt_name, domain, search_type, search_input)
        result.objects = objects

        # Discover memberships for each found object
        for obj in objects:
            memberships = await _resolve_memberships(
                client, mgmt_name, domain, obj.uid, domain_label, max_depth
            )
            if memberships:
                result.memberships[obj.uid] = memberships

    except Exception as e:
        error_msg = f"Error searching domain {domain_label}: {e}"
        logger.error(error_msg)
        result.error = error_msg

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def find_cp_objects(
    client: CPAIOPSClient,
    search_input: str,
    max_depth: int = 2,
) -> dict[str, DomainSearchResult]:
    """Search for Check Point objects across all domains.

    Args:
        client: An open CPAIOPSClient instance (inside async context manager).
        search_input: IP, CIDR, IP range, or object name to search for.
        max_depth: Maximum levels of parent-group nesting to resolve.

    Returns:
        Dictionary keyed by domain name with DomainSearchResult values.
    """
    search_type, cleaned = classify_input(search_input)
    logger.debug(f"Search classified as {search_type.value} for input: {cleaned}")

    mgmt_names = client.get_mgmt_names()
    if not mgmt_names:
        logger.warning("No management servers registered")
        return {}

    mgmt_name = mgmt_names[0]

    # Discover domains
    domains_result = await client.api_query(mgmt_name, "show-domains")
    domain_names: list[str] = [""]  # system domain always included

    if domains_result.success and domains_result.objects:
        for obj in domains_result.objects:
            name = obj.get("name", "")
            if name:
                domain_names.append(name)

    logger.info(f"Searching across {len(domain_names)} domain(s) on {mgmt_name}")

    # Fan out across all domains in parallel
    tasks = [
        _search_domain(client, mgmt_name, domain, search_type, cleaned, max_depth)
        for domain in domain_names
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: dict[str, DomainSearchResult] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Domain search failed with exception: {r}")
            continue
        if isinstance(r, DomainSearchResult) and (r.objects or r.error):
            # Only include domains that have results or errors
            output[r.domain_name] = r

    return output
