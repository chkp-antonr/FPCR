# FPCR Create & Verify Flow Design

**Date:** 2026-04-12

**Status:** Design Approved

**Related:** RITM Implementation, CPCRUD Enhancement

---

## 1. Overview

This design implements the "Create & Verify" flow for Firewall Policy Change Requests (FPCR). The flow enables firewall engineers to:

1. Input source IPs, destination IPs, and services
2. Automatically match or create Check Point objects
3. Define rules with domain/package/section selection
4. Create rules with automatic verification
5. Rollback rules in failed packages
6. Generate evidence cards (HTML, PDF, YAML export)
7. Submit for peer review and approval

**Key Principle:** Frontend-orchestrated workflow with backend services handling all business logic.

---

## 2. Architecture

### 2.1 Modular Service Layer

```text
src/fa/
├── services/
│   ├── initials_loader.py      # Engineer initials from CSV
│   ├── object_matcher.py       # Object matching + creation
│   ├── policy_verifier.py      # Policy verification
│   ├── rule_creator.py         # Rule creation with rollback
│   └── evidence_generator.py   # HTML/PDF/YAML generation
├── routes/
│   └── ritm_flow.py            # Flow API endpoints
└── templates/
    └── evidence_card.html      # Smart Console-style template
```

### 2.2 Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, SQLAlchemy |
| CPAIOPS | All Check Point API calls |
| Object Search | cpsearch (existing) |
| Template Engine | Jinja2 |
| PDF Generation | WeasyPrint |
| YAML Validation | jsonschema |
| Database | SQLite (async) |

---

## 3. Database Schema

### 3.1 New Tables

```sql
-- Track objects created during RITM workflow
CREATE TABLE ritm_created_objects (
    id INTEGER PRIMARY KEY,
    ritm_number TEXT NOT NULL,
    object_uid TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_name TEXT NOT NULL,
    domain_uid TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ritm_number) REFERENCES ritm(ritm_number)
);

-- Track rules created during RITM workflow
CREATE TABLE ritm_created_rules (
    id INTEGER PRIMARY KEY,
    ritm_number TEXT NOT NULL,
    rule_uid TEXT NOT NULL,
    rule_number INTEGER,
    package_uid TEXT NOT NULL,
    domain_uid TEXT NOT NULL,
    verification_status TEXT DEFAULT 'pending',
    disabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ritm_number) REFERENCES ritm(ritm_number)
);

-- Store verification results per package
CREATE TABLE ritm_verification (
    id INTEGER PRIMARY KEY,
    ritm_number TEXT NOT NULL,
    package_uid TEXT NOT NULL,
    domain_uid TEXT NOT NULL,
    verified BOOLEAN NOT NULL,
    errors TEXT,
    changes_snapshot TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ritm_number) REFERENCES ritm(ritm_number)
);
```

### 3.2 Table Updates

```sql
-- Add to existing ritm table
ALTER TABLE ritm ADD COLUMN engineer_initials TEXT;
ALTER TABLE ritm ADD COLUMN evidence_html TEXT;
ALTER TABLE ritm ADD COLUMN evidence_yaml TEXT;
ALTER TABLE ritm ADD COLUMN evidence_changes TEXT;
```

---

## 4. API Endpoints

### 4.1 New Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/ritm/{id}/match-objects` | Match/create objects |
| POST | `/ritm/{id}/verify-policy` | Verify policy before rules |
| POST | `/ritm/{id}/create-rules` | Create rules with verification |
| POST | `/ritm/{id}/generate-evidence` | Generate evidence artifacts |
| GET | `/ritm/{id}/export-pdf` | Download PDF evidence |
| GET | `/ritm/{id}/export-errors` | Download error log |

### 4.2 Request/Response Models

```python
class MatchResult(BaseModel):
    input: str
    object_uid: str
    object_name: str
    object_type: str
    created: bool
    matches_convention: bool
    usage_count: int | None = None

class ErrorResponse(BaseModel):
    package_uid: str
    package_name: str
    domain_name: str
    verified: bool
    created_count: int
    kept_count: int
    deleted_count: int
    errors: list[str]

class CreationResult(BaseModel):
    ritm_number: str
    total_created: int
    total_kept: int
    total_deleted: int
    packages: list[ErrorResponse]
```

---

## 5. Service Layer

### 5.1 InitialsLoader

Loads engineer initials from CSV file (`_tmp/FWTeam_admins.csv`).

```python
class InitialsLoader:
    def get_initials(self, username: str) -> str:
        """Map A-account to Short Name (initials)."""
        # CSV format: Name,Email,A-account,Short Name
        # Returns: "AV", "JD", etc.
```

### 5.2 ObjectMatcher

Matches existing objects or creates new ones following naming conventions.

**Naming Conventions:**

- Hosts: `Host_10.0.0.1`, `global_Host_10.0.0.1`
- Networks: `Net_192.168.1.0_24`, `global_Net_192.168.1.0_24`
- Ranges: `IPR_name`, `global_IPR_name`
- Groups: `GRP_<Name>_Host`, `GRP_<Name>_IPRange`, `GRP_<Name>_Subnets`

**Scoring:**

1. Prefer objects matching naming convention
2. Then prefer by highest usage count

### 5.3 PolicyVerifier

Verifies policy via CPAIOPS `verify-policy` API call.

```python
class PolicyVerifier:
    async def verify_policy(
        self,
        domain_uid: str,
        package_uid: str,
        session_name: str | None = None
    ) -> VerificationResult:
        """Call verify-policy API via CPAIOPS."""
```

### 5.4 RuleCreator

Creates rules with automatic rollback on verification failure.

**Flow:**

1. Create rules for package
2. Verify policy
3. If verified: disable rules
4. If failed: delete created rules (rollback)
5. Store results in database

**Rollback Strategy:**

- Objects/Groups: Keep (don't rollback)
- Rules in failed packages: Delete
- Rules in verified packages: Keep (disabled)

### 5.5 EvidenceGenerator

Generates three types of evidence:

1. **HTML Evidence Card**: Smart Console-style view with:
   - Domain headers (blue background)
   - Package headers (light blue)
   - Section headers (yellow background)
   - Rule tables with columns: No., Name, Source, Destination, VPN, Services, Action, Track

2. **YAML Export**: CPCRUD-compatible format validated against `ops/checkpoint_ops_schema.json`

3. **PDF Export**: Combines HTML + YAML + raw API changes response

---

## 6. Frontend Workflow

### 6.1 Engineer 1: Create/Edit RITM

```
1. Create RITM → POST /ritm
2. Enter source/dest/services → POST /ritm/{id}/pools
3. Match/create objects → POST /ritm/{id}/match-objects
4. Define rules → POST /ritm/{id}/policy (auto-save)
5. Create & Verify → POST /ritm/{id}/create-rules
6. Generate evidence → POST /ritm/{id}/generate-evidence
7. Export PDF → GET /ritm/{id}/export-pdf
8. Submit for approval → PUT /ritm/{id} (status=READY_FOR_APPROVAL)
```

### 6.2 Engineer 2: Peer Review

```
1. List pending → GET /ritm?status=1
2. Lock for review → POST /ritm/{id}/lock
3. View evidence → GET /ritm/{id} (includes HTML)
4. Approve → PUT /ritm/{id} (status=APPROVED, enable rules, publish)
5. Reject → PUT /ritm/{id} (status=WORK_IN_PROGRESS, add feedback)
```

---

## 7. Error Handling

### 7.1 Error Response Format

Errors are returned as a structured list with:

- Package/domain context
- Specific error messages
- Counts (created/kept/deleted)

### 7.2 Error Export

```
RITM: RITM1234567
Date: 2026-04-12 14:30:00
Engineer: a-avermahmooddttl (AV)

=== Package: Standard_Policy ===
Domain: Global
Verified: FAILED
Errors:
  - Rule 'RITM1234567' conflicts with existing rule at position 42
  - Service 'tcp-8080-custom' not found in domain
```

### 7.3 Session Naming

Every published session includes errors in section description:

```
Session: "RITM1234567 a-avermahmooddttl Created (2 errors)"
```

---

## 8. Configuration

### 8.1 Environment Variables

```bash
# Initials lookup
INITIALS_CSV_PATH=_tmp/FWTeam_admins.csv

# Evidence generation
EVIDENCE_TEMPLATE_DIR=src/fa/templates
PDF_RENDER_TIMEOUT=30

# Object matching
OBJECT_CREATE_MISSING=true
OBJECT_PREFER_CONVENTION=true

# Rule creation
RULE_DISABLE_AFTER_CREATE=true
RULE_VERIFY_AFTER_CREATE=true
```

### 8.2 Dependencies

```toml
weasyprint = ">=60"
jinja2 = ">=3.1.0"
jsonschema = ">=4.0.0"
```

---

## 9. Integration Points

### 9.1 CPAIOPS

All Check Point API calls go through CPAIOPS:

- `api_call()` for commands (add-host, add-access-rule, etc.)
- `api_query()` for queries (show-changes, show-objects, etc.)
- `verify-policy` for policy verification

### 9.2 cpsearch

Existing `cpsearch.py` is reused for:

- `classify_input()` - Determine object type from input
- `find_cp_objects()` - Search for existing objects
- Group membership traversal

### 9.3 Cache Service

Existing `cache_service.py` provides:

- Domain list for dropdowns
- Package list per domain
- Section list per package

### 9.4 CPCRUD

YAML export must be compatible with CPCRUD schema:

- Validate against `ops/checkpoint_ops_schema.json`
- Structure: `management_servers > domains > operations`
- Operation types: add, update, delete, show

---

## 10. Security & Validation

### 10.1 Input Validation

- RITM number format: `RITM\d+`
- IP addresses validated via `classify_input()`
- Domain/package/section UIDs verified against cache

### 10.2 Authorization

- Only creator can submit for approval
- Cannot approve own RITM
- Approval lock with timeout (30 minutes default)

---

## 11. Testing Strategy

### 11.1 Unit Tests

- `test_initials_loader.py` - CSV parsing, initials mapping
- `test_object_matcher.py` - Scoring, name generation, creation
- `test_policy_verifier.py` - Mock CPAIOPS responses
- `test_rule_creator.py` - Rollback logic, error handling
- `test_evidence_generator.py` - Template rendering, PDF generation

### 11.2 Integration Tests

- Full Create & Verify flow with mock CPAIOPS
- Rollback scenarios
- Error export formatting

---

## 12. Future Enhancements

- Expiration datetime support for temporary rules
- Batch object creation validation
- Evidence card customization (user preferences)
- CMDB integration (object/rule tracking)
- Audit log exports

---

## Appendix: Rule Comment Format

```
RITM<NUMBER> #YYYY-MM-DD-WW#

Example:
RITM1234567 #2026-04-12-AV#
```

Where WW = engineer initials from CSV lookup.
