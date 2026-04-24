# Mock Data Source Feature Design

**Date:** 2026-03-05

**Author:** AI Assistant

**Status:** Approved

---

## Overview

Add a mock data source feature to FPCR that allows the WebUI to operate without a live Check Point API connection. When `MOCK_DATA` environment variable is set, the application reads domains, policy packages, and access sections from a local file instead of querying the Check Point management server.

---

## Architecture

### Current State

The WebUI (`src/fa/`) uses `CPAIOPSClient` to connect to Check Point API:

```
Route Handler → CPAIOPSClient → Check Point API
```

### Proposed State

Add a `MockDataSource` class that can substitute the API client:

```
Route Handler → Check MOCK_DATA env
                │
                ├─ Set → MockDataSource → Read file
                └─ Not set → CPAIOPSClient → Check Point API
```

---

## Components

### 1. Mock Data File Format

Support both JSON and YAML, auto-detected by file extension.

**Example (`mock_data.yaml`):**

```yaml
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
```

### 2. MockDataSource Class

**Location:** `src/fa/mock_source.py`

```python
class MockDataSource:
    """Mock data source for WebUI testing without Check Point API."""

    def __init__(self, file_path: str):
        """Load and parse mock data file (JSON or YAML)."""
        self.data = self._load_file(file_path)
        self._ensure_uids()

    def get_domains(self) -> list[DomainItem]:
        """Return all domains with auto-generated UIDs."""

    def get_packages(self, domain_uid: str) -> list[PackageItem]:
        """Return packages for a domain."""

    def get_sections(
        self, domain_uid: str, package_uid: str
    ) -> tuple[list[SectionItem], int]:
        """Return sections with sequential rulebase ranges and total rule count."""
```

### 3. Route Modifications

**Files to modify:**

- `src/fa/routes/domains.py`
- `src/fa/routes/packages.py`

**Pattern for both files:**

```python
@router.get("/domains")
async def list_domains(session: SessionData = Depends(get_session_data)):
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        return DomainsResponse(domains=mock.get_domains())

    # Existing API code continues...
```

---

## Key Design Decisions

### UID Auto-Generation

- **Problem:** Check Point API provides UUIDs for all entities. Mock file may not.
- **Solution:** Auto-generate UUIDs on first load using `uuid.uuid4()`
- **Behavior:** Generated UIDs stored in memory for consistency during session

### Rulebase Range Calculation

- **Problem:** Mock file specifies rule counts per section, not ranges
- **Solution:** Calculate cumulative ranges sequentially
- **Example:**
  - Input: `init: 3, ingress: 5`
  - Output: `init: [1, 3], ingress: [4, 8]`

### Firewall/Subnet Data

- **Decision:** Include in mock structure but DO NOT expose via WebUI API yet
- **Rationale:** Store for future CLI features, avoid scope creep

### File Format Support

- **Library:** Use `ruamel.yaml` (already a dependency via `cpcrud`)
- **Detection:** Check file extension (`.json`, `.yaml`, `.yml`)
- **Priority:** YAML preferred (as shown in user example)

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| File not found | Log warning, return empty results |
| Invalid YAML/JSON | Raise HTTP 500 with error details |
| Missing sections key | Return empty sections list |
| Missing domain UID | Return empty packages list |

---

## Testing Strategy

### Unit Tests (`tests/test_mock_source.py`)

1. Test YAML file loading
2. Test JSON file loading
3. Test UID auto-generation
4. Test sequential rulebase range calculation
5. Test missing file handling
6. Test invalid format handling

### Integration Test (`tests/test_mock_integration.py`)

1. Set `MOCK_DATA` environment variable
2. Start WebUI
3. Call `/api/v1/domains`
4. Call `/api/v1/domains/{uid}/packages`
5. Call `/api/v1/domains/{uid}/packages/{uid}/sections`
6. Verify response structures match live API

### Manual Verification

1. Create `mock_data.yaml`
2. Set `MOCK_DATA=mock_data.yaml` in `.env`
3. Start WebUI: `uv run fpcr webui`
4. Login → Select domain → Select package
5. Verify sections display correctly

---

## Files to Create

- `src/fa/mock_source.py` - MockDataSource implementation
- `tests/test_mock_source.py` - Unit tests
- `tests/test_mock_integration.py` - Integration tests
- `mock_data.yaml` - Sample mock data file

## Files to Modify

- `src/fa/routes/domains.py` - Add mock detection
- `src/fa/routes/packages.py` - Add mock detection

---

## Configuration

**`.env` (already added):**

```bash
MOCK_DATA=mock_data.json  # or mock_data.yaml
```

---

## Success Criteria

- [ ] WebUI operates without Check Point API connection when `MOCK_DATA` is set
- [ ] Domain selection works
- [ ] Package selection works after domain selection
- [ ] Section list displays with correct rulebase ranges
- [ ] Firewall/subnet data stored but not exposed via API
- [ ] Both JSON and YAML formats supported
- [ ] UIDs auto-generated where missing
- [ ] Graceful error handling for file issues
