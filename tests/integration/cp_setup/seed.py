#!/usr/bin/env python
"""
One-time CP environment seeding for RITM integration tests.

Usage:
    uv run python tests/integration/cp_setup/seed.py
    uv run python tests/integration/cp_setup/seed.py --check   # dry-run
    uv run python tests/integration/cp_setup/seed.py --force   # re-seed even if revision exists

Reads schema.yaml; idempotent — safe to re-run.
Skips entirely if the named CP revision already exists (use --force to override).
After seeding, creates the named CP revision CP_REVISION_NAME.

API note: CPAIOPSClient exposes api_call(mgmt_name, command, domain, payload=...).
There is no client.run() — the plan's assumed signature does not exist.
In credential mode mgmt_name == the management IP (client.get_mgmt_names()[0]).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.test")

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SCHEMA_PATH = Path(__file__).parent / "schema.yaml"
DOMAIN_A = os.environ["TEST_DOMAIN_A"]
DOMAIN_B = os.environ["TEST_DOMAIN_B"]
PACKAGE_NAME = os.environ["TEST_PACKAGE_NAME"]
REVISION_NAME = os.environ["CP_REVISION_NAME"]

# Credentials used exclusively by seed.py (admin account).
_API_MGMT = os.environ["API_MGMT"]
_API_USERNAME = os.environ["API_USERNAME"]
_API_PASSWORD = os.environ["API_PASSWORD"]


async def object_exists(
    client: Any, mgmt_name: str, domain: str, obj_type: str, name: str
) -> bool:
    """Return True if an object with given name already exists in the domain."""
    try:
        result = await client.api_call(
            mgmt_name,
            f"show-{obj_type}",
            domain,
            payload={"name": name},
        )
        return bool(result.success and result.data and result.data.get("uid"))
    except Exception:
        return False


async def ensure_host(
    client: Any, mgmt_name: str, domain: str, name: str, ip: str
) -> str:
    """Create host if absent; return its UID."""
    if await object_exists(client, mgmt_name, domain, "host", name):
        log.info("[%s] host %r already exists — skip", domain, name)
        result = await client.api_call(
            mgmt_name, "show-host", domain, payload={"name": name}
        )
        return result.data["uid"]
    result = await client.api_call(
        mgmt_name,
        "add-host",
        domain,
        payload={"name": name, "ip-address": ip},
    )
    log.info("[%s] created host %r uid=%s", domain, name, result.data["uid"])
    return result.data["uid"]


async def ensure_network(
    client: Any, mgmt_name: str, domain: str, name: str, subnet: str, mask: int
) -> str:
    """Create network if absent; return its UID."""
    if await object_exists(client, mgmt_name, domain, "network", name):
        log.info("[%s] network %r already exists — skip", domain, name)
        result = await client.api_call(
            mgmt_name, "show-network", domain, payload={"name": name}
        )
        return result.data["uid"]
    result = await client.api_call(
        mgmt_name,
        "add-network",
        domain,
        payload={"name": name, "subnet": subnet, "mask-length": mask},
    )
    log.info("[%s] created network %r uid=%s", domain, name, result.data["uid"])
    return result.data["uid"]


async def ensure_service_tcp(
    client: Any, mgmt_name: str, domain: str, name: str, port: int
) -> str:
    """Create TCP service if absent; return its UID."""
    if await object_exists(client, mgmt_name, domain, "service-tcp", name):
        log.info("[%s] service %r already exists — skip", domain, name)
        result = await client.api_call(
            mgmt_name, "show-service-tcp", domain, payload={"name": name}
        )
        return result.data["uid"]
    result = await client.api_call(
        mgmt_name,
        "add-service-tcp",
        domain,
        payload={"name": name, "port": str(port)},
    )
    log.info("[%s] created service %r uid=%s", domain, name, result.data["uid"])
    return result.data["uid"]


async def ensure_section(
    client: Any, mgmt_name: str, domain: str, package: str, section_name: str
) -> str:
    """Create policy section if absent; return its UID."""
    rulebase = await client.api_call(
        mgmt_name,
        "show-access-rulebase",
        domain,
        payload={"name": package, "details-level": "standard", "limit": 500},
    )
    for entry in (rulebase.data or {}).get("rulebase", []):
        if entry.get("type") == "access-section" and entry.get("name") == section_name:
            log.info("[%s] section %r already exists — skip", domain, section_name)
            return entry["uid"]
    result = await client.api_call(
        mgmt_name,
        "add-access-section",
        domain,
        payload={"layer": package, "name": section_name, "position": "top"},
    )
    log.info("[%s] created section %r uid=%s", domain, section_name, result.data["uid"])
    return result.data["uid"]


async def _rule_exists_in_section(
    client: Any, mgmt_name: str, domain: str, package: str, rule_name: str
) -> bool:
    """Return True if a rule with given name exists anywhere in the package rulebase."""
    rulebase = await client.api_call(
        mgmt_name,
        "show-access-rulebase",
        domain,
        payload={"name": package, "details-level": "standard", "limit": 500},
    )
    for entry in (rulebase.data or {}).get("rulebase", []):
        for rule in entry.get("rulebase", []):
            if rule.get("name") == rule_name:
                return True
    return False


async def ensure_broken_rule(
    client: Any, mgmt_name: str, schema: dict, section_uid: str
) -> None:
    """Create BROKEN_RULE in TEST_DOMAIN_A if absent (disabled at rest)."""
    br = schema["broken_rule"]
    domain = DOMAIN_A
    package = PACKAGE_NAME
    if await _rule_exists_in_section(client, mgmt_name, domain, package, br["name"]):
        log.info("[%s] BROKEN_RULE already exists — skip", domain)
        return
    await client.api_call(
        mgmt_name,
        "add-access-rule",
        domain,
        payload={
            "layer": package,
            "name": br["name"],
            "position": {"section": section_uid, "above": "top"},
            "source": [br["source"]],
            "destination": [br["destination"]],
            "service": [br["service"]],
            "action": br["action"],
            "track": {"type": br["track"]},
            "enabled": br["enabled"],
        },
    )
    log.info("[%s] created BROKEN_RULE (disabled)", domain)


async def ensure_conflict_seed_rule(
    client: Any, mgmt_name: str, schema: dict, section_uid: str, domain: str
) -> None:
    """Create RITM_TEST_SECTION_CONFLICT rule if absent (used by Scenario 3)."""
    cr = schema["conflict_seed_rule"]
    package = PACKAGE_NAME
    if await _rule_exists_in_section(client, mgmt_name, domain, package, cr["name"]):
        log.info("[%s] conflict seed rule already exists — skip", domain)
        return
    await client.api_call(
        mgmt_name,
        "add-access-rule",
        domain,
        payload={
            "layer": package,
            "name": cr["name"],
            "position": {"section": section_uid, "above": "top"},
            "source": [cr["source"]],
            "destination": [cr["destination"]],
            "service": [cr["service"]],
            "action": cr["action"],
            "track": {"type": cr["track"]},
            "enabled": cr["enabled"],
        },
    )
    log.info("[%s] created conflict seed rule", domain)


async def seed_domain(
    client: Any, mgmt_name: str, domain: str, schema: dict
) -> str:
    """Seed all objects and sections for one domain. Returns section UID."""
    log.info("=== Seeding domain: %s ===", domain)
    package = PACKAGE_NAME

    section_uid = await ensure_section(client, mgmt_name, domain, package, "RITM_TEST_SECTION")

    for h in schema["hosts"]:
        await ensure_host(client, mgmt_name, domain, h["name"], h["ip"])

    for n in schema["networks"]:
        await ensure_network(
            client, mgmt_name, domain, n["name"], n["subnet"], n["mask-length"]
        )

    for s in schema["services"]:
        await ensure_service_tcp(client, mgmt_name, domain, s["name"], s["port"])

    return section_uid


async def main(check_only: bool = False, force: bool = False) -> None:
    from cpaiops import CPAIOPSClient
    from tests.integration.cp_setup.revision import (
        create_revision,
        revision_exists,
    )

    async with CPAIOPSClient(
        username=_API_USERNAME,
        password=_API_PASSWORD,
        mgmt_ip=_API_MGMT,
    ) as client:
        # In credential mode the mgmt_name defaults to the management IP.
        mgmt_name = client.get_mgmt_names()[0]
        log.info("Connected to management server: %s", mgmt_name)

        # Skip seed entirely if the baseline revision already exists (unless --force).
        if not force and not check_only:
            if await revision_exists(client, mgmt_name, REVISION_NAME):
                log.info(
                    "Revision %r already exists — seed skipped. "
                    "Use --force to re-seed.",
                    REVISION_NAME,
                )
                return

        schema = yaml.safe_load(SCHEMA_PATH.read_text())

        if check_only:
            log.info("--check mode: listing existing objects only (no changes)")

        section_uid_a = await seed_domain(client, mgmt_name, DOMAIN_A, schema)
        section_uid_b = await seed_domain(client, mgmt_name, DOMAIN_B, schema)

        if not check_only:
            await ensure_broken_rule(client, mgmt_name, schema, section_uid_a)
            await ensure_conflict_seed_rule(
                client, mgmt_name, schema, section_uid_a, DOMAIN_A
            )
            await ensure_conflict_seed_rule(
                client, mgmt_name, schema, section_uid_b, DOMAIN_B
            )

            for domain in (DOMAIN_A, DOMAIN_B):
                await client.api_call(mgmt_name, "publish", domain)
                log.info("[%s] published", domain)

            await create_revision(
                client,
                mgmt_name,
                REVISION_NAME,
                "RITM integration test baseline",
            )
            log.info("Baseline revision %r ready.", REVISION_NAME)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run: list existing objects, make no changes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-seed even if the named revision already exists.",
    )
    args = parser.parse_args()
    asyncio.run(main(check_only=args.check, force=args.force))
