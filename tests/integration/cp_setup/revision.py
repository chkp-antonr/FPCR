"""Create and restore named CP management revisions for integration tests."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Actual cpaiops API: client.api_call(mgmt_name, command, domain="", payload={})
# Returns ApiCallResult with .data dict and .success bool.
# There is no client.run() — the plan's assumed signature does not exist.


async def list_revisions(client: Any, mgmt_name: str, domain: str = "") -> list[dict]:
    """Return all named revisions from the management server."""
    result = await client.api_call(
        mgmt_name,
        "show-sessions",
        domain,
        payload={"details-level": "full", "view-published-sessions": True, "limit": 500},
    )
    if not result.success or not result.data:
        return []
    return result.data.get("objects", [])


async def revision_exists(client: Any, mgmt_name: str, name: str, domain: str = "") -> bool:
    """Return True if a revision with the given name exists."""
    revisions = await list_revisions(client, mgmt_name, domain)
    return any(r.get("name") == name for r in revisions)


async def create_revision(
    client: Any,
    mgmt_name: str,
    name: str,
    description: str = "",
    domain: str = "",
) -> str:
    """
    Create a named revision at the current published state.
    Returns the revision UID.

    Call this AFTER seed.py has published its changes.
    """
    result = await client.api_call(
        mgmt_name,
        "set-session",
        domain,
        payload={"new-name": name, "description": description},
    )
    if not result.success or not result.data:
        raise RuntimeError(
            f"Failed to create revision {name!r}: {result.message} (code={result.code})"
        )
    uid = result.data.get("uid", "")
    if not uid:
        raise RuntimeError(
            f"create_revision: CP response missing 'uid'. Full response: {result.data}"
        )
    log.info("Created revision %r uid=%s", name, uid)
    return uid


async def restore_revision(
    client: Any,
    mgmt_name: str,
    name: str,
    domain: str = "",
) -> None:
    """
    Restore the management server to the named revision.

    This discards any unpublished changes and reverts published policy
    to the state captured at revision creation time.
    """
    revisions = await list_revisions(client, mgmt_name, domain)
    match = next((r for r in revisions if r.get("name") == name), None)
    if match is None:
        raise RuntimeError(
            f"CP revision {name!r} not found. Run seed.py first."
        )
    log.info("Restoring CP to revision %r (uid=%s)", name, match["uid"])
    result = await client.api_call(
        mgmt_name,
        "revert-to-revision",
        domain,
        payload={"to-session": match["uid"]},
    )
    if not result.success:
        raise RuntimeError(
            f"revert-to-revision failed: {result.message} (code={result.code})"
        )
    log.info("Revision restore complete.")
