# Package Selection Flow Design

**Date:** 2026-02-20

**Status:** Approved

**Phase:** 1 - UI Flow and Data Structure

## Overview

Extend the existing Domains page with a cascading selection flow for domains, policy packages, and sections. Users select where to insert rules by choosing a section and a position (top/bottom/custom rule number).

## Page Layout

```
┌─────────────────────────────────────────────────────┐
│ Domains                                    [Logout] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Domain:    [Search domain... ▼]                    │
│                                                     │
│  Package:   [Search package... ▼]                   │
│                                                     │
│  Sections:  (click to select)                       │
│             ┌─────────────────────────────────┐     │
│             │ 1-11   Global section     [SEL] │     │
│             ├─────────────────────────────────┤     │
│             │ 12-15  DMZ section              │     │
│             └─────────────────────────────────┘     │
│                                                     │
│  Position:  ○ Top  ○ Bottom  ○ Custom: [___]        │
│             (enabled when section selected)         │
│                                                     │
│                                    [Submit]         │
└─────────────────────────────────────────────────────┘
```

## Component Structure

```
Domains.tsx (modified)
├── PageHeader
├── DomainSelector (AutoComplete with search)
├── PackageSelector (AutoComplete with search, disabled until domain)
├── SectionsPanel (hidden until package selected)
│   └── SectionCard (clickable, selectable)
│       └── SectionLabel "{min}-{max} {name}"
├── PositionPanel (disabled until section selected)
│   ├── RadioGroup [Top | Bottom | Custom]
│   └── CustomNumberInput (conditional, validated)
└── SubmitButton (disabled until complete)
```

## Data Types

### Frontend

```typescript
interface PackageItem {
  name: string;
  uid: string;
  access_layer: string;
}

interface SectionItem {
  name: string;
  uid: string;
  rulebase_range: [number, number];  // [min, max]
  rule_count: number;
}

interface PositionChoice {
  type: 'top' | 'bottom' | 'custom';
  custom_number?: number;
}
```

### Backend Response Models

```python
class PackageItem(BaseModel):
    name: str
    uid: str
    access_layer: str
    # Additional extended fields for future use

class SectionItem(BaseModel):
    name: str
    uid: str
    rulebase_range: tuple[int, int]  # (min, max)
    rule_count: int

class PackagesResponse(BaseModel):
    packages: list[PackageItem]

class SectionsResponse(BaseModel):
    sections: list[SectionItem]
    total_rules: int
```

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/domains/{domain_uid}/packages` | List policy packages for domain |
| GET | `/api/v1/domains/{domain_uid}/packages/{pkg_uid}/sections` | Get sections with rule ranges |

### Backend Implementation (cpaiops)

**Packages endpoint:**

```python
await client.api_query(mgmt_name, "show-packages", {"domain": domain_uid})
```

**Sections endpoint:**

```python
layer_data = await client.api_query(
    mgmt_name,
    "show-access-rulebase",
    {"name": access_layer_name, "details-level": "full"}
)

# Extract sections and calculate rule ranges
sections = []
current_rule = 1
for rule in layer_data["rulebase"]:
    if rule["type"] == "access-section":
        # Calculate range based on rules in section
        section_min = current_rule
        section_max = current_rule + len(rule.get("rules", [])) - 1
        sections.append({
            "name": rule["name"],
            "uid": rule["uid"],
            "rulebase_range": (section_min, section_max),
            "rule_count": len(rule.get("rules", []))
        })
        current_rule = section_max + 1
```

## State Management

```typescript
interface DomainsState {
  selectedDomain: DomainItem | null;
  selectedPackage: PackageItem | null;
  packages: PackageItem[];
  sections: SectionItem[];
  selectedSection: SectionItem | null;
  position: PositionChoice | null;
}
```

## Validation Rules

| Field | Rule |
|-------|------|
| Domain | Required, must be from dropdown |
| Package | Required, must be from dropdown |
| Section | Required, must be clicked/selected |
| Position | Required (Top/Bottom/Custom) |
| Custom number | Must be within `selectedSection.rulebase_range` |

## User Flow

1. User types in Domain search → filtered dropdown → selects domain
2. Package selector enables → user types/searches → selects package
3. Sections list renders → user clicks a section
4. Position selector enables → user selects Top/Bottom or Custom
5. If Custom: number input validates against selected section's range
6. Submit button enables → user clicks Submit

## Error Handling

| Scenario | Response |
|----------|----------|
| API failure | `message.error()` toast with error details |
| Invalid custom number | Inline "Must be between X and Y" error |
| Network error | Retry prompt |
| Empty session | Redirect to login |

## Files to Create/Modify

### Backend

- `src/fa/routes/packages.py` (new) - packages and sections endpoints
- `src/fa/routes/__init__.py` - add `packages_router`
- `src/fa/models.py` - add Pydantic models

### Frontend

- `webui/src/pages/Domains.tsx` - rewrite with new layout
- `webui/src/types/index.ts` - add PackageItem, SectionItem, PositionChoice
- `webui/src/api/endpoints.ts` - add packagesApi

## Future Considerations

- Phase 2: Implement Submit action endpoint
- Phase 2+: Add rule preview in sections
- Phase 2+: Add bulk section operations
