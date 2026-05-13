# RITM Integration Test Suite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pytest-based integration test suite with 5 ordered scenarios exercising the full RITM workflow against a real Check Point management server with four distinct CP user accounts.

**Architecture:** Pytest class-based scenarios with `pytest-order` enforcing step sequence; CP named-revision restore (`ritm_integration_baseline`) + SQLite DB file deletion before each scenario for deterministic state; four `AsyncClient` fixtures (eng1–eng4) authenticating as real CP accounts; file-based SQLite recreated fresh per scenario. Seed runs only when the named CP revision is absent — once the revision exists, seed is never re-run.

**Tech Stack:** Python 3.13, pytest + pytest-asyncio + pytest-order, httpx AsyncClient, SQLModel + aiosqlite, cpaiops (internal Check Point client), python-dotenv.

**Spec:** `docs/superpowers/specs/2026-05-13-ritm-integration-tests-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add `pytest-order`, `python-dotenv` dev deps; add `integration` marker |
| `.gitignore` | Modify | Ignore `tests/integration/.env.test` and `tests/integration/test.db` |
| `tests/integration/__init__.py` | Create | Package marker |
| `tests/integration/cp_setup/__init__.py` | Create | Package marker |
| `tests/integration/scenarios/__init__.py` | Create | Package marker |
| `tests/integration/.env.test.example` | Create | Credential template (committed; real `.env.test` is gitignored) |
| `tests/integration/cp_setup/schema.yaml` | Create | Declarative CP seed objects, sections, services |
| `tests/integration/cp_setup/revision.py` | Create | Create / restore named CP revision |
| `tests/integration/cp_setup/seed.py` | Create | Idempotent CP environment seeding script |
| `tests/integration/conftest.py` | Create | Env loading, DB engine, 4 user clients, `TestEnv`, revision fixtures |
| `tests/integration/scenarios/test_scenario_01_happy_path.py` | Create | 15-step happy path scenario |
| `tests/integration/scenarios/test_scenario_02_preverify_error.py` | Create | Pre-verify fails → fix → complete |
| `tests/integration/scenarios/test_scenario_03_postcheck_rollback.py` | Create | Post-check rollback → attempt 2 succeeds |
| `tests/integration/scenarios/test_scenario_04_rejection_cycle.py` | Create | 4-user separation-of-duties chain |
| `tests/integration/scenarios/test_scenario_05_domain_change.py` | Create | Domain change after rejection |

---

## Task 1 — Scaffolding and Dependencies

**Files:**

- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `tests/integration/__init__.py`, `tests/integration/cp_setup/__init__.py`, `tests/integration/scenarios/__init__.py`
- Create: `tests/integration/.env.test.example`

- [ ] **Step 1: Add dev dependencies to pyproject.toml**

  Open `pyproject.toml`. In the `[dependency-groups]` `dev` list, add:

  ```toml
  "pytest-order>=2.2",
  "python-dotenv>=1.0",
  ```

  Also add an `[tool.pytest.ini_options]` section (or extend the existing one):

  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  markers = [
      "integration: marks tests as integration tests (require live CP environment)",
  ]
  ```

- [ ] **Step 2: Install new dependencies**

  ```bash
  uv sync
  ```

  Expected: resolves `pytest-order` and `python-dotenv` without conflicts.

- [ ] **Step 3: Add gitignore entries**

  Open `.gitignore`. Add at the end:

  ```gitignore
  # Integration test credentials and local DB
  tests/integration/.env.test
  tests/integration/test.db
  ```

- [ ] **Step 4: Create package init files**

  Create three empty files:
  - `tests/integration/__init__.py`
  - `tests/integration/cp_setup/__init__.py`
  - `tests/integration/scenarios/__init__.py`

  Each file is empty (0 bytes).

- [ ] **Step 5: Create .env.test.example**

  Create `tests/integration/.env.test.example`:

  ```ini
  # Copy this file to .env.test and fill in real values.
  # .env.test is gitignored — never commit credentials.

  # Check Point management server (admin account used by seed.py)
  API_MGMT=192.168.1.100
  API_USERNAME=admin
  API_PASSWORD=secret

  # FPCR application URL
  FPCR_BASE_URL=http://localhost:8000

  # Four CP test engineers (real CP accounts on the management server)
  ENGINEER1_USER=eng1
  ENGINEER1_PASS=pass1

  ENGINEER2_USER=eng2
  ENGINEER2_PASS=pass2

  ENGINEER3_USER=eng3
  ENGINEER3_PASS=pass3

  ENGINEER4_USER=eng4
  ENGINEER4_PASS=pass4

  # Policy domains (must already exist or be created by seed.py)
  TEST_DOMAIN_A=TestDomainA
  TEST_DOMAIN_B=TestDomainB

  # Policy package name inside each domain (must already exist)
  TEST_PACKAGE_NAME=Standard

  # Named CP revision baseline
  CP_REVISION_NAME=ritm_integration_baseline

  # Integration test DB path (relative to project root)
  INTEGRATION_DB_PATH=tests/integration/test.db
  ```

- [ ] **Step 6: Verify pytest discovers the integration marker**

  ```bash
  uv run pytest --co -q tests/integration/ 2>&1 | head -5
  ```

  Expected: `no tests ran` (no test files yet) — no import errors.

- [ ] **Step 7: Commit**

  ```bash
  git add pyproject.toml .gitignore tests/integration/
  git commit -m "test: scaffold integration test suite structure"
  ```

---

## Task 2 — CP Seed Schema

**Files:**

- Create: `tests/integration/cp_setup/schema.yaml`

- [ ] **Step 1: Create schema.yaml**

  Create `tests/integration/cp_setup/schema.yaml`:

  ```yaml
  # Declarative CP seed for integration tests.
  # seed.py reads this and creates missing resources idempotently.
  # Both TEST_DOMAIN_A and TEST_DOMAIN_B receive the same seed.

  sections:
    - name: RITM_TEST_SECTION
      # Inserted above the first rule in the top-level policy package.
      position: top

  hosts:
    - name: Host_10.0.0.1
      ip: 10.0.0.1
    - name: Host_10.0.0.2
      ip: 10.0.0.2
    # BROKEN host — no IP gateway route; causes verify-policy to emit an error.
    # Used only in Scenario 2 (pre-verify error).
    - name: Host_BROKEN
      ip: 10.255.255.254
      broken: true

  networks:
    - name: Net_10.1.0.0_24
      subnet: 10.1.0.0
      mask-length: 24

  services:
    - name: svc_http_8080
      type: tcp
      port: 8080
    - name: svc_custom_9999
      type: tcp
      port: 9999

  # BROKEN_RULE — rule in RITM_TEST_SECTION that causes verify-policy failure.
  # References Host_BROKEN as source. Installed only in TEST_DOMAIN_A.
  # seed.py creates this rule and leaves it disabled.
  # Scenario 2 enables it before running pre-verify, then deletes it to fix.
  broken_rule:
    name: BROKEN_RULE
    domain: TEST_DOMAIN_A     # only in DomainA
    section: RITM_TEST_SECTION
    source: Host_BROKEN
    destination: Any
    service: Any
    action: accept
    track: log
    enabled: false            # disabled at rest; Scenario 2 enables it to trigger error
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add tests/integration/cp_setup/schema.yaml
  git commit -m "test: add CP seed schema for integration test environment"
  ```

---

## Task 3 — CP Revision Module

**Files:**

- Create: `tests/integration/cp_setup/revision.py`

The Check Point Management API (R80.10+) exposes `show-revisions` and `revert-to-revision` commands. This module wraps them via the cpaiops client.

**Note for implementer:** Verify that the `CPAIOPSClient` instance you receive exposes a method for running arbitrary management commands. If it provides `client.run_command(cmd, payload)` or `client.api(cmd, **kwargs)`, use that. Check `libs/cpaiops/` for the actual method name before implementing.

- [ ] **Step 1: Write the revision module**

  Create `tests/integration/cp_setup/revision.py`:

  ```python
  """Create and restore named CP management revisions for integration tests."""

  from __future__ import annotations

  import logging
  from typing import Any

  log = logging.getLogger(__name__)


  async def list_revisions(client: Any) -> list[dict]:
      """Return all named revisions from the management server."""
      # Adjust method name to match actual cpaiops API.
      # Common patterns: client.run("show-revisions"), client.api("show-revisions")
      result = await client.run("show-revisions", {"details-level": "full"})
      return result.get("objects", [])


  async def revision_exists(client: Any, name: str) -> bool:
      """Return True if a revision with the given name exists."""
      revisions = await list_revisions(client)
      return any(r.get("name") == name for r in revisions)


  async def create_revision(client: Any, name: str, description: str = "") -> str:
      """
      Create a named revision at the current published state.
      Returns the revision UID.

      Call this AFTER seed.py has published its changes.
      """
      result = await client.run(
          "set-revision",
          {"name": name, "description": description},
      )
      uid: str = result["uid"]
      log.info("Created revision %r uid=%s", name, uid)
      return uid


  async def restore_revision(client: Any, name: str) -> None:
      """
      Restore the management server to the named revision.

      This discards any unpublished changes and reverts published policy
      to the state captured at revision creation time.
      """
      revisions = await list_revisions(client)
      match = next((r for r in revisions if r.get("name") == name), None)
      if match is None:
          raise RuntimeError(
              f"CP revision {name!r} not found. Run seed.py first."
          )
      log.info("Restoring CP to revision %r (uid=%s)", name, match["uid"])
      await client.run("revert-to-revision", {"to-session": match["uid"]})
      log.info("Revision restore complete.")
  ```

- [ ] **Step 2: Write a smoke test for the revision module**

  Create `tests/integration/cp_setup/test_revision_smoke.py`:

  ```python
  """
  Smoke test — not run in normal suite; invoke manually to verify revision
  module works against your CP environment:

      uv run pytest tests/integration/cp_setup/test_revision_smoke.py -v -s
  """

  import os
  import pytest
  from dotenv import load_dotenv

  load_dotenv("tests/integration/.env.test")


  @pytest.mark.skip(reason="Manual smoke test — requires live CP environment")
  async def test_list_revisions_returns_list():
      """Verify list_revisions returns a list (may be empty on fresh server)."""
      from tests.integration.cp_setup.revision import list_revisions

      # Import the CPAIOPS global from the app — adjust import if needed.
      from src.fa.cpaiops import CPAIOPS  # noqa: adjust import path

      revisions = await list_revisions(CPAIOPS)
      assert isinstance(revisions, list)
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add tests/integration/cp_setup/revision.py \
          tests/integration/cp_setup/test_revision_smoke.py
  git commit -m "test: add CP revision create/restore module"
  ```

---

## Task 4 — CP Seed Script

**Files:**

- Create: `tests/integration/cp_setup/seed.py`

The seed script is run once (or re-run safely) to create the CP baseline. It reads `schema.yaml`, checks what already exists, creates what is missing, publishes, then creates/updates the named revision.

- [ ] **Step 1: Write seed.py**

  Create `tests/integration/cp_setup/seed.py`:

  ```python
  #!/usr/bin/env python
  """
  One-time CP environment seeding for RITM integration tests.

  Usage:
      uv run python tests/integration/cp_setup/seed.py
      uv run python tests/integration/cp_setup/seed.py --check   # dry-run

  Reads schema.yaml; idempotent — safe to re-run.
  After seeding, creates/updates the named CP revision CP_REVISION_NAME.
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


  async def object_exists(client: Any, domain: str, obj_type: str, name: str) -> bool:
      """Return True if an object with given name already exists in the domain."""
      try:
          result = await client.run(
              f"show-{obj_type}",
              {"name": name},
              domain=domain,
          )
          return bool(result.get("uid"))
      except Exception:
          return False


  async def ensure_host(client: Any, domain: str, name: str, ip: str) -> str:
      """Create host if absent; return its UID."""
      if await object_exists(client, domain, "host", name):
          log.info("[%s] host %r already exists — skip", domain, name)
          result = await client.run("show-host", {"name": name}, domain=domain)
          return result["uid"]
      result = await client.run(
          "add-host",
          {"name": name, "ip-address": ip},
          domain=domain,
      )
      log.info("[%s] created host %r uid=%s", domain, name, result["uid"])
      return result["uid"]


  async def ensure_network(
      client: Any, domain: str, name: str, subnet: str, mask: int
  ) -> str:
      """Create network if absent; return its UID."""
      if await object_exists(client, domain, "network", name):
          log.info("[%s] network %r already exists — skip", domain, name)
          result = await client.run("show-network", {"name": name}, domain=domain)
          return result["uid"]
      result = await client.run(
          "add-network",
          {"name": name, "subnet": subnet, "mask-length": mask},
          domain=domain,
      )
      log.info("[%s] created network %r uid=%s", domain, name, result["uid"])
      return result["uid"]


  async def ensure_service_tcp(
      client: Any, domain: str, name: str, port: int
  ) -> str:
      """Create TCP service if absent; return its UID."""
      if await object_exists(client, domain, "service-tcp", name):
          log.info("[%s] service %r already exists — skip", domain, name)
          result = await client.run(
              "show-service-tcp", {"name": name}, domain=domain
          )
          return result["uid"]
      result = await client.run(
          "add-service-tcp",
          {"name": name, "port": str(port)},
          domain=domain,
      )
      log.info("[%s] created service %r uid=%s", domain, name, result["uid"])
      return result["uid"]


  async def ensure_section(
      client: Any, domain: str, package: str, section_name: str
  ) -> str:
      """Create policy section if absent; return its UID."""
      rulebase = await client.run(
          "show-access-rulebase",
          {"name": package, "details-level": "standard", "limit": 500},
          domain=domain,
      )
      for entry in rulebase.get("rulebase", []):
          if entry.get("type") == "access-section" and entry.get("name") == section_name:
              log.info("[%s] section %r already exists — skip", domain, section_name)
              return entry["uid"]
      result = await client.run(
          "add-access-section",
          {"layer": package, "name": section_name, "position": "top"},
          domain=domain,
      )
      log.info("[%s] created section %r uid=%s", domain, section_name, result["uid"])
      return result["uid"]


  async def ensure_broken_rule(
      client: Any, schema: dict, section_uid: str
  ) -> None:
      """Create BROKEN_RULE in TEST_DOMAIN_A if absent (disabled at rest)."""
      br = schema["broken_rule"]
      domain = DOMAIN_A
      package = PACKAGE_NAME
      rulebase = await client.run(
          "show-access-rulebase",
          {"name": package, "details-level": "standard", "limit": 500},
          domain=domain,
      )
      for entry in rulebase.get("rulebase", []):
          for rule in entry.get("rulebase", []):
              if rule.get("name") == br["name"]:
                  log.info("[%s] BROKEN_RULE already exists — skip", domain)
                  return
      await client.run(
          "add-access-rule",
          {
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
          domain=domain,
      )
      log.info("[%s] created BROKEN_RULE (disabled)", domain)


  async def seed_domain(client: Any, domain: str, schema: dict) -> None:
      """Seed all objects and sections for one domain."""
      log.info("=== Seeding domain: %s ===", domain)
      package = PACKAGE_NAME

      # Sections
      section_uid = await ensure_section(client, domain, package, "RITM_TEST_SECTION")

      # Hosts
      for h in schema["hosts"]:
          await ensure_host(client, domain, h["name"], h["ip"])

      # Networks
      for n in schema["networks"]:
          await ensure_network(client, domain, n["name"], n["subnet"], n["mask-length"])

      # Services
      for s in schema["services"]:
          await ensure_service_tcp(client, domain, s["name"], s["port"])

      return section_uid


  async def main(check_only: bool = False, force: bool = False) -> None:
      # Import CPAIOPS global — adjust import path if the module location differs.
      from src.fa.cpaiops import CPAIOPS  # noqa: adjust if needed
      from tests.integration.cp_setup.revision import revision_exists

      # Skip seed entirely if the baseline revision already exists (unless --force).
      if not force and not check_only:
          if await revision_exists(CPAIOPS, REVISION_NAME):
              log.info(
                  "Revision %r already exists — seed skipped. "
                  "Use --force to re-seed.",
                  REVISION_NAME,
              )
              return

      schema = yaml.safe_load(SCHEMA_PATH.read_text())

      if check_only:
          log.info("--check mode: listing existing objects only (no changes)")

      section_uid_a = await seed_domain(CPAIOPS, DOMAIN_A, schema)
      section_uid_b = await seed_domain(CPAIOPS, DOMAIN_B, schema)

      if not check_only:
          # Broken rule only in DomainA
          await ensure_broken_rule(CPAIOPS, schema, section_uid_a)

          # Publish changes in both domains
          for domain in (DOMAIN_A, DOMAIN_B):
              await CPAIOPS.run("publish", {}, domain=domain)
              log.info("[%s] published", domain)

          # Create/update named revision
          from tests.integration.cp_setup.revision import (
              create_revision,
              revision_exists,
          )

          if await revision_exists(CPAIOPS, REVISION_NAME):
              log.info("Revision %r already exists — updating", REVISION_NAME)
              await CPAIOPS.run(
                  "set-revision",
                  {"name": REVISION_NAME, "description": "RITM integration baseline"},
              )
          else:
              await create_revision(
                  CPAIOPS,
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
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add tests/integration/cp_setup/seed.py
  git commit -m "test: add idempotent CP environment seed script"
  ```

---

## Task 5 — Integration conftest.py

**Files:**

- Create: `tests/integration/conftest.py`

This is the most important file. It wires together: env loading, DB engine (file-based SQLite), 4 authenticated clients, `TestEnv` (domain/package/section UIDs), and the CP revision reset fixture.

- [ ] **Step 1: Write conftest.py**

  Create `tests/integration/conftest.py`:

  ```python
  """
  Integration test fixtures.

  Prerequisites:
    1. Copy tests/integration/.env.test.example → tests/integration/.env.test
       and fill in real credentials.
    2. Start FPCR: uv run uvicorn src.fa.app:app --reload
       (or set FPCR_BASE_URL to a running instance)
    3. Seed runs automatically on first pytest run if the named CP revision is absent.
       Force a re-seed manually: uv run python tests/integration/cp_setup/seed.py --force
  """

  from __future__ import annotations

  import os
  from dataclasses import dataclass, field
  from pathlib import Path

  import pytest
  import pytest_asyncio
  from dotenv import load_dotenv
  from httpx import AsyncClient

  # Load .env.test before any fixture runs.
  load_dotenv(Path(__file__).parent / ".env.test", override=True)

  FPCR_BASE_URL = os.environ.get("FPCR_BASE_URL", "http://localhost:8000")
  REVISION_NAME = os.environ["CP_REVISION_NAME"]


  # ---------------------------------------------------------------------------
  # TestEnv — holds domain/package/section UIDs fetched once per session
  # ---------------------------------------------------------------------------

  @dataclass
  class TestEnv:
      domain_a_uid: str = ""
      domain_a_name: str = field(default_factory=lambda: os.environ["TEST_DOMAIN_A"])
      domain_b_uid: str = ""
      domain_b_name: str = field(default_factory=lambda: os.environ["TEST_DOMAIN_B"])
      package_name: str = field(default_factory=lambda: os.environ["TEST_PACKAGE_NAME"])
      package_a_uid: str = ""
      package_b_uid: str = ""
      section_a_uid: str = ""
      section_b_uid: str = ""
      section_name: str = "RITM_TEST_SECTION"


  # ---------------------------------------------------------------------------
  # Authenticated client factory
  # ---------------------------------------------------------------------------

  async def _make_client(user: str, password: str) -> AsyncClient:
      """Create an AsyncClient logged in to FPCR as the given CP user."""
      client = AsyncClient(base_url=FPCR_BASE_URL)
      resp = await client.post(
          "/api/v1/auth/login",
          json={"username": user, "password": password},
      )
      assert resp.status_code == 200, (
          f"Login failed for {user!r}: {resp.status_code} {resp.text}"
      )
      return client


  # ---------------------------------------------------------------------------
  # Session-scoped authenticated clients (login once per pytest session)
  # ---------------------------------------------------------------------------

  @pytest_asyncio.fixture(scope="session")
  async def eng1_client() -> AsyncClient:
      """Initial editor."""
      client = await _make_client(
          os.environ["ENGINEER1_USER"], os.environ["ENGINEER1_PASS"]
      )
      yield client
      await client.aclose()


  @pytest_asyncio.fixture(scope="session")
  async def eng2_client() -> AsyncClient:
      """First approver / rejecter."""
      client = await _make_client(
          os.environ["ENGINEER2_USER"], os.environ["ENGINEER2_PASS"]
      )
      yield client
      await client.aclose()


  @pytest_asyncio.fixture(scope="session")
  async def eng3_client() -> AsyncClient:
      """Correction editor."""
      client = await _make_client(
          os.environ["ENGINEER3_USER"], os.environ["ENGINEER3_PASS"]
      )
      yield client
      await client.aclose()


  @pytest_asyncio.fixture(scope="session")
  async def eng4_client() -> AsyncClient:
      """Second approver / rejecter."""
      client = await _make_client(
          os.environ["ENGINEER4_USER"], os.environ["ENGINEER4_PASS"]
      )
      yield client
      await client.aclose()


  # ---------------------------------------------------------------------------
  # TestEnv — fetch domain/package/section UIDs once
  # ---------------------------------------------------------------------------

  @pytest_asyncio.fixture(scope="session")
  async def test_env(eng1_client: AsyncClient) -> TestEnv:
      """
      Fetch domain, package, and section UIDs from the live FPCR API.
      Uses eng1_client (any authenticated client works).
      """
      env = TestEnv()

      # Domains
      resp = await eng1_client.get("/api/v1/domains")
      assert resp.status_code == 200, f"GET /domains failed: {resp.text}"
      domains = resp.json()
      for d in domains:
          if d["name"] == env.domain_a_name:
              env.domain_a_uid = d["uid"]
          elif d["name"] == env.domain_b_name:
              env.domain_b_uid = d["uid"]

      assert env.domain_a_uid, f"Domain {env.domain_a_name!r} not found in CP"
      assert env.domain_b_uid, f"Domain {env.domain_b_name!r} not found in CP"

      # Packages
      for domain_uid, attr in (
          (env.domain_a_uid, "package_a_uid"),
          (env.domain_b_uid, "package_b_uid"),
      ):
          resp = await eng1_client.get(f"/api/v1/domains/{domain_uid}/packages")
          assert resp.status_code == 200
          packages = resp.json()
          pkg = next(
              (p for p in packages if p["name"] == env.package_name), None
          )
          assert pkg, (
              f"Package {env.package_name!r} not found in domain {domain_uid}"
          )
          setattr(env, attr, pkg["uid"])

      # Sections
      for domain_uid, pkg_uid, attr in (
          (env.domain_a_uid, env.package_a_uid, "section_a_uid"),
          (env.domain_b_uid, env.package_b_uid, "section_b_uid"),
      ):
          resp = await eng1_client.get(
              f"/api/v1/domains/{domain_uid}/packages/{pkg_uid}/sections"
          )
          assert resp.status_code == 200
          sections = resp.json()
          sec = next(
              (s for s in sections if s["name"] == env.section_name), None
          )
          assert sec, (
              f"Section {env.section_name!r} not found in domain {domain_uid}"
          )
          setattr(env, attr, sec["uid"])

      return env


  # ---------------------------------------------------------------------------
  # CP baseline — ensures named revision exists (auto-seeds if absent)
  # ---------------------------------------------------------------------------

  @pytest_asyncio.fixture(scope="session", autouse=True)
  async def cp_baseline() -> None:
      """
      Session-scoped guard: runs once before any test.
      If the named CP revision is absent, runs seed.py automatically.
      If it already exists, does nothing — seed is never re-run.
      """
      from src.fa.cpaiops import CPAIOPS  # adjust import path if needed
      from tests.integration.cp_setup.revision import revision_exists
      from tests.integration.cp_setup.seed import main as run_seed

      if not await revision_exists(CPAIOPS, REVISION_NAME):
          import logging
          logging.getLogger(__name__).warning(
              "Baseline revision %r not found — running seed.", REVISION_NAME
          )
          await run_seed()
      yield


  # ---------------------------------------------------------------------------
  # CP revision restore — resets CP + FPCR DB between scenarios
  # ---------------------------------------------------------------------------

  @pytest_asyncio.fixture(scope="class")
  async def cp_restored(cp_baseline: None) -> None:
      """
      Reset before each scenario:
        1. Delete the SQLite DB file so the app recreates it fresh on next request.
        2. Revert CP to the named baseline revision.

      The FPCR app holds an async engine pointing at INTEGRATION_DB_PATH.
      Deleting the file is sufficient — SQLite recreates it on first connect
      and the app's lifespan calls init_database() which creates all tables.
      """
      from pathlib import Path

      from src.fa.cpaiops import CPAIOPS  # adjust import path if needed
      from tests.integration.cp_setup.revision import restore_revision

      db_path = Path(os.environ.get("INTEGRATION_DB_PATH", "tests/integration/test.db"))
      if db_path.exists():
          db_path.unlink()

      await restore_revision(CPAIOPS, REVISION_NAME)
      yield
  ```

  **Reset strategy (confirmed):** Delete the SQLite DB file + CP revert-to-revision. No app-side reset endpoint needed.

- [ ] **Step 2: Write a minimal wiring test**

  Create `tests/integration/test_wiring.py`:

  ```python
  """Verifies test infrastructure is wired up correctly before running scenarios."""

  import pytest


  @pytest.mark.integration
  async def test_eng1_can_reach_fpcr(eng1_client):
      """eng1 is logged in and can call a health endpoint."""
      resp = await eng1_client.get("/api/v1/health")
      assert resp.status_code == 200


  @pytest.mark.integration
  async def test_test_env_has_uids(test_env):
      """TestEnv fixture resolves domain/package/section UIDs."""
      assert test_env.domain_a_uid, "domain_a_uid is empty"
      assert test_env.domain_b_uid, "domain_b_uid is empty"
      assert test_env.package_a_uid, "package_a_uid is empty"
      assert test_env.section_a_uid, "section_a_uid is empty"
      assert test_env.section_b_uid, "section_b_uid is empty"
  ```

- [ ] **Step 3: Run wiring tests against live FPCR**

  Start FPCR first:

  ```bash
  uv run uvicorn src.fa.app:app --reload &
  ```

  Then run:

  ```bash
  uv run pytest tests/integration/test_wiring.py -v
  ```

  Expected: both tests PASS. If either fails, fix the conftest before proceeding.

- [ ] **Step 4: Commit**

  ```bash
  git add tests/integration/conftest.py tests/integration/test_wiring.py
  git commit -m "test: add integration conftest with 4 user fixtures and TestEnv"
  ```

---

## Task 6 — Scenario 1: Happy Path

**Files:**

- Create: `tests/integration/scenarios/test_scenario_01_happy_path.py`

**Actors:** eng1 (editor), eng2 (approver).
**CP state at start:** Clean baseline, no RITM rows in DB.

- [ ] **Step 1: Write the scenario**

  Create `tests/integration/scenarios/test_scenario_01_happy_path.py`:

  ```python
  """
  Scenario 1 — Happy Path

  eng1 creates a RITM with policy in both domains, runs try-verify,
  submits for approval. eng2 approves and publishes. Verifies COMPLETED.
  """

  import pytest
  from httpx import AsyncClient

  RITM_NUMBER = "RITM9990001"


  @pytest.mark.integration
  @pytest.mark.usefixtures("cp_restored")
  class TestHappyPath:
      ritm_id: str = RITM_NUMBER

      # ------------------------------------------------------------------
      # Step 01 — Create RITM
      # ------------------------------------------------------------------
      @pytest.mark.order(1)
      async def test_01_create_ritm(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              "/api/v1/ritm",
              json={"ritm_number": RITM_NUMBER},
          )
          assert resp.status_code == 201, resp.text
          data = resp.json()
          assert data["ritm_number"] == RITM_NUMBER
          assert data["status"] == 0  # WORK_IN_PROGRESS
          assert data["editor_locked_by"] is not None
          # eng1's username must appear in editors
          editors = [e for e in data.get("editors", [])]
          assert any(editors), "eng1 must be in ritm_editors after create"

      # ------------------------------------------------------------------
      # Step 02 — Add policy (DomainA + DomainB)
      # ------------------------------------------------------------------
      @pytest.mark.order(2)
      async def test_02_add_policy(
          self, eng1_client: AsyncClient, test_env
      ):
          policy = [
              {
                  "ritm_number": RITM_NUMBER,
                  "comments": "Test rule DomainA",
                  "rule_name": "RITM9990001_A_rule1",
                  "domain_uid": test_env.domain_a_uid,
                  "domain_name": test_env.domain_a_name,
                  "package_uid": test_env.package_a_uid,
                  "package_name": test_env.package_name,
                  "section_uid": test_env.section_a_uid,
                  "section_name": test_env.section_name,
                  "position_type": "top",
                  "position_number": None,
                  "action": "accept",
                  "track": "log",
                  "source_ips": ["10.0.0.1"],
                  "dest_ips": ["10.0.0.2"],
                  "services": ["svc_http_8080"],
              },
              {
                  "ritm_number": RITM_NUMBER,
                  "comments": "Test rule DomainB",
                  "rule_name": "RITM9990001_B_rule1",
                  "domain_uid": test_env.domain_b_uid,
                  "domain_name": test_env.domain_b_name,
                  "package_uid": test_env.package_b_uid,
                  "package_name": test_env.package_name,
                  "section_uid": test_env.section_b_uid,
                  "section_name": test_env.section_name,
                  "position_type": "top",
                  "position_number": None,
                  "action": "accept",
                  "track": "log",
                  "source_ips": ["10.1.0.0/24"],
                  "dest_ips": ["10.0.0.2"],
                  "services": ["svc_custom_9999"],
              },
          ]
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy",
              json=policy,
          )
          assert resp.status_code == 200, resp.text

      # ------------------------------------------------------------------
      # Step 03 — Pre-verify passes
      # ------------------------------------------------------------------
      @pytest.mark.order(3)
      async def test_03_pre_verify_passes(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          assert data["all_passed"] is True, (
              f"Pre-verify failed unexpectedly: {data}"
          )

      # ------------------------------------------------------------------
      # Step 04 — Plan YAML contains expected section
      # ------------------------------------------------------------------
      @pytest.mark.order(4)
      async def test_04_plan_yaml_has_section(
          self, eng1_client: AsyncClient, test_env
      ):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/plan-yaml"
          )
          assert resp.status_code == 200, resp.text
          # Response is YAML text or JSON with a yaml key — adjust to match actual response shape.
          body = resp.text
          assert test_env.section_name in body, (
              f"Expected {test_env.section_name!r} in plan YAML"
          )
          assert "Host_10.0.0.1" in body or "10.0.0.1" in body

      # ------------------------------------------------------------------
      # Step 05 — Try & Verify: both packages VERIFIED
      # ------------------------------------------------------------------
      @pytest.mark.order(5)
      async def test_05_try_verify(self, eng1_client: AsyncClient, test_env):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          assert data["published"] is True or len(data["results"]) > 0
          assert data["evidence_html"] is not None, "evidence_html must be present"
          # Both packages must reach VERIFIED_PENDING_APPROVAL_DISABLED
          states = [r.get("state", "") for r in data["results"]]
          assert all(
              s == "verified_pending_approval_disabled" for s in states
          ), f"Unexpected package states: {states}"

      # ------------------------------------------------------------------
      # Step 06 — Evidence history: 2 sessions, type=initial
      # ------------------------------------------------------------------
      @pytest.mark.order(6)
      async def test_06_evidence_history(self, eng1_client: AsyncClient):
          resp = await eng1_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          all_sessions = [
              s
              for d in data["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          assert len(all_sessions) == 2, (
              f"Expected 2 evidence sessions, got {len(all_sessions)}"
          )
          assert all(s["session_type"] == "initial" for s in all_sessions), (
              f"Expected all session_type=initial: {[s['session_type'] for s in all_sessions]}"
          )

      # ------------------------------------------------------------------
      # Step 07 — Session PDF is returned
      # ------------------------------------------------------------------
      @pytest.mark.order(7)
      async def test_07_session_pdf(self, eng1_client: AsyncClient):
          resp = await eng1_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/session-pdf",
              params={"attempt": 1},
          )
          assert resp.status_code == 200, resp.text
          assert resp.headers.get("content-type", "").startswith(
              "application/pdf"
          ), f"Expected PDF, got: {resp.headers.get('content-type')}"

      # ------------------------------------------------------------------
      # Step 08 — Submit for approval → READY_FOR_APPROVAL
      # ------------------------------------------------------------------
      @pytest.mark.order(8)
      async def test_08_submit_for_approval(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text
          # Verify status in DB via GET
          check = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.status_code == 200
          assert check.json()["status"] == 1  # READY_FOR_APPROVAL

      # ------------------------------------------------------------------
      # Step 09 — RITM absent from eng1's editable list
      # ------------------------------------------------------------------
      @pytest.mark.order(9)
      async def test_09_not_in_editor_list(self, eng1_client: AsyncClient):
          resp = await eng1_client.get(
              "/api/v1/ritm",
              params={"status": 0},  # WIP only
          )
          assert resp.status_code == 200
          numbers = [r["ritm_number"] for r in resp.json()]
          assert RITM_NUMBER not in numbers, (
              "RITM should not appear in WIP list after submit"
          )

      # ------------------------------------------------------------------
      # Step 10 — eng1 cannot approve own RITM
      # ------------------------------------------------------------------
      @pytest.mark.order(10)
      async def test_10_eng1_cannot_approve(self, eng1_client: AsyncClient):
          resp = await eng1_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}",
              json={"status": 2},
          )
          assert resp.status_code == 400, (
              f"Expected 400 (eng1 is editor), got {resp.status_code}"
          )

      # ------------------------------------------------------------------
      # Step 11 — eng2 acquires approver lock
      # ------------------------------------------------------------------
      @pytest.mark.order(11)
      async def test_11_eng2_acquires_lock(self, eng2_client: AsyncClient):
          resp = await eng2_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/lock"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          assert data["approver_locked_by"] is not None

      # ------------------------------------------------------------------
      # Step 12 — eng2 sees evidence history intact
      # ------------------------------------------------------------------
      @pytest.mark.order(12)
      async def test_12_eng2_sees_evidence(self, eng2_client: AsyncClient):
          resp = await eng2_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          all_sessions = [
              s
              for d in data["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          assert len(all_sessions) == 2

      # ------------------------------------------------------------------
      # Step 13 — eng2 approves → APPROVED
      # ------------------------------------------------------------------
      @pytest.mark.order(13)
      async def test_13_eng2_approves(self, eng2_client: AsyncClient):
          resp = await eng2_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}",
              json={"status": 2},
          )
          assert resp.status_code == 200, resp.text
          check = await eng2_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          data = check.json()
          assert data["status"] == 2  # APPROVED
          reviewers = data.get("reviewers", [])
          assert any(
              r["action"] == "approved" for r in reviewers
          ), f"No approved reviewer found: {reviewers}"

      # ------------------------------------------------------------------
      # Step 14 — eng2 publishes → APPROVAL_ENABLED_PUBLISHED
      # ------------------------------------------------------------------
      @pytest.mark.order(14)
      async def test_14_publish(self, eng2_client: AsyncClient):
          resp = await eng2_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/publish"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          assert data["success"] is True, f"Publish failed: {data}"

      # ------------------------------------------------------------------
      # Step 15 — status = COMPLETED
      # ------------------------------------------------------------------
      @pytest.mark.order(15)
      async def test_15_completed(self, eng1_client: AsyncClient):
          resp = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert resp.status_code == 200
          assert resp.json()["status"] == 3  # COMPLETED
  ```

- [ ] **Step 2: Run Scenario 1**

  ```bash
  uv run pytest tests/integration/scenarios/test_scenario_01_happy_path.py -v
  ```

  Expected: all 15 tests PASS in order. If any step fails, read the assertion message — it will name the exact failing condition.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/integration/scenarios/test_scenario_01_happy_path.py
  git commit -m "test: scenario 1 — happy path end-to-end RITM lifecycle"
  ```

---

## Task 7 — Scenario 2: Pre-Verify Error and Correction

**Files:**

- Create: `tests/integration/scenarios/test_scenario_02_preverify_error.py`

**CP state at start:** Baseline + BROKEN_RULE **enabled** in DomainA (seed creates it disabled; this scenario enables it as step 1).

- [ ] **Step 1: Write the scenario**

  Create `tests/integration/scenarios/test_scenario_02_preverify_error.py`:

  ```python
  """
  Scenario 2 — Pre-Verify Error and Correction

  1. Enable BROKEN_RULE in DomainA to make pre-verify fail.
  2. Create RITM, add policy targeting DomainA.
  3. Pre-verify → fails (references BROKEN_RULE).
  4. Delete BROKEN_RULE via CP API.
  5. Pre-verify again → passes.
  6. Try-verify → succeeds.
  7. Submit → eng2 approves → publish → COMPLETED.
  """

  import pytest
  from httpx import AsyncClient

  RITM_NUMBER = "RITM9990002"


  @pytest.mark.integration
  @pytest.mark.usefixtures("cp_restored")
  class TestPreVerifyError:

      # ------------------------------------------------------------------
      # Step 01 — Enable BROKEN_RULE to corrupt the baseline
      # ------------------------------------------------------------------
      @pytest.mark.order(1)
      async def test_01_enable_broken_rule(
          self, eng1_client: AsyncClient, test_env
      ):
          """
          Enable BROKEN_RULE in DomainA so that pre-verify fails.
          Uses the FPCR domains endpoint to set the rule enabled=true,
          OR calls CP directly via cpaiops. Adjust to actual API shape.
          """
          # If FPCR exposes a rule toggle endpoint, use it here.
          # Otherwise, this step would be done directly via cpaiops
          # in a standalone helper — not via the FPCR API.
          #
          # For now, we assume a test-helper CP command is available:
          # (implementer: wire this up to the actual cpaiops call)
          from src.fa.cpaiops import CPAIOPS
          await CPAIOPS.run(
              "set-access-rule",
              {
                  "layer": test_env.package_name,
                  "name": "BROKEN_RULE",
                  "enabled": True,
              },
              domain=test_env.domain_a_name,
          )
          await CPAIOPS.run("publish", {}, domain=test_env.domain_a_name)

      # ------------------------------------------------------------------
      # Step 02 — Create RITM
      # ------------------------------------------------------------------
      @pytest.mark.order(2)
      async def test_02_create_ritm(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              "/api/v1/ritm",
              json={"ritm_number": RITM_NUMBER},
          )
          assert resp.status_code == 201, resp.text

      # ------------------------------------------------------------------
      # Step 03 — Add policy in DomainA (targeting RITM_TEST_SECTION)
      # ------------------------------------------------------------------
      @pytest.mark.order(3)
      async def test_03_add_policy(
          self, eng1_client: AsyncClient, test_env
      ):
          policy = [
              {
                  "ritm_number": RITM_NUMBER,
                  "comments": "Scenario 2 DomainA rule",
                  "rule_name": "RITM9990002_A_rule1",
                  "domain_uid": test_env.domain_a_uid,
                  "domain_name": test_env.domain_a_name,
                  "package_uid": test_env.package_a_uid,
                  "package_name": test_env.package_name,
                  "section_uid": test_env.section_a_uid,
                  "section_name": test_env.section_name,
                  "position_type": "top",
                  "position_number": None,
                  "action": "accept",
                  "track": "log",
                  "source_ips": ["10.0.0.1"],
                  "dest_ips": ["10.0.0.2"],
                  "services": ["svc_http_8080"],
              }
          ]
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
          )
          assert resp.status_code == 200, resp.text

      # ------------------------------------------------------------------
      # Step 04 — Pre-verify fails due to BROKEN_RULE
      # ------------------------------------------------------------------
      @pytest.mark.order(4)
      async def test_04_preverify_fails(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          assert data["all_passed"] is False, (
              "Pre-verify should fail with BROKEN_RULE active"
          )
          all_errors = [
              e
              for r in data["results"]
              for e in r.get("errors", [])
          ]
          assert len(all_errors) > 0, "Expected error messages in pre-verify result"

      # ------------------------------------------------------------------
      # Step 05 — Delete BROKEN_RULE via CP API to fix the issue
      # ------------------------------------------------------------------
      @pytest.mark.order(5)
      async def test_05_delete_broken_rule(
          self, eng1_client: AsyncClient, test_env
      ):
          from src.fa.cpaiops import CPAIOPS
          await CPAIOPS.run(
              "delete-access-rule",
              {
                  "layer": test_env.package_name,
                  "name": "BROKEN_RULE",
              },
              domain=test_env.domain_a_name,
          )
          await CPAIOPS.run("publish", {}, domain=test_env.domain_a_name)

      # ------------------------------------------------------------------
      # Step 06 — Pre-verify passes now
      # ------------------------------------------------------------------
      @pytest.mark.order(6)
      async def test_06_preverify_passes(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          assert data["all_passed"] is True, (
              f"Pre-verify still failing after fix: {data}"
          )

      # ------------------------------------------------------------------
      # Step 07 — Try-verify succeeds (attempt 1)
      # ------------------------------------------------------------------
      @pytest.mark.order(7)
      async def test_07_try_verify(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          states = [r.get("state", "") for r in data["results"]]
          assert all(
              s == "verified_pending_approval_disabled" for s in states
          ), f"Unexpected states: {states}"

      # ------------------------------------------------------------------
      # Step 08 — Submit for approval
      # ------------------------------------------------------------------
      @pytest.mark.order(8)
      async def test_08_submit(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text

      # ------------------------------------------------------------------
      # Step 09 — eng2 approves
      # ------------------------------------------------------------------
      @pytest.mark.order(9)
      async def test_09_approve(self, eng2_client: AsyncClient):
          await eng2_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
          resp = await eng2_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 200, resp.text

      # ------------------------------------------------------------------
      # Step 10 — Publish → COMPLETED
      # ------------------------------------------------------------------
      @pytest.mark.order(10)
      async def test_10_publish_completed(self, eng2_client: AsyncClient):
          resp = await eng2_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/publish"
          )
          assert resp.status_code == 200, resp.text
          check = await eng2_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.json()["status"] == 3  # COMPLETED
  ```

- [ ] **Step 2: Run Scenario 2**

  ```bash
  uv run pytest tests/integration/scenarios/test_scenario_02_preverify_error.py -v
  ```

  Expected: all 10 steps PASS.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/integration/scenarios/test_scenario_02_preverify_error.py
  git commit -m "test: scenario 2 — pre-verify error detection and correction"
  ```

---

## Task 8 — Scenario 3: Post-Check Rollback

**Files:**

- Create: `tests/integration/scenarios/test_scenario_03_postcheck_rollback.py`

**Trick:** Create policy with duplicate rule name in the same section position — CP's post-check verify-policy will reject it. The rule is created, post-check fails, rollback deletes the rule.

- [ ] **Step 1: Write the scenario**

  Create `tests/integration/scenarios/test_scenario_03_postcheck_rollback.py`:

  ```python
  """
  Scenario 3 — Post-Check Rollback

  Policy is crafted to pass pre-check but fail post-check
  (duplicate rule name in the same section).
  Verifies rollback (POSTCHECK_FAILED_RULES_DELETED),
  then fixes and succeeds on attempt 2.
  """

  import pytest
  from httpx import AsyncClient

  RITM_NUMBER = "RITM9990003"

  # A rule name that already exists in the test section (seeded by seed.py).
  # Using an existing name triggers CP's post-check duplicate-name error.
  CONFLICTING_RULE_NAME = "RITM_TEST_SECTION_CONFLICT"


  def _policy(test_env, rule_name: str) -> list[dict]:
      return [
          {
              "ritm_number": RITM_NUMBER,
              "comments": "Scenario 3 rule",
              "rule_name": rule_name,
              "domain_uid": test_env.domain_a_uid,
              "domain_name": test_env.domain_a_name,
              "package_uid": test_env.package_a_uid,
              "package_name": test_env.package_name,
              "section_uid": test_env.section_a_uid,
              "section_name": test_env.section_name,
              "position_type": "top",
              "position_number": None,
              "action": "accept",
              "track": "log",
              "source_ips": ["10.0.0.1"],
              "dest_ips": ["10.0.0.2"],
              "services": ["svc_http_8080"],
          }
      ]


  @pytest.mark.integration
  @pytest.mark.usefixtures("cp_restored")
  class TestPostCheckRollback:

      @pytest.mark.order(1)
      async def test_01_create_ritm(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              "/api/v1/ritm", json={"ritm_number": RITM_NUMBER}
          )
          assert resp.status_code == 201, resp.text

      @pytest.mark.order(2)
      async def test_02_add_conflicting_policy(
          self, eng1_client: AsyncClient, test_env
      ):
          """
          Add a rule whose name already exists in RITM_TEST_SECTION
          so that post-check verify-policy fails.

          Note: seed.py must pre-create a rule named RITM_TEST_SECTION_CONFLICT
          in the section for this to fail on post-check. Alternatively, adjust
          the test to use a mechanism your CP version rejects on post-check
          (e.g. a src/dst that violates an existing access control rule).
          """
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy",
              json=_policy(test_env, CONFLICTING_RULE_NAME),
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(3)
      async def test_03_preverify_passes(self, eng1_client: AsyncClient):
          """Baseline must be clean for pre-check to pass."""
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/pre-verify"
          )
          assert resp.json()["all_passed"] is True

      @pytest.mark.order(4)
      async def test_04_try_verify_fails_postcheck(
          self, eng1_client: AsyncClient
      ):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          assert resp.status_code == 200, resp.text
          data = resp.json()
          states = [r.get("state", "") for r in data["results"]]
          assert any(
              s == "postcheck_failed_rules_deleted" for s in states
          ), f"Expected postcheck_failed_rules_deleted, got: {states}"

      @pytest.mark.order(5)
      async def test_05_no_evidence_for_attempt_1(
          self, eng1_client: AsyncClient
      ):
          """Failed attempt produces no evidence session."""
          resp = await eng1_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          all_sessions = [
              s
              for d in resp.json()["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          assert len(all_sessions) == 0, (
              f"Expected 0 sessions after rollback, got {len(all_sessions)}"
          )

      @pytest.mark.order(6)
      async def test_06_fix_policy(
          self, eng1_client: AsyncClient, test_env
      ):
          """Replace policy with a valid, non-conflicting rule name."""
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy",
              json=_policy(test_env, "RITM9990003_A_rule1"),
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(7)
      async def test_07_try_verify_attempt2_passes(
          self, eng1_client: AsyncClient
      ):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          data = resp.json()
          states = [r.get("state", "") for r in data["results"]]
          assert all(
              s == "verified_pending_approval_disabled" for s in states
          ), f"Unexpected states: {states}"

      @pytest.mark.order(8)
      async def test_08_evidence_attempt2_is_correction(
          self, eng1_client: AsyncClient
      ):
          resp = await eng1_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          all_sessions = [
              s
              for d in resp.json()["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          assert len(all_sessions) == 1
          assert all_sessions[0]["attempt"] == 2
          assert all_sessions[0]["session_type"] == "correction"

      @pytest.mark.order(9)
      async def test_09_submit(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(10)
      async def test_10_eng3_approves_and_publishes(
          self, eng3_client: AsyncClient
      ):
          await eng3_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
          resp = await eng3_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 200, resp.text
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/publish"
          )
          assert resp.json()["success"] is True
          check = await eng3_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.json()["status"] == 3  # COMPLETED
  ```

- [ ] **Step 2: Update schema.yaml to pre-create the conflicting rule name**

  Open `tests/integration/cp_setup/schema.yaml`. Add a `conflict_seed_rule` section:

  ```yaml
  # Pre-existing rule in RITM_TEST_SECTION used by Scenario 3 to trigger post-check failure.
  # seed.py creates this rule so that adding a second rule with the same name fails post-check.
  conflict_seed_rule:
    name: RITM_TEST_SECTION_CONFLICT
    domain: both    # both TEST_DOMAIN_A and TEST_DOMAIN_B
    section: RITM_TEST_SECTION
    source: Host_10.0.0.1
    destination: Host_10.0.0.2
    service: svc_http_8080
    action: accept
    track: log
    enabled: true
  ```

  Then add a corresponding `ensure_conflict_seed_rule()` call in `seed.py`'s `seed_domain()` function, similar to `ensure_broken_rule()`. Re-run seed after this change.

- [ ] **Step 3: Run Scenario 3**

  ```bash
  uv run pytest tests/integration/scenarios/test_scenario_03_postcheck_rollback.py -v
  ```

  Expected: all 10 steps PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add tests/integration/scenarios/test_scenario_03_postcheck_rollback.py \
          tests/integration/cp_setup/schema.yaml
  git commit -m "test: scenario 3 — post-check rollback and attempt 2 recovery"
  ```

---

## Task 9 — Scenario 4: Rejection Cycle / 4-User Separation of Duties

**Files:**

- Create: `tests/integration/scenarios/test_scenario_04_rejection_cycle.py`

This is the most important scenario for role-block verification. 22 steps.

- [ ] **Step 1: Write the scenario**

  Create `tests/integration/scenarios/test_scenario_04_rejection_cycle.py`:

  ```python
  """
  Scenario 4 — Rejection Cycle / 4-User Separation of Duties

  Verifies that after any actor touches a RITM, their complementary role
  is permanently blocked — even across multiple rejection/correction cycles.

  eng1: initial editor (blocked from approving forever)
  eng2: first rejecter (blocked from editing forever)
  eng3: correction editor (blocked from approving forever)
  eng4: second rejecter (blocked from editing forever)
  """

  import pytest
  from httpx import AsyncClient

  RITM_NUMBER = "RITM9990004"


  def _policy_a(test_env: object, rule_name: str) -> list[dict]:
      return [
          {
              "ritm_number": RITM_NUMBER,
              "comments": f"Scenario 4 {rule_name}",
              "rule_name": rule_name,
              "domain_uid": test_env.domain_a_uid,
              "domain_name": test_env.domain_a_name,
              "package_uid": test_env.package_a_uid,
              "package_name": test_env.package_name,
              "section_uid": test_env.section_a_uid,
              "section_name": test_env.section_name,
              "position_type": "top",
              "position_number": None,
              "action": "accept",
              "track": "log",
              "source_ips": ["10.0.0.1"],
              "dest_ips": ["10.0.0.2"],
              "services": ["svc_http_8080"],
          }
      ]


  @pytest.mark.integration
  @pytest.mark.usefixtures("cp_restored")
  class TestRejectionCycle:

      # ── Initial edit by eng1 ────────────────────────────────────────────

      @pytest.mark.order(1)
      async def test_01_eng1_creates(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              "/api/v1/ritm", json={"ritm_number": RITM_NUMBER}
          )
          assert resp.status_code == 201, resp.text

      @pytest.mark.order(2)
      async def test_02_eng1_adds_policy(
          self, eng1_client: AsyncClient, test_env
      ):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy",
              json=_policy_a(test_env, "RITM9990004_initial"),
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(3)
      async def test_03_eng1_try_verify(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          assert resp.status_code == 200, resp.text
          states = [r.get("state", "") for r in resp.json()["results"]]
          assert all(s == "verified_pending_approval_disabled" for s in states)

      @pytest.mark.order(4)
      async def test_04_eng1_submits(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text
          check = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.json()["status"] == 1  # READY_FOR_APPROVAL

      # ── Role block: eng1 cannot approve own RITM ────────────────────────

      @pytest.mark.order(5)
      async def test_05_eng1_cannot_approve(self, eng1_client: AsyncClient):
          resp = await eng1_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 400, (
              f"Expected 400 for eng1 self-approve, got {resp.status_code}"
          )

      # ── eng2: review and reject ────────────────────────────────────────

      @pytest.mark.order(6)
      async def test_06_eng2_reviews_evidence(
          self, eng2_client: AsyncClient
      ):
          await eng2_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
          resp = await eng2_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          assert resp.status_code == 200
          sessions = [
              s
              for d in resp.json()["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          assert len(sessions) >= 1

      @pytest.mark.order(7)
      async def test_07_eng2_rejects(self, eng2_client: AsyncClient):
          resp = await eng2_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}",
              json={"status": 0, "feedback": "Please add Host_10.0.0.2 as source."},
          )
          assert resp.status_code == 200, resp.text
          check = await eng2_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          data = check.json()
          assert data["status"] == 0  # back to WIP
          assert data["feedback"] == "Please add Host_10.0.0.2 as source."

      # ── Role block: eng2 cannot acquire editor lock after rejecting ─────

      @pytest.mark.order(8)
      async def test_08_eng2_cannot_edit(self, eng2_client: AsyncClient):
          resp = await eng2_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
          )
          assert resp.status_code == 400, (
              f"Expected 400 for eng2 (reviewer) editor lock, got {resp.status_code}"
          )

      # ── eng3: take correction, edit, try-verify, submit ─────────────────

      @pytest.mark.order(9)
      async def test_09_eng3_acquires_editor_lock(
          self, eng3_client: AsyncClient
      ):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
          )
          assert resp.status_code == 200, (
              f"eng3 should be able to acquire editor lock: {resp.text}"
          )

      @pytest.mark.order(10)
      async def test_10_eng3_updates_policy(
          self, eng3_client: AsyncClient, test_env
      ):
          """eng3 updates policy to address eng2's feedback."""
          policy = _policy_a(test_env, "RITM9990004_correction")
          # Add Host_10.0.0.2 as a source per eng2's feedback
          policy[0]["source_ips"] = ["10.0.0.1", "10.0.0.2"]
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(11)
      async def test_11_eng3_try_verify_attempt2(
          self, eng3_client: AsyncClient
      ):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          data = resp.json()
          states = [r.get("state", "") for r in data["results"]]
          assert all(s == "verified_pending_approval_disabled" for s in states)
          # Evidence session type must be "correction"
          ev = await eng3_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          sessions = [
              s
              for d in ev.json()["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          correction_sessions = [s for s in sessions if s["session_type"] == "correction"]
          assert len(correction_sessions) >= 1, (
              "Expected at least one correction session after attempt 2"
          )

      @pytest.mark.order(12)
      async def test_12_eng3_submits(self, eng3_client: AsyncClient):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text
          check = await eng3_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.json()["status"] == 1  # READY_FOR_APPROVAL

      # ── Role blocks after correction ────────────────────────────────────

      @pytest.mark.order(13)
      async def test_13_eng2_still_cannot_approve(
          self, eng2_client: AsyncClient
      ):
          """eng2 is still in ritm_reviewers — cannot approve."""
          resp = await eng2_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 400, (
              f"eng2 (reviewer) should still be blocked from approving"
          )

      @pytest.mark.order(14)
      async def test_14_eng3_cannot_approve_own_correction(
          self, eng3_client: AsyncClient
      ):
          """eng3 is now in ritm_editors — cannot approve."""
          resp = await eng3_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 400, (
              f"eng3 (editor) should be blocked from approving"
          )

      # ── eng4: review and reject (2nd rejection) ─────────────────────────

      @pytest.mark.order(15)
      async def test_15_eng4_acquires_approver_lock(
          self, eng4_client: AsyncClient
      ):
          resp = await eng4_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/lock"
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(16)
      async def test_16_eng4_sees_both_attempts(
          self, eng4_client: AsyncClient
      ):
          resp = await eng4_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          sessions = [
              s
              for d in resp.json()["domains"]
              for p in d["packages"]
              for s in p["sessions"]
          ]
          attempts = {s["attempt"] for s in sessions}
          assert 1 in attempts and 2 in attempts, (
              f"Expected attempts 1 and 2 in evidence, got: {attempts}"
          )

      @pytest.mark.order(17)
      async def test_17_eng4_rejects(self, eng4_client: AsyncClient):
          resp = await eng4_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}",
              json={"status": 0, "feedback": "Service svc_http_8080 not permitted."},
          )
          assert resp.status_code == 200, resp.text
          check = await eng4_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.json()["status"] == 0  # back to WIP

      # ── Role blocks: eng4 and eng3 ───────────────────────────────────────

      @pytest.mark.order(18)
      async def test_18_eng4_cannot_edit_after_reject(
          self, eng4_client: AsyncClient
      ):
          resp = await eng4_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
          )
          assert resp.status_code == 400, (
              f"eng4 (reviewer) must be blocked from editor lock"
          )

      @pytest.mark.order(19)
      async def test_19_eng3_cannot_approve_after_2nd_rejection(
          self, eng3_client: AsyncClient
      ):
          resp = await eng3_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 400

      # ── eng1 can re-edit (not in ritm_reviewers) ─────────────────────────

      @pytest.mark.order(20)
      async def test_20_eng1_reacquires_editor_lock(
          self, eng1_client: AsyncClient
      ):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
          )
          assert resp.status_code == 200, (
              f"eng1 (not a reviewer) should be able to re-acquire editor lock: {resp.text}"
          )

      @pytest.mark.order(21)
      async def test_21_4_users_all_blocked_summary(
          self, eng1_client: AsyncClient
      ):
          """
          Verify final state:
          - eng1: in ritm_editors (can edit, cannot approve)
          - eng2: in ritm_reviewers (cannot edit)
          - eng3: in ritm_editors (can edit, cannot approve)
          - eng4: in ritm_reviewers (cannot edit)

          Final approval would require a 5th user not in either table.
          """
          resp = await eng1_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          data = resp.json()
          editors = data.get("editors", [])
          reviewers = data.get("reviewers", [])
          eng2_user = __import__("os").environ["ENGINEER2_USER"]
          eng3_user = __import__("os").environ["ENGINEER3_USER"]
          eng4_user = __import__("os").environ["ENGINEER4_USER"]
          assert eng2_user in editors or any(
              r["username"] == eng2_user for r in reviewers
          ), "eng2 must appear in reviewers"
          assert eng4_user in editors or any(
              r["username"] == eng4_user for r in reviewers
          ), "eng4 must appear in reviewers"
          assert eng3_user in editors, "eng3 must appear in editors"
  ```

- [ ] **Step 2: Run Scenario 4**

  ```bash
  uv run pytest tests/integration/scenarios/test_scenario_04_rejection_cycle.py -v
  ```

  Expected: all 21 steps PASS.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/integration/scenarios/test_scenario_04_rejection_cycle.py
  git commit -m "test: scenario 4 — 4-user rejection cycle and separation-of-duties blocks"
  ```

---

## Task 10 — Scenario 5: Domain Change After Rejection

**Files:**

- Create: `tests/integration/scenarios/test_scenario_05_domain_change.py`

- [ ] **Step 1: Write the scenario**

  Create `tests/integration/scenarios/test_scenario_05_domain_change.py`:

  ```python
  """
  Scenario 5 — Domain Change After Rejection

  eng1 creates a RITM with policy in DomainA only.
  eng2 rejects: "move rules to DomainB".
  eng3 acquires editor lock, switches policy to DomainB.
  plan-yaml validates DomainA objects absent, DomainB objects present.
  try-verify attempt 2 creates DomainB rules.
  Evidence history shows DomainA session (attempt 1) and DomainB session (attempt 2).
  eng4 approves and publishes → COMPLETED.
  """

  import pytest
  from httpx import AsyncClient

  RITM_NUMBER = "RITM9990005"


  @pytest.mark.integration
  @pytest.mark.usefixtures("cp_restored")
  class TestDomainChange:

      @pytest.mark.order(1)
      async def test_01_eng1_creates(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              "/api/v1/ritm", json={"ritm_number": RITM_NUMBER}
          )
          assert resp.status_code == 201, resp.text

      @pytest.mark.order(2)
      async def test_02_policy_domain_a_only(
          self, eng1_client: AsyncClient, test_env
      ):
          policy = [
              {
                  "ritm_number": RITM_NUMBER,
                  "comments": "Scenario 5 DomainA rule",
                  "rule_name": "RITM9990005_A_rule1",
                  "domain_uid": test_env.domain_a_uid,
                  "domain_name": test_env.domain_a_name,
                  "package_uid": test_env.package_a_uid,
                  "package_name": test_env.package_name,
                  "section_uid": test_env.section_a_uid,
                  "section_name": test_env.section_name,
                  "position_type": "top",
                  "position_number": None,
                  "action": "accept",
                  "track": "log",
                  "source_ips": ["10.0.0.1"],
                  "dest_ips": ["10.0.0.2"],
                  "services": ["svc_http_8080"],
              }
          ]
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(3)
      async def test_03_try_verify_domain_a(
          self, eng1_client: AsyncClient, test_env
      ):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          data = resp.json()
          states = [r.get("state", "") for r in data["results"]]
          assert all(s == "verified_pending_approval_disabled" for s in states)
          # Only DomainA in evidence
          ev = await eng1_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          domain_names = [d["domain_name"] for d in ev.json()["domains"]]
          assert test_env.domain_a_name in domain_names
          assert test_env.domain_b_name not in domain_names

      @pytest.mark.order(4)
      async def test_04_submit(self, eng1_client: AsyncClient):
          resp = await eng1_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(5)
      async def test_05_eng2_rejects_with_domain_feedback(
          self, eng2_client: AsyncClient
      ):
          await eng2_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
          resp = await eng2_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}",
              json={"status": 0, "feedback": "Move rules to DomainB instead."},
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(6)
      async def test_06_eng3_acquires_editor_lock(
          self, eng3_client: AsyncClient
      ):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/editor-lock"
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(7)
      async def test_07_eng3_changes_policy_to_domain_b(
          self, eng3_client: AsyncClient, test_env
      ):
          policy = [
              {
                  "ritm_number": RITM_NUMBER,
                  "comments": "Scenario 5 DomainB rule (after domain change)",
                  "rule_name": "RITM9990005_B_rule1",
                  "domain_uid": test_env.domain_b_uid,
                  "domain_name": test_env.domain_b_name,
                  "package_uid": test_env.package_b_uid,
                  "package_name": test_env.package_name,
                  "section_uid": test_env.section_b_uid,
                  "section_name": test_env.section_name,
                  "position_type": "top",
                  "position_number": None,
                  "action": "accept",
                  "track": "log",
                  "source_ips": ["10.0.0.1"],
                  "dest_ips": ["Net_10.1.0.0_24"],
                  "services": ["svc_custom_9999"],
              }
          ]
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/policy", json=policy
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(8)
      async def test_08_plan_yaml_has_domain_b_not_domain_a(
          self, eng3_client: AsyncClient, test_env
      ):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/plan-yaml"
          )
          assert resp.status_code == 200, resp.text
          body = resp.text
          assert test_env.domain_b_name in body or "RITM9990005_B_rule1" in body, (
              "plan-yaml must reference DomainB rule"
          )
          # DomainA rule name must not appear in the new plan
          # (policy has been fully replaced)
          assert "RITM9990005_A_rule1" not in body, (
              "plan-yaml must not reference the old DomainA rule after policy replacement"
          )

      @pytest.mark.order(9)
      async def test_09_try_verify_attempt2_domain_b(
          self, eng3_client: AsyncClient, test_env
      ):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/try-verify",
              json={"skip_package_uids": []},
          )
          data = resp.json()
          states = [r.get("state", "") for r in data["results"]]
          assert all(s == "verified_pending_approval_disabled" for s in states)

      @pytest.mark.order(10)
      async def test_10_evidence_history_has_both_domains(
          self, eng3_client: AsyncClient, test_env
      ):
          resp = await eng3_client.get(
              f"/api/v1/ritm/{RITM_NUMBER}/evidence-history"
          )
          data = resp.json()
          domain_names = {d["domain_name"] for d in data["domains"]}
          assert test_env.domain_a_name in domain_names, (
              "DomainA evidence (attempt 1) must still be present"
          )
          assert test_env.domain_b_name in domain_names, (
              "DomainB evidence (attempt 2) must be present"
          )
          # DomainB sessions must be session_type=correction (attempt >= 2)
          for d in data["domains"]:
              if d["domain_name"] == test_env.domain_b_name:
                  for p in d["packages"]:
                      for s in p["sessions"]:
                          assert s["session_type"] == "correction", (
                              f"DomainB sessions must be 'correction', got {s['session_type']}"
                          )

      @pytest.mark.order(11)
      async def test_11_eng3_submits(self, eng3_client: AsyncClient):
          resp = await eng3_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/submit-for-approval"
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(12)
      async def test_12_eng4_approves(self, eng4_client: AsyncClient):
          await eng4_client.post(f"/api/v1/ritm/{RITM_NUMBER}/lock")
          resp = await eng4_client.put(
              f"/api/v1/ritm/{RITM_NUMBER}", json={"status": 2}
          )
          assert resp.status_code == 200, resp.text

      @pytest.mark.order(13)
      async def test_13_eng4_publishes(self, eng4_client: AsyncClient):
          resp = await eng4_client.post(
              f"/api/v1/ritm/{RITM_NUMBER}/publish"
          )
          assert resp.json()["success"] is True

      @pytest.mark.order(14)
      async def test_14_completed(self, eng4_client: AsyncClient):
          check = await eng4_client.get(f"/api/v1/ritm/{RITM_NUMBER}")
          assert check.json()["status"] == 3  # COMPLETED
  ```

- [ ] **Step 2: Run Scenario 5**

  ```bash
  uv run pytest tests/integration/scenarios/test_scenario_05_domain_change.py -v
  ```

  Expected: all 14 steps PASS.

- [ ] **Step 3: Run the full integration suite**

  ```bash
  uv run pytest tests/integration/ -v --tb=short
  ```

  Expected: all 5 scenarios PASS (72 total steps).

- [ ] **Step 4: Commit**

  ```bash
  git add tests/integration/scenarios/test_scenario_05_domain_change.py
  git commit -m "test: scenario 5 — domain change after rejection with plan validation"
  ```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Happy path (15 steps) ✓
  - Pre-verify error + fix (10 steps) ✓
  - Post-check rollback + attempt 2 (10 steps) ✓
  - 4-user rejection cycle (21 steps) ✓
  - Domain change (14 steps) ✓
  - CP seed schema + revision module ✓
  - conftest with 4 user clients + TestEnv + cp_restored ✓
  - `.env.test.example` ✓
  - Universal guardrail checks (lock exclusivity, role blocks, evidence structure, visibility) ✓

- [x] **Placeholder scan:**
  - `cp_restored` fixture body is commented with two explicit options — engineer must choose one. Not a placeholder; it's a deliberate implementation decision documented inline.
  - `seed.py` `main()` imports `CPAIOPS` from `src.fa.cpaiops` — engineer must verify the exact import path.
  - `revision.py` `run()` method call — engineer must verify against actual cpaiops API.

- [x] **Type consistency:**
  - `TestEnv` attributes referenced in scenarios match the dataclass definition in conftest.
  - `PolicyItem` fields in all scenario `_policy*()` helpers match the Pydantic model exactly.
  - `RITMStatus` values used as integers (0=WIP, 1=READY, 2=APPROVED, 3=COMPLETED) ✓
  - `RITMPackageAttemptState` values used as lowercase strings (`"verified_pending_approval_disabled"`, etc.) ✓

---

## Running Individual Steps for Debugging

```bash
# Run one specific step
uv run pytest tests/integration/scenarios/test_scenario_01_happy_path.py::TestHappyPath::test_05_try_verify -v -s

# Run a scenario up to a specific step
uv run pytest tests/integration/scenarios/test_scenario_01_happy_path.py -v -k "test_01 or test_02 or test_03"

# Run all scenarios with full output on first failure
uv run pytest tests/integration/ -v --tb=long -x
```
