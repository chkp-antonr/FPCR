# FPCR Create & Verify - Technical Overview

**Date:** 2026-04-12

**Audience:** Developers, System Architects

**Related:** [260412-fpcr-flow-design.md](./260412-fpcr-flow-design.md), [260412-fpcr-flow-diagrams.md](./260412-fpcr-flow-diagrams.md)

---

## Executive Summary

The FPCR Create & Verify flow is a **frontend-orchestrated, backend-heavy** system that streamlines firewall policy change requests. It automates object matching, rule creation, verification, and evidence generation while maintaining full auditability and rollback capabilities.

**Key Technical Decisions:**

- Modular service layer for testability and reusability
- CPAIOPS for all Check Point API interactions
- Existing cpsearch for object discovery
- CPCRUD-compatible YAML exports
- Smart Console-style HTML evidence cards

---

## 1. System Architecture

### 1.1 Frontend-Backend Contract

The frontend drives the workflow but relies on backend services for all business logic:

```
Frontend                                  Backend
────────                                  ────────
1. User enters IPs/services    ────────>  Match/create objects
2. User selects objects        <────────  Return matches with metadata
3. User defines rules          ────────>  Validate and save (auto-save)
4. User clicks "Create"        ────────>  Create, verify, rollback
5. Display results             <────────  Return creation result
6. User clicks "Evidence"      ────────>  Generate HTML/PDF/YAML
7. Display evidence            <────────  Return artifacts
8. User clicks "Export"        ────────>  Generate downloadable files
```

### 1.2 Service Layer Design

Each service has a single responsibility:

| Service | Responsibility | Input | Output |
|---------|---------------|-------|--------|
| InitialsLoader | Map username to initials | A-account | Short Name (e.g., "AV") |
| ObjectMatcher | Find or create objects | IPs, services, domain | MatchResult[] |
| PolicyVerifier | Verify policy integrity | Domain, package | VerificationResult |
| RuleCreator | Create rules with rollback | PolicyItem[] | CreationResult |
| EvidenceGenerator | Generate artifacts | Changes, results | HTML, YAML, PDF |

---

## 2. Object Matching System

### 2.1 How It Works

When an engineer enters an IP address (e.g., `10.0.0.1`):

1. **Classification**: Determine object type (host, network, range, FQDN)
   - Uses `cpsearch.classify_input()`
   - Returns: `host`, `network`, `address-range`, etc.

2. **Search**: Query existing objects in the domain
   - Uses `cpsearch.find_cp_objects()`
   - Searches by name, IP, or partial match

3. **Scoring**: Rank results by preference
   - **Naming convention match**: +100 points
   - **Usage count**: +N points (from Check Point)
   - Best score wins

4. **Creation**: If no match found (and auto-create enabled)
   - Generate name following convention
   - Create via CPAIOPS
   - Return with `created=True` flag

### 2.2 Naming Convention Logic

```
Input: 10.0.0.1
Type: host
Domain: Global (system domain)
Output: global_Host_10.0.0.1

Input: 192.168.1.0/24
Type: network
Domain: customer_domain
Output: Net_192.168.1.0_24

Input: 10.1.1.1-10.1.1.100
Type: address-range
Domain: customer_domain
Output: IPR_10_1_1_1_to_10_1_1_100
```

### 2.3 Scoring Example

For IP `10.0.0.1` in Global domain:

| Object Name | Convention Match | Usage Count | Total Score |
|-------------|------------------|-------------|-------------|
| global_Host_10.0.0.1 | ✅ (+100) | 45 | **145** |
| web-server-01 | ❌ (0) | 120 | 120 |
| Host_10.0.0.1 | ✅ (+100) | 5 | 105 |
| random-host-name | ❌ (0) | 2 | 2 |

**Winner:** `global_Host_10.0.0.1`

---

## 3. Rule Creation & Verification

### 3.1 Transaction Flow

Rules are created **per package** with independent verification:

```
Package A: Standard_Policy
├── Create 3 rules → UIDs: [uid1, uid2, uid3]
├── Verify policy → SUCCESS
├── Disable rules → [uid1, uid2, uid3] disabled
└── Status: VERIFIED (rules kept)

Package B: DMZ_Policy
├── Create 2 rules → UIDs: [uid4, uid5]
├── Verify policy → FAILED (error: service not found)
├── Rollback → Delete [uid4, uid5]
└── Status: FAILED (rules deleted)
```

### 3.2 Rollback Strategy

| Asset Type | On Success | On Failure |
|------------|------------|------------|
| Hosts | Keep | Keep |
| Networks | Keep | Keep |
| Address Ranges | Keep | Keep |
| Groups | Keep | Keep |
| Rules (verified package) | Keep (disabled) | N/A |
| Rules (failed package) | N/A | Delete |

**Rationale:** Objects are reusable and don't cause policy errors. Rules in failed packages could cause installation failures.

### 3.3 Verification API

Uses CPAIOPS `api_call()` with `verify-policy` command:

```python
result = await client.api_call(
    mgmt_name,
    "verify-policy",
    domain=domain_name,
    payload={"policy-package": package_name}
)

# Response structure
{
    "success": True/False,
    "errors": ["error message 1", "error message 2"],
    "warnings": [...]
}
```

---

## 4. Evidence Generation

### 4.1 Three-Part Evidence System

#### Part 1: HTML Evidence Card

Renders a Smart Console-like view:

```
┌─────────────────────────────────────────────────────┐
│ Global Domain                                       │ ← Blue header
├─────────────────────────────────────────────────────┤
│ Package: Standard_Policy           ✓ Verified       │ ← Light blue
├─────────────────────────────────────────────────────┤
│ Section: Network_Access                          │ ← Yellow
├─────────────────────────────────────────────────────┤
│ No.  │ Name        │ Source   │ Dest  │ Action... │
├──────┼─────────────┼──────────┼───────┼───────────┤
│ 42   │ RITM1234567 │ Host_10  │ Net_20│ Accept    │
│ 43   │ RITM1234567 │ Host_30  │ Any   │ Accept    │
└─────────────────────────────────────────────────────┘
```

#### Part 2: YAML Export

CPCRUD-compatible format:

```yaml
management_servers:
  - mgmt_name: "mgmt-server"
    domains:
      - name: "Global"
        operations:
          - operation: "add"
            type: "host"
            data:
              name: "global_Host_10.0.0.1"
              ip-address: "10.0.0.1"
          - operation: "add"
            type: "access-rule"
            layer: "Network"
            position: {"top": "Network_Access"}
            data:
              name: "RITM1234567"
              source: ["global_Host_10.0.0.1"]
              destination: ["Net_192.168.1.0_24"]
              action: "Accept"
```

#### Part 3: Raw API Changes

Direct JSON from `show-changes` API:

```json
{
  "changes": [
    {
      "uid": "12345678-1234-1234-1234-123456789abc",
      "type": "add",
      "object-type": "host",
      "name": "global_Host_10.0.0.1"
    }
  ]
}
```

### 4.2 PDF Generation

Uses WeasyPrint to combine all three parts:

1. Render HTML template with Jinja2
2. Append YAML as formatted text block
3. Append API changes as JSON block
4. Generate PDF with headers/footers

---

## 5. Database Design

### 5.1 Tracking Tables

Three new tables track the workflow:

```sql
ritm_created_objects   -- What objects were created
ritm_created_rules     -- What rules were created + verification status
ritm_verification      -- Package-level verification results
```

### 5.2 Audit Trail

Every RITM has complete history:

```sql
SELECT * FROM ritm WHERE ritm_number = 'RITM1234567';
-- Shows: created_at, engineer_initials, status

SELECT * FROM ritm_created_objects WHERE ritm_number = 'RITM1234567';
-- Shows: All objects created for this RITM

SELECT * FROM ritm_created_rules WHERE ritm_number = 'RITM1234567';
-- Shows: All rules created, their verification status

SELECT * FROM ritm_verification WHERE ritm_number = 'RITM1234567';
-- Shows: Per-package verification results + errors
```

### 5.3 Evidence Storage

Evidence artifacts are stored in the RITM table:

```sql
SELECT
    evidence_html,    -- For display in browser
    evidence_yaml,    -- For YAML export
    evidence_changes  -- Raw API response
FROM ritm
WHERE ritm_number = 'RITM1234567';
```

---

## 6. Error Handling

### 6.1 Error Response Format

All errors are structured:

```json
{
  "ritm_number": "RITM1234567",
  "total_created": 5,
  "total_kept": 3,
  "total_deleted": 2,
  "packages": [
    {
      "package_uid": "...",
      "package_name": "Standard_Policy",
      "domain_name": "Global",
      "verified": true,
      "created_count": 3,
      "kept_count": 3,
      "deleted_count": 0,
      "errors": []
    },
    {
      "package_uid": "...",
      "package_name": "DMZ_Policy",
      "domain_name": "DMZ",
      "verified": false,
      "created_count": 2,
      "kept_count": 0,
      "deleted_count": 2,
      "errors": [
        "Service 'tcp-8080-custom' not found in domain",
        "Rule conflicts with existing rule at position 42"
      ]
    }
  ]
}
```

### 6.2 Error Export

Text file format for easy review:

```
RITM: RITM1234567
Date: 2026-04-12 14:30:00
Engineer: a-avermahmooddttl (AV)

=== Package: DMZ_Policy ===
Domain: DMZ
Verified: FAILED
Created: 2 rules
Deleted: 2 rules (rolled back)

Errors:
  - Service 'tcp-8080-custom' not found in domain
  - Rule conflicts with existing rule at position 42
```

---

## 7. Integration Points

### 7.1 CPAIOPS Usage

All Check Point API calls go through CPAIOPS:

```python
# Direct API call for commands
result = await client.api_call(
    mgmt_name,
    "add-host",
    domain=domain_name,
    payload={...}
)

# API query for data retrieval
result = await client.api_query(
    mgmt_name,
    "show-changes",
    domain=domain_name,
    payload={"from-session": session_name}
)
```

### 7.2 cpsearch Integration

Reuses existing functionality:

```python
from cpsearch import classify_input, find_cp_objects

# Determine object type
obj_type = classify_input("10.0.0.1")  # Returns "host"

# Find existing objects
found = await find_cp_objects(
    client=cpaiops_client,
    domain_uid="...",
    search="10.0.0.1",
    obj_type="host"
)
```

### 7.3 Cache Service Integration

Uses cached data for dropdowns:

```python
from fa.cache_service import cache_service

# Get all domains
domains = await cache_service.get_cached_domains()

# Get packages for domain
packages = await cache_service.get_cached_packages(domain_uid)

# Get sections for package
sections = await cache_service.get_cached_sections(domain_uid, package_uid)
```

---

## 8. Security Considerations

### 8.1 Input Validation

- RITM numbers: Must match `^RITM\d+$`
- IP addresses: Validated via `classify_input()`
- Domain/package/section: Verified against cache
- YAML exports: Validated against `checkpoint_ops_schema.json`

### 8.2 Authorization

- Only creator can submit for approval
- Cannot approve own RITM
- Approval lock expires after 30 minutes
- Session-based authentication

### 8.3 Audit Trail

All actions are logged:

- Who created the RITM
- Who approved/rejected
- What objects/rules were created
- Verification results and errors
- Session names for all publish operations

---

## 9. Performance Considerations

### 9.1 Async Operations

All database and API operations are async:

```python
async def create_rules_with_rollback(...):
    # Non-blocking database operations
    async with AsyncSession(engine) as session:
        ...

    # Non-blocking API calls
    await client.api_call(...)
```

### 9.2 Caching Strategy

- Domain/package/section data cached in SQLite
- Initials CSV loaded once at startup
- Evidence artifacts stored in database (regenerate on demand)

### 9.3 Batch Processing

- Rules created in batches per package
- Verification runs per package (parallelizable in future)
- Evidence generation combines all results at once

---

## 10. Future Enhancements

### 10.1 Planned Features

- **Expiration datetime**: Support for temporary rules
- **Batch validation**: Pre-validate all objects before creation
- **CMDB integration**: Push created objects/rules to CMDB
- **Audit export**: JSON/CSV export of full RITM history

### 10.2 Technical Debt

- **Frontend state management**: Currently manual, could use React Query
- **Background tasks**: Evidence generation could be async
- **Error recovery**: Failed RITMs require manual cleanup

---

## 11. Glossary

| Term | Definition |
|------|------------|
| RITM | Request Item (ServiceNow ticket number) |
| CPCRUD | Check Point CRUD operations (YAML-based) |
| CPAIOPS | Check Point API Operations library |
| Smart Console | Check Point's GUI management interface |
| Evidence Card | HTML representation of created rules |
| Verification | Policy integrity check before/after rule creation |
| Rollback | Deleting rules that failed verification |

---

## 12. References

- [Design Document](./260412-fpcr-flow-design.md)
- [Flow Diagrams](./260412-fpcr-flow-diagrams.md)
- [CPCRUD Schema](../../ops/checkpoint_ops_schema.json)
- [cpsearch Module](../../src/cpsearch.py)
