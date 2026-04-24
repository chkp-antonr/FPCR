# CPCRUD Enhancement Design Spec

**Date:** 2026-04-11

**Status:** Approved

**Author:** Claude (via brainstorming session)

---

## Overview

Enhance the existing CPCRUD (Check Point CRUD) functionality by porting proven features from the reference implementation at `W:\MMP\src\plugins\actions\cpcrud\`. This enhancement adds support for NAT settings on network objects, firewall rule management (access, NAT, threat prevention, HTTPS), and sophisticated rule positioning.

---

## Motivation

The current CPCRUD implementation supports basic CRUD operations for network objects (hosts, networks, address ranges, groups) but lacks:

1. NAT settings configuration for network objects
2. Firewall rule management capabilities
3. Rule positioning and ordering
4. Advanced duplicate detection and handling

The reference implementation (`W:\MMP\`) has production-tested code for these features. Porting this functionality will significantly enhance FPCR's automation capabilities.

---

## Architecture

### Component Overview

```
src/cpcrud/
├── __init__.py          # Public API exports
├── object_manager.py    # CheckPointObjectManager - network objects CRUD
├── rule_manager.py      # CheckPointRuleManager - firewall rules CRUD
├── position_helper.py   # PositionHelper - rule positioning validation
├── business_logic.py    # Template processing orchestration
└── config.py           # Configuration constants

ops/
└── checkpoint_ops_schema.json  # Updated JSON schema with new types
```

### Design Principles

- **Separation of Concerns:** ObjectManager for network objects, RuleManager for firewall rules
- **Proven Architecture:** Closely follow reference implementation from W:\MMP\
- **No Backward Compatibility Breaking:** Existing templates continue to work
- **Structured Results:** All operations return `{success, errors, warnings}` format
- **Fail-Safe Validation:** JSON schema validation before API calls

---

## Module Specifications

### 1. CheckPointObjectManager (`object_manager.py`)

Enhanced version of existing object manager.

#### Responsibilities

- CRUD operations for: `host`, `network`, `address-range`, `network-group`
- NAT settings transformation and validation
- Duplicate detection and resolution
- Cache integration (read-only object lookups)

#### Key Methods

```python
class CheckPointObjectManager:
    async def add(object_type, data, mgmt_name, domain, duplicates=None)
    async def update(object_type, key, data, mgmt_name, domain)
    async def delete(object_type, key, mgmt_name, domain)
    async def show(object_type, key, mgmt_name, domain)

    def _transform_nat_settings(object_type, nat_settings) -> dict | None
    def _validate_object_data(object_type, object_data) -> None
```

#### NAT Settings Transformation

The `_transform_nat_settings()` method handles:

1. **Field Mapping:**
   - `gateway` → `install-on` for hide NAT
   - `ip-address` ↔ `ipv4-address` based on object type

2. **Auto-Rule Handling:**
   - Adds `auto-rule: true` when method specified but auto-rule missing

3. **Method Support:**
   - `static`: 1:1 IP translation (requires `ipv4-address` or `ipv6-address`)
   - `hide`: Hide behind gateway or IP (requires `gateway` or `ip-address`)

#### Exception Classes

```python
CheckPointObjectManagerError (base)
├── CheckPointAPIError          # API communication failures
├── ObjectNotFoundError         # Object not found
├── DuplicateObjectError        # Duplicate detection
├── InvalidIdentifierError      # Non-unique identifiers
└── ValidationError             # Validation failures
```

---

### 2. CheckPointRuleManager (`rule_manager.py`)

New class for firewall rule management.

#### Supported Rule Types

| Rule Type | Operations | Required Parameters |
|-----------|-----------|---------------------|
| `access-rule` | add, update, delete, show | `layer` |
| `nat-rule` | add, update, delete, show | `package` |
| `threat-prevention-rule` | add | `layer` |
| `https-rule` | add | `layer` |

#### Key Methods

```python
class CheckPointRuleManager:
    async def add(rule_type, data, mgmt_name, domain, layer=None, package=None, position=None, match_threshold=0)
    async def update(rule_type, key, data, mgmt_name, domain, layer=None, package=None)
    async def delete(rule_type, key, mgmt_name, domain, layer=None, package=None)
    async def show(rule_type, key, mgmt_name, domain, layer=None, package=None)

    async def _find_existing_rule(rule_type, name, mgmt_name, domain, layer, package)
    def _calculate_rule_differences(existing_rule, new_data) -> int
```

#### Match-Threshold Duplicate Handling

- `match-threshold` parameter in add operations
- Calculates difference score between existing and new rule
- Score == 0: Skips API call (identical rule exists)
- Score <= threshold: Updates existing rule instead of adding

---

### 3. PositionHelper (`position_helper.py`)

Validates and transforms rule position values.

#### Supported Position Formats

```yaml
# Absolute position (1-based)
position: 1

# Layer-level
position: "top"
position: "bottom"

# Section-relative
position:
  top: "Section Name"
position:
  bottom: "Section Name"
position:
  above: "Rule Name"
position:
  below: "Rule Name"
```

#### Validation Rules

- Integer: Must be >= 1
- String: Must be "top" or "bottom"
- Object: Exactly one key (top/bottom/above/below) with non-empty string value

---

### 4. Business Logic (`business_logic.py`)

Orchestrates template processing and validation.

#### Key Functions

```python
def validate_template(template: dict, file_path: str) -> list[str]
async def apply_crud_templates(client: CPAIOPSClient, template_files: list[str], no_publish: bool = False)
```

#### Processing Flow

```
1. Load YAML template
2. Validate against JSON schema
3. For each management server:
   a. For each domain:
      - Pre-process: ensure groups exist
      - Process object operations (host, network, etc.)
      - Process rule operations (access-rule, nat-rule, etc.)
      - Publish changes (unless no_publish)
```

---

### 5. Schema Updates (`checkpoint_ops_schema.json`)

#### New Definitions

- `nat_settings`: NAT configuration for objects
- `access_rule_*`: Access rule definitions (add, update, delete, show)
- `nat_rule_*`: NAT rule definitions
- `threat_rule_add`: Threat prevention rule definition
- `https_rule_add`: HTTPS rule definition
- `rule_position`: Rule positioning specification
- `track_settings`: Rule tracking/audit settings

#### Updated Object Definitions

All object types (host, network, address-range) now support:

- `nat-settings` property
- `uid` in common_data
- `new-name` in update operations

---

## Data Flow

### Template Processing

```
YAML Template
    ↓
JSON Schema Validation
    ↓
Operation Format Validation
    ↓
┌─────────────────────────────────────┐
│  For each operation:                │
│  ├─ Detect operation type           │
│  ├─ Route to appropriate manager    │
│  ├─ Validate data                   │
│  ├─ Transform (NAT, position)       │
│  ├─ Execute API call                │
│  └─ Collect results                 │
└─────────────────────────────────────┘
    ↓
Aggregate Results (success/errors/warnings)
    ↓
Publish (if not no_publish)
```

### NAT Settings Transformation

```
Template Input:
  nat-settings:
    method: static
    ip-address: 10.0.0.1

Transform:
  1. Map ip-address → ipv4-address (for host)
  2. Add auto-rule: true

API Payload:
  nat-settings:
    method: static
    ipv4-address: 10.0.0.1
    auto-rule: true
```

---

## Error Handling

### Result Structure

All operations return:

```python
{
    "success": [  # Successful operations
        {"operation": "add", "object_type": "host", "name": "host1", "uid": "..."}
    ],
    "errors": [   # Failed operations
        {"operation": "add", "object_type": "host", "error": "...", "error_type": "..."}
    ],
    "warnings": [ # Intentional skips
        {"operation": "add", "object_type": "host", "warning": "...", "warning_type": "..."}
    ]
}
```

### Error Categories

1. **Validation Errors:** Schema or format validation failures
2. **API Errors:** Check Point API communication failures
3. **Duplicate Warnings:** Objects/rules already exist (when configured to skip)
4. **Position Errors:** Invalid rule position specifications

---

## Dependencies

### Required (Already in Project)

- `cpaiops` - Check Point API client
- `ruamel.yaml` - YAML parsing
- `jsonschema` - Schema validation

### Optional (Consider)

- `dataclasses` - For structured data (Python 3.7+ standard library)
- Existing cache infrastructure in FPCR

---

## Backward Compatibility

### Maintained

- Existing object templates work without modification
- CLI interface unchanged: `apply_crud_templates(client, template_files, no_publish)`
- Domain handling: empty string → "SMC User"

### New Features (Opt-In)

- Rule operations only processed if present in templates
- NAT settings optional for objects
- Position only required for rule add operations

---

## Testing Considerations

### Unit Tests

1. **PositionHelper:**
   - Valid position formats (int, string, object)
   - Invalid position formats (negative int, invalid strings, malformed objects)

2. **ObjectManager:**
   - NAT settings transformation for each object type
   - Field name mapping (ip-address ↔ ipv4-address)
   - Auto-rule addition

3. **RuleManager:**
   - Match-threshold calculation
   - Duplicate detection logic

### Integration Tests

1. End-to-end template processing
2. API interaction with mock Check Point
3. Error handling and recovery

---

## Implementation Phases

### Phase 1: Foundation

- Create new file structure
- Port PositionHelper
- Update checkpoint_ops_schema.json

### Phase 2: Object Manager

- Enhance CheckPointObjectManager
- Add NAT settings support
- Add exception classes
- Update result formatting

### Phase 3: Rule Manager

- Create CheckPointRuleManager
- Implement rule CRUD operations
- Add positioning support
- Add match-threshold logic

### Phase 4: Integration

- Update business_logic.py
- Wire up managers in template processing
- Update CLI integration
- Add documentation

---

## Open Questions

None at this time.

---

## References

- Reference implementation: `W:\MMP\src\plugins\actions\cpcrud\`
- Reference schema: `W:\MMP\ops\checkpoint_ops_schema.json`
- Current implementation: `src/cpcrud/cpcrud.py`
- Current schema: `ops/checkpoint_ops_schema.json`
