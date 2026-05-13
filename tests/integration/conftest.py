"""
Integration test configuration for the FPCR RITM workflow.

Prerequisites:
  1. A live Check Point management server reachable at API_MGMT.
  2. tests/integration/.env.test populated from .env.test.example.
  3. seed.py has been run at least once to create the baseline CP revision:
         uv run python tests/integration/cp_setup/seed.py
  4. FPCR application running at FPCR_BASE_URL (default: http://localhost:8000).
  5. Four CP engineer accounts configured: ENGINEER1_USER/PASS … ENGINEER4_USER/PASS.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest_asyncio
from cpaiops import CPAIOPSClient
from dotenv import load_dotenv
from httpx import AsyncClient

load_dotenv(Path(__file__).parent / ".env.test")

# ---------------------------------------------------------------------------
# Module-level constants (read from env after load_dotenv)
# ---------------------------------------------------------------------------

FPCR_BASE_URL: str = os.environ.get("FPCR_BASE_URL", "http://localhost:8000")
REVISION_NAME: str = os.environ.get("CP_REVISION_NAME", "ritm_integration_baseline")


# ---------------------------------------------------------------------------
# TestEnv dataclass — resolved UIDs for the test topology
# ---------------------------------------------------------------------------


@dataclass
class TestEnv:
    """Resolved UIDs for the seeded CP test topology."""

    domain_a_uid: str
    domain_a_name: str
    domain_b_uid: str
    domain_b_name: str
    package_name: str
    package_a_uid: str
    package_b_uid: str
    section_a_uid: str
    section_b_uid: str
    section_name: str = field(default="RITM_TEST_SECTION")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


async def _make_client(user: str, password: str) -> AsyncClient:
    """Log in to FPCR and return an authenticated AsyncClient (cookie-based)."""
    client = AsyncClient(base_url=FPCR_BASE_URL, timeout=30.0)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user, "password": password},
    )
    resp.raise_for_status()
    return client


# ---------------------------------------------------------------------------
# Four session-scoped engineer clients
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def eng1_client() -> AsyncClient:
    """Authenticated AsyncClient for engineer 1."""
    user = os.environ["ENGINEER1_USER"]
    password = os.environ["ENGINEER1_PASS"]
    client = await _make_client(user, password)
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def eng2_client() -> AsyncClient:
    """Authenticated AsyncClient for engineer 2."""
    user = os.environ["ENGINEER2_USER"]
    password = os.environ["ENGINEER2_PASS"]
    client = await _make_client(user, password)
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def eng3_client() -> AsyncClient:
    """Authenticated AsyncClient for engineer 3."""
    user = os.environ["ENGINEER3_USER"]
    password = os.environ["ENGINEER3_PASS"]
    client = await _make_client(user, password)
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def eng4_client() -> AsyncClient:
    """Authenticated AsyncClient for engineer 4."""
    user = os.environ["ENGINEER4_USER"]
    password = os.environ["ENGINEER4_PASS"]
    client = await _make_client(user, password)
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# test_env — resolves domain / package / section UIDs via FPCR API
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def test_env(eng1_client: AsyncClient) -> TestEnv:
    """
    Resolve domain/package/section UIDs from the live FPCR API.

    Uses eng1_client (already authenticated) to call:
      GET /api/v1/domains
      GET /api/v1/domains/{uid}/packages
      GET /api/v1/domains/{uid}/packages/{uid}/sections
    """
    domain_a_name: str = os.environ["TEST_DOMAIN_A"]
    domain_b_name: str = os.environ["TEST_DOMAIN_B"]
    package_name: str = os.environ["TEST_PACKAGE_NAME"]

    # -- Domains --
    resp = await eng1_client.get("/api/v1/domains")
    resp.raise_for_status()
    domains: list[dict] = resp.json()["domains"]

    def _find_domain(name: str) -> dict:
        for d in domains:
            if d["name"] == name:
                return d
        raise RuntimeError(
            f"Domain {name!r} not found in FPCR /api/v1/domains response. "
            "Run seed.py and ensure the cache is populated."
        )

    domain_a = _find_domain(domain_a_name)
    domain_b = _find_domain(domain_b_name)

    # -- Packages --
    async def _get_package_uid(domain_uid: str, domain_name: str) -> str:
        resp = await eng1_client.get(f"/api/v1/domains/{domain_uid}/packages")
        resp.raise_for_status()
        packages: list[dict] = resp.json()["packages"]
        for p in packages:
            if p["name"] == package_name:
                return p["uid"]
        raise RuntimeError(
            f"Package {package_name!r} not found in domain {domain_name!r}. "
            "Run seed.py and ensure the cache is populated."
        )

    package_a_uid = await _get_package_uid(domain_a["uid"], domain_a_name)
    package_b_uid = await _get_package_uid(domain_b["uid"], domain_b_name)

    # -- Sections --
    section_name = "RITM_TEST_SECTION"

    async def _get_section_uid(domain_uid: str, pkg_uid: str, domain_name: str) -> str:
        resp = await eng1_client.get(
            f"/api/v1/domains/{domain_uid}/packages/{pkg_uid}/sections"
        )
        resp.raise_for_status()
        sections: list[dict] = resp.json()["sections"]
        for s in sections:
            if s["name"] == section_name:
                return s["uid"]
        raise RuntimeError(
            f"Section {section_name!r} not found in domain {domain_name!r} / "
            f"package {package_name!r}. Run seed.py first."
        )

    section_a_uid = await _get_section_uid(domain_a["uid"], package_a_uid, domain_a_name)
    section_b_uid = await _get_section_uid(domain_b["uid"], package_b_uid, domain_b_name)

    return TestEnv(
        domain_a_uid=domain_a["uid"],
        domain_a_name=domain_a_name,
        domain_b_uid=domain_b["uid"],
        domain_b_name=domain_b_name,
        package_name=package_name,
        package_a_uid=package_a_uid,
        package_b_uid=package_b_uid,
        section_a_uid=section_a_uid,
        section_b_uid=section_b_uid,
    )


# ---------------------------------------------------------------------------
# cp_baseline — ensures the seed revision exists (auto-seeds if absent)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", autouse=True)
async def cp_baseline() -> None:
    """
    Ensure the named CP baseline revision exists before any tests run.

    Constructs a CPAIOPSClient from env vars (matching seed.py exactly),
    checks for the revision, and auto-runs seed.py if it is absent.
    """
    from tests.integration.cp_setup.revision import revision_exists

    mgmt_ip = os.environ["API_MGMT"]
    username = os.environ["API_USERNAME"]
    password = os.environ["API_PASSWORD"]

    async with CPAIOPSClient(
        username=username,
        password=password,
        mgmt_ip=mgmt_ip,
    ) as client:
        mgmt_name: str = client.get_mgmt_names()[0]
        exists = await revision_exists(client, mgmt_name, REVISION_NAME)

    if not exists:
        seed_script = Path(__file__).parent / "cp_setup" / "seed.py"
        result = subprocess.run(
            [sys.executable, str(seed_script)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"seed.py failed (exit {result.returncode}).\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )


# ---------------------------------------------------------------------------
# cp_restored — class-scoped: deletes DB and restores CP to baseline
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="class")
async def cp_restored(cp_baseline: None) -> None:
    """
    Before each test class: delete the integration SQLite DB and restore
    the CP management server to the named baseline revision.

    Depends on cp_baseline to guarantee the revision exists first.
    """
    from tests.integration.cp_setup.revision import restore_revision

    mgmt_ip = os.environ["API_MGMT"]
    username = os.environ["API_USERNAME"]
    password = os.environ["API_PASSWORD"]

    # Delete the integration DB so each scenario starts from a clean slate.
    db_path_str = os.environ.get("INTEGRATION_DB_PATH", "tests/integration/test.db")
    db_path = Path(db_path_str)
    if not db_path.is_absolute():
        db_path = Path(__file__).parent.parent.parent / db_path_str
    if db_path.exists():
        db_path.unlink()

    # Restore CP to the baseline revision.
    async with CPAIOPSClient(
        username=username,
        password=password,
        mgmt_ip=mgmt_ip,
    ) as client:
        mgmt_name: str = client.get_mgmt_names()[0]
        await restore_revision(client, mgmt_name, REVISION_NAME)

    yield


# ---------------------------------------------------------------------------
# admin_cp — function-scoped: yields a connected CPAIOPSClient for direct CP
#            operations in tests (scenarios that need to call CP API directly)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def admin_cp():
    """Yields a (CPAIOPSClient, mgmt_name) tuple for direct CP API calls in tests."""
    mgmt_ip = os.environ["API_MGMT"]
    username = os.environ["API_USERNAME"]
    password = os.environ["API_PASSWORD"]

    async with CPAIOPSClient(
        username=username,
        password=password,
        mgmt_ip=mgmt_ip,
    ) as client:
        mgmt_name: str = client.get_mgmt_names()[0]
        yield client, mgmt_name
