# Mock Data Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable FPCR WebUI to operate without Check Point API by reading domains, packages, and sections from a local mock data file.

**Architecture:** Create a `MockDataSource` class that substitutes for `CPAIOPSClient` when `MOCK_DATA` environment variable is set. Routes detect mock mode and return data from the file instead of making API calls. UIDs are auto-generated where missing, and rulebase ranges are calculated sequentially from rule counts.

**Tech Stack:** Python 3.13, FastAPI, ruamel.yaml (YAML parsing), uuid4 (UID generation), pytest (testing)

---

## Task 1: Create MockDataSource class skeleton

**Files:**

- Create: `src/fa/mock_source.py`

**Step 1: Write the failing test**

Create `tests/test_mock_source.py`:

```python
"""Tests for MockDataSource."""

import pytest
from fa.mock_source import MockDataSource


def test_mock_data_source_init_with_yaml(tmp_path):
    """Test MockDataSource initializes with YAML file."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))
    assert mock.data is not None
    assert "TEST_DOMAIN" in mock.data.get("domains", {})


def test_mock_data_source_init_with_json(tmp_path):
    """Test MockDataSource initializes with JSON file."""
    json_file = tmp_path / "test.json"
    json_file.write_text('{"domains": {"TEST_DOMAIN": {"policies": {"TEST_POLICY": {"sections": {"init": 3}}}}}}')
    mock = MockDataSource(str(json_file))
    assert mock.data is not None
    assert "TEST_DOMAIN" in mock.data.get("domains", {})
```

**Step 2: Run test to verify it fails**

```bash
cd /d/Files/GSe_new/2026/Labs/Dev/FPCR
uv run pytest tests/test_mock_source.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'fa.mock_source'"

**Step 3: Write minimal implementation**

Create `src/fa/mock_source.py`:

```python
"""Mock data source for WebUI testing without Check Point API."""

import json
from pathlib import Path
from ruamel.yaml import YAML


class MockDataSource:
    """Mock data source that reads from local file instead of Check Point API."""

    def __init__(self, file_path: str):
        """Load and parse mock data file (JSON or YAML)."""
        self.file_path = Path(file_path)
        self.data = self._load_file()

    def _load_file(self) -> dict:
        """Load file based on extension (json or yaml)."""
        if not self.file_path.exists():
            return {}

        suffix = self.file_path.suffix.lower()

        if suffix == ".json":
            with open(self.file_path) as f:
                return json.load(f)
        elif suffix in [".yaml", ".yml"]:
            yaml = YAML(typ="safe")
            with open(self.file_path) as f:
                return yaml.load(f) or {}
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_mock_source.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/mock_source.py tests/test_mock_source.py
git commit -m "feat: add MockDataSource class skeleton with YAML/JSON support"
```

---

## Task 2: Add UID auto-generation

**Files:**

- Modify: `src/fa/mock_source.py`
- Test: `tests/test_mock_source.py`

**Step 1: Write the failing test**

Add to `tests/test_mock_source.py`:

```python
import uuid


def test_auto_generate_domain_uids(tmp_path):
    """Test that UIDs are auto-generated for domains."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))
    domains = mock.get_domains()

    assert len(domains) == 1
    assert domains[0].name == "TEST_DOMAIN"
    assert domains[0].uid is not None
    # Should be a valid UUID string
    uuid.UUID(domains[0].uid)  # Raises ValueError if invalid


def test_uids_consistent_across_calls(tmp_path):
    """Test that same UID is returned on subsequent calls."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))
    domains1 = mock.get_domains()
    domains2 = mock.get_domains()

    assert domains1[0].uid == domains2[0].uid
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_mock_source.py::test_auto_generate_domain_uids -v
```

Expected: FAIL with "MockDataSource has no attribute 'get_domains'"

**Step 3: Write minimal implementation**

Update `src/fa/mock_source.py`:

```python
"""Mock data source for WebUI testing without Check Point API."""

import json
import uuid
from pathlib import Path
from ruamel.yaml import YAML
from fa.models import DomainItem, PackageItem, SectionItem


class MockDataSource:
    """Mock data source that reads from local file instead of Check Point API."""

    def __init__(self, file_path: str):
        """Load and parse mock data file (JSON or YAML)."""
        self.file_path = Path(file_path)
        self.data = self._load_file()
        self._uids: dict[str, str] = {}  # Cache for generated UIDs
        self._ensure_uids()

    def _load_file(self) -> dict:
        """Load file based on extension (json or yaml)."""
        if not self.file_path.exists():
            return {"domains": {}}

        suffix = self.file_path.suffix.lower()

        if suffix == ".json":
            with open(self.file_path) as f:
                return json.load(f)
        elif suffix in [".yaml", ".yml"]:
            yaml = YAML(typ="safe")
            with open(self.file_path) as f:
                return yaml.load(f) or {}
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def _ensure_uids(self):
        """Auto-generate UIDs for entities missing them."""
        domains = self.data.get("domains", {})

        for domain_name, domain_data in domains.items():
            domain_key = f"domain:{domain_name}"
            if domain_key not in self._uids:
                self._uids[domain_key] = str(uuid.uuid4())

            policies = domain_data.get("policies", {})
            for policy_name, policy_data in policies.items():
                policy_key = f"policy:{domain_name}:{policy_name}"
                if policy_key not in self._uids:
                    self._uids[policy_key] = str(uuid.uuid4())

                sections = policy_data.get("sections", {})
                for section_name in sections.keys():
                    section_key = f"section:{domain_name}:{policy_name}:{section_name}"
                    if section_key not in self._uids:
                        self._uids[section_key] = str(uuid.uuid4())

                firewalls = policy_data.get("firewalls", {})
                for fw_name in firewalls.keys():
                    fw_key = f"firewall:{domain_name}:{policy_name}:{fw_name}"
                    if fw_key not in self._uids:
                        self._uids[fw_key] = str(uuid.uuid4())

    def _get_domain_uid(self, domain_name: str) -> str:
        """Get or generate UID for a domain."""
        key = f"domain:{domain_name}"
        if key not in self._uids:
            self._uids[key] = str(uuid.uuid4())
        return self._uids[key]

    def _get_policy_uid(self, domain_name: str, policy_name: str) -> str:
        """Get or generate UID for a policy."""
        key = f"policy:{domain_name}:{policy_name}"
        if key not in self._uids:
            self._uids[key] = str(uuid.uuid4())
        return self._uids[key]

    def _get_section_uid(self, domain_name: str, policy_name: str, section_name: str) -> str:
        """Get or generate UID for a section."""
        key = f"section:{domain_name}:{policy_name}:{section_name}"
        if key not in self._uids:
            self._uids[key] = str(uuid.uuid4())
        return self._uids[key]

    def get_domains(self) -> list[DomainItem]:
        """Return all domains with auto-generated UIDs."""
        domains = []
        for name in self.data.get("domains", {}).keys():
            domains.append(DomainItem(name=name, uid=self._get_domain_uid(name)))
        return domains
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_mock_source.py::test_auto_generate_domain_uids tests/test_mock_source.py::test_uids_consistent_across_calls -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/mock_source.py tests/test_mock_source.py
git commit -m "feat: add UID auto-generation to MockDataSource"
```

---

## Task 3: Implement get_packages method

**Files:**

- Modify: `src/fa/mock_source.py`
- Test: `tests/test_mock_source.py`

**Step 1: Write the failing test**

Add to `tests/test_mock_source.py`:

```python
def test_get_packages_for_domain(tmp_path):
    """Test getting packages for a specific domain."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  DOMAIN_1:
    policies:
      POLICY_A:
        sections:
          init: 3
  DOMAIN_2:
    policies:
      POLICY_B:
        sections:
          init: 5
""")
    mock = MockDataSource(str(yaml_file))
    domain_uid = mock._get_domain_uid("DOMAIN_1")

    packages = mock.get_packages(domain_uid)

    assert len(packages) == 1
    assert packages[0].name == "POLICY_A"
    assert packages[0].uid is not None


def test_get_packages_unknown_domain(tmp_path):
    """Test getting packages for unknown domain returns empty list."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  DOMAIN_1:
    policies:
      POLICY_A:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))

    packages = mock.get_packages("unknown-uid")

    assert len(packages) == 0
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_mock_source.py::test_get_packages_for_domain -v
```

Expected: FAIL with "MockDataSource has no attribute 'get_packages'"

**Step 3: Write minimal implementation**

Add to `src/fa/mock_source.py` (after `get_domains` method):

```python
    def get_packages(self, domain_uid: str) -> list[PackageItem]:
        """Return packages for a domain."""
        # Find domain name by UID
        domain_name = None
        for name in self.data.get("domains", {}).keys():
            if self._get_domain_uid(name) == domain_uid:
                domain_name = name
                break

        if not domain_name:
            return []

        packages = []
        policies = self.data.get("domains", {}).get(domain_name, {}).get("policies", {})
        for policy_name in policies.keys():
            packages.append(
                PackageItem(
                    name=policy_name,
                    uid=self._get_policy_uid(domain_name, policy_name),
                    access_layer=f"{policy_name}-layer",  # Auto-generate layer name
                )
            )
        return packages
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_mock_source.py::test_get_packages_for_domain tests/test_mock_source.py::test_get_packages_unknown_domain -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/mock_source.py tests/test_mock_source.py
git commit -m "feat: add get_packages method to MockDataSource"
```

---

## Task 4: Implement get_sections with sequential rulebase ranges

**Files:**

- Modify: `src/fa/mock_source.py`
- Test: `tests/test_mock_source.py`

**Step 1: Write the failing test**

Add to `tests/test_mock_source.py`:

```python
def test_get_sections_with_sequential_ranges(tmp_path):
    """Test that sections have sequential rulebase ranges."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
          ingress: 5
          egress: 2
""")
    mock = MockDataSource(str(yaml_file))
    domain_uid = mock._get_domain_uid("TEST_DOMAIN")
    policy_uid = mock._get_policy_uid("TEST_DOMAIN", "TEST_POLICY")

    sections, total = mock.get_sections(domain_uid, policy_uid)

    assert len(sections) == 3
    # init: rules 1-3 (3 rules)
    assert sections[0].name == "init"
    assert sections[0].rulebase_range == (1, 3)
    assert sections[0].rule_count == 3
    # ingress: rules 4-8 (5 rules)
    assert sections[1].name == "ingress"
    assert sections[1].rulebase_range == (4, 8)
    assert sections[1].rule_count == 5
    # egress: rules 9-10 (2 rules)
    assert sections[2].name == "egress"
    assert sections[2].rulebase_range == (9, 10)
    assert sections[2].rule_count == 2
    # total rules
    assert total == 10


def test_get_sections_unknown_policy(tmp_path):
    """Test getting sections for unknown policy returns empty."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))

    sections, total = mock.get_sections("unknown", "unknown")

    assert len(sections) == 0
    assert total == 0
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_mock_source.py::test_get_sections_with_sequential_ranges -v
```

Expected: FAIL with "MockDataSource has no attribute 'get_sections'"

**Step 3: Write minimal implementation**

Add to `src/fa/mock_source.py` (after `get_packages` method):

```python
    def get_sections(self, domain_uid: str, package_uid: str) -> tuple[list[SectionItem], int]:
        """Return sections with sequential rulebase ranges and total rule count."""
        # Find domain and policy by UIDs
        domain_name = None
        policy_name = None

        for d_name in self.data.get("domains", {}).keys():
            if self._get_domain_uid(d_name) == domain_uid:
                domain_name = d_name
                policies = self.data.get("domains", {}).get(d_name, {}).get("policies", {})
                for p_name in policies.keys():
                    if self._get_policy_uid(d_name, p_name) == package_uid:
                        policy_name = p_name
                        break
                break

        if not domain_name or not policy_name:
            return [], 0

        sections_data = self.data.get("domains", {}).get(domain_name, {}).get("policies", {}).get(policy_name, {}).get("sections", {})

        sections = []
        current_rule = 1

        for section_name, rule_count in sections_data.items():
            section_min = current_rule
            section_max = current_rule + rule_count - 1
            sections.append(
                SectionItem(
                    name=section_name,
                    uid=self._get_section_uid(domain_name, policy_name, section_name),
                    rulebase_range=(section_min, section_max),
                    rule_count=rule_count,
                )
            )
            current_rule = section_max + 1

        total_rules = current_rule - 1
        return sections, total_rules
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_mock_source.py::test_get_sections_with_sequential_ranges tests/test_mock_source.py::test_get_sections_unknown_policy -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/mock_source.py tests/test_mock_source.py
git commit -m "feat: add get_sections with sequential rulebase range calculation"
```

---

## Task 5: Add error handling for missing/invalid files

**Files:**

- Modify: `src/fa/mock_source.py`
- Test: `tests/test_mock_source.py`

**Step 1: Write the failing test**

Add to `tests/test_mock_source.py`:

```python
def test_missing_file_returns_empty_domains(tmp_path):
    """Test that missing file returns empty domain list."""
    mock = MockDataSource(str(tmp_path / "nonexistent.yaml"))
    domains = mock.get_domains()
    assert domains == []


def test_invalid_yaml_raises_error(tmp_path, caplog):
    """Test that invalid YAML returns empty results gracefully."""
    import logging

    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text("domains: [invalid yaml structure")

    mock = MockDataSource(str(yaml_file))
    domains = mock.get_domains()
    # Should return empty, not crash
    assert domains == []
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_mock_source.py::test_missing_file_returns_empty_domains tests/test_mock_source.py::test_invalid_yaml_raises_error -v
```

Expected: FAIL or ERROR (depends on current behavior)

**Step 3: Write minimal implementation**

Update `_load_file` method in `src/fa/mock_source.py`:

```python
    def _load_file(self) -> dict:
        """Load file based on extension (json or yaml)."""
        if not self.file_path.exists():
            return {"domains": {}}

        suffix = self.file_path.suffix.lower()

        try:
            if suffix == ".json":
                with open(self.file_path) as f:
                    return json.load(f)
            elif suffix in [".yaml", ".yml"]:
                yaml = YAML(typ="safe")
                with open(self.file_path) as f:
                    result = yaml.load(f)
                    return result if result else {}
            else:
                return {"domains": {}}
        except Exception:
            # Return empty dict on parse errors
            return {"domains": {}}
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_mock_source.py::test_missing_file_returns_empty_domains tests/test_mock_source.py::test_invalid_yaml_raises_error -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/mock_source.py tests/test_mock_source.py
git commit -m "feat: add graceful error handling for missing/invalid mock files"
```

---

## Task 6: Integrate MockDataSource into domains route

**Files:**

- Modify: `src/fa/routes/domains.py`
- Test: Create `tests/fa/test_routes_mock.py`

**Step 1: Write the failing test**

Create `tests/fa/test_routes_mock.py`:

```python
"""Tests for route handlers with mock data source."""

import os
import pytest
from fastapi.testclient import TestClient
from fa.app import create_app


@pytest.fixture
def mock_env(tmp_path, monkeypatch):
    """Set up mock environment."""
    yaml_file = tmp_path / "mock.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN_1:
    policies:
      TEST_POLICY:
        sections:
          init: 3
  TEST_DOMAIN_2:
    policies:
      ANOTHER_POLICY:
        sections:
          ingress: 5
""")
    monkeypatch.setenv("MOCK_DATA", str(yaml_file))
    monkeypatch.setenv("API_MGMT", "127.0.0.1")  # Not used but required
    return yaml_file


@pytest.fixture
def client(mock_env):
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_list_domains_with_mock(client, mock_env):
    """Test /domains endpoint uses mock data when MOCK_DATA is set."""
    # First, login to get session
    login_response = client.post(
        "/api/v1/login",
        json={"username": "test", "password": "test"}
    )
    assert login_response.status_code == 200

    # Get domains
    response = client.get("/api/v1/domains")
    assert response.status_code == 200

    data = response.json()
    assert "domains" in data
    assert len(data["domains"]) == 2
    domain_names = [d["name"] for d in data["domains"]]
    assert "TEST_DOMAIN_1" in domain_names
    assert "TEST_DOMAIN_2" in domain_names
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/fa/test_routes_mock.py::test_list_domains_with_mock -v
```

Expected: FAIL (routes don't check MOCK_DATA yet)

**Step 3: Write minimal implementation**

Update `src/fa/routes/domains.py`:

```python
"""Domain endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from cpaiops import CPAIOPSClient

from ..db import engine
from ..models import ErrorResponse
from ..mock_source import MockDataSource
from ..session import SessionData, SessionManager, session_manager

router = APIRouter(tags=["domains"])


async def get_session_data(request: Request):
    """Dependency to get current session."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


class DomainItem(BaseModel):
    """Single domain item."""

    name: str
    uid: str


class DomainsResponse(BaseModel):
    """Domains list response."""

    domains: list[DomainItem]


@router.get("/domains", response_model=DomainsResponse)
async def list_domains(session: SessionData = Depends(get_session_data)):
    """
    List all Check Point domains.

    Uses MOCK_DATA file if configured, otherwise connects to
    Check Point API with authenticated user's credentials.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        return DomainsResponse(domains=mock.get_domains())

    # Original API code continues...
    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    client = CPAIOPSClient(
        engine=engine,
        username=session.username,
        password=session.password,
        mgmt_ip=mgmt_ip,
    )

    try:
        async with client:
            server_names = client.get_mgmt_names()
            if not server_names:
                return DomainsResponse(domains=[])

            mgmt_name = server_names[0]
            result = await client.api_query(mgmt_name, "show-domains")

            if result.success:
                domains = [
                    DomainItem(name=obj.get("name", ""), uid=obj.get("uid", ""))
                    for obj in (result.objects or [])
                ]
                return DomainsResponse(domains=domains)
            else:
                raise HTTPException(
                    status_code=500, detail=f"Check Point API error: {result.message}"
                )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect to Check Point: {str(e)}")
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/fa/test_routes_mock.py::test_list_domains_with_mock -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/routes/domains.py tests/fa/test_routes_mock.py
git commit -m "feat: integrate MockDataSource into domains route"
```

---

## Task 7: Integrate MockDataSource into packages route

**Files:**

- Modify: `src/fa/routes/packages.py`
- Test: `tests/fa/test_routes_mock.py`

**Step 1: Write the failing test**

Add to `tests/fa/test_routes_mock.py`:

```python
def test_list_packages_with_mock(client):
    """Test /packages endpoint uses mock data when MOCK_DATA is set."""
    # Login
    client.post("/api/v1/login", json={"username": "test", "password": "test"})

    # Get domains first
    domains_response = client.get("/api/v1/domains")
    domains = domains_response.json()["domains"]
    domain_uid = domains[0]["uid"]

    # Get packages
    response = client.get(f"/api/v1/domains/{domain_uid}/packages")
    assert response.status_code == 200

    data = response.json()
    assert "packages" in data
    assert len(data["packages"]) == 1
    assert data["packages"][0]["name"] == "TEST_POLICY"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/fa/test_routes_mock.py::test_list_packages_with_mock -v
```

Expected: FAIL (packages route doesn't check MOCK_DATA yet)

**Step 3: Write minimal implementation**

Update `src/fa/routes/packages.py`:

Add import at top:

```python
from ..mock_source import MockDataSource
```

Update `list_packages` function:

```python
@router.get("/domains/{domain_uid}/packages", response_model=PackagesResponse)
async def list_packages(
    domain_uid: str, session: SessionData = Depends(get_session_data)
):
    """
    List all policy packages for a domain.

    Uses MOCK_DATA file if configured, otherwise connects to
    Check Point API with authenticated user's credentials.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        return PackagesResponse(packages=mock.get_packages(domain_uid))

    # Original API code continues...
    mgmt_ip = os.getenv("API_MGMT")
    # ... rest of original code unchanged ...
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/fa/test_routes_mock.py::test_list_packages_with_mock -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/routes/packages.py tests/fa/test_routes_mock.py
git commit -m "feat: integrate MockDataSource into packages route"
```

---

## Task 8: Integrate MockDataSource into sections route

**Files:**

- Modify: `src/fa/routes/packages.py`
- Test: `tests/fa/test_routes_mock.py`

**Step 1: Write the failing test**

Add to `tests/fa/test_routes_mock.py`:

```python
def test_list_sections_with_mock(client):
    """Test /sections endpoint uses mock data when MOCK_DATA is set."""
    # Login
    client.post("/api/v1/login", json={"username": "test", "password": "test"})

    # Get domains
    domains_response = client.get("/api/v1/domains")
    domain_uid = domains_response.json()["domains"][0]["uid"]

    # Get packages
    packages_response = client.get(f"/api/v1/domains/{domain_uid}/packages")
    package_uid = packages_response.json()["packages"][0]["uid"]

    # Get sections
    response = client.get(f"/api/v1/domains/{domain_uid}/packages/{package_uid}/sections")
    assert response.status_code == 200

    data = response.json()
    assert "sections" in data
    assert "total_rules" in data
    assert data["total_rules"] == 3
    assert len(data["sections"]) == 1
    assert data["sections"][0]["name"] == "init"
    assert data["sections"][0]["rulebase_range"] == [1, 3]
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/fa/test_routes_mock.py::test_list_sections_with_mock -v
```

Expected: FAIL (sections route doesn't check MOCK_DATA yet)

**Step 3: Write minimal implementation**

Update `list_sections` function in `src/fa/routes/packages.py`:

```python
@router.get(
    "/domains/{domain_uid}/packages/{pkg_uid}/sections",
    response_model=SectionsResponse,
)
async def list_sections(
    domain_uid: str,
    pkg_uid: str,
    session: SessionData = Depends(get_session_data),
):
    """
    List all sections for a policy package with rule ranges.

    Uses MOCK_DATA file if configured, otherwise connects to
    Check Point API with authenticated user's credentials.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        sections, total = mock.get_sections(domain_uid, pkg_uid)
        return SectionsResponse(sections=sections, total_rules=total)

    # Original API code continues...
    mgmt_ip = os.getenv("API_MGMT")
    # ... rest of original code unchanged ...
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/fa/test_routes_mock.py::test_list_sections_with_mock -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/fa/routes/packages.py tests/fa/test_routes_mock.py
git commit -m "feat: integrate MockDataSource into sections route"
```

---

## Task 9: Create sample mock_data.yaml file

**Files:**

- Create: `mock_data.yaml`

**Step 1: Create the file**

```bash
cat > mock_data.yaml << 'EOF'
# Mock data file for FPCR WebUI testing
# When MOCK_DATA=mock_data.yaml is set in .env, the WebUI uses this data
# instead of connecting to Check Point API.

domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW:
            subnets:
              - 10.76.66.0/24
        sections:
          init: 3
          ingress: 5
          egress: 5
          cleanup: 2
  AME_DC:
    policies:
      US-NY-DC:
        firewalls:
          US-NY-DC:
            subnets:
              - 10.76.67.0/24
        sections:
          init: 4
          ingress: 4
          egress: 6
          cleanup: 1
EOF
```

**Step 2: Verify file syntax**

```bash
python -c "from ruamel.yaml import YAML; YAML(typ='safe').load(open('mock_data.yaml'))"
echo "YAML syntax valid"
```

Expected: No errors, prints "YAML syntax valid"

**Step 3: Commit**

```bash
git add mock_data.yaml
git commit -m "feat: add sample mock_data.yaml file"
```

---

## Task 10: Run full test suite and verify

**Step 1: Run all unit tests**

```bash
uv run pytest tests/test_mock_source.py -v
```

Expected: All PASS

**Step 2: Run all integration tests**

```bash
uv run pytest tests/fa/test_routes_mock.py -v
```

Expected: All PASS

**Step 3: Run entire test suite to ensure no regressions**

```bash
uv run pytest -v
```

Expected: All PASS

**Step 4: Manual verification**

```bash
# Set MOCK_DATA in .env (already there)
# Start WebUI
uv run fpcr webui
```

Then in browser:

1. Open http://localhost:8000
2. Login with any credentials
3. Select domain "AME_CORP" or "AME_DC"
4. Verify packages appear
5. Select a package
6. Verify sections display with correct rule counts and ranges

**Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete mock data source feature with full test coverage"
```

---

## Verification Checklist

- [ ] Unit tests pass for MockDataSource
- [ ] Integration tests pass for route handlers
- [ ] WebUI works with mock data file
- [ ] Both JSON and YAML formats supported
- [ ] UIDs auto-generated where missing
- [ ] Sequential rulebase ranges calculated correctly
- [ ] Firewall/subnet data stored for future use
- [ ] Graceful error handling for file issues
- [ ] No regressions in existing functionality
