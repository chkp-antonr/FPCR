# Domains_2 Design Document

**Date:** 2026-03-06

**Status:** Approved

**Author:** AI-Assisted Design

## Overview

Create a new `/domains-2` page that provides an alternative UI for creating firewall rules. Unlike the existing card-based `/domains` interface, Domains_2 uses a row-based table approach with topology-aware predictions, drag-and-drop field filling, and multi-select IP support.

## Motivation

The existing `/domains` page works well for single-IP-per-rule scenarios. However, users need:

1. **Multi-select IPs**: Single rule covering multiple source/destination IPs
2. **Topology awareness**: Predict which domains/packages match based on gateway subnets
3. **Bulk operations**: Clone rules for multi-gateway traffic scenarios
4. **Visual feedback**: See which IPs are unused at a glance

Domains_2 provides these features while maintaining a clear separation from the existing `/domains` UX for A/B comparison.

## Architecture

### Page Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FPCR.                         username                    [Logout]         │
├──────────┬──────────────────────────────────────────────────────────────────┤
│          │  Domains_2                                                         │
│ Dashboard │  ┌──────────┬────────────┬──────────────┐                        │
│ Domains  │  │ Source   │ Destination│ Services     │                        │
│ Domains_2│  │ IPs      │ IPs        │ (optional)   │                        │
│          │  │ [tags]   │ [tags]     │ [text]       │                        │
│          │  │ [+ Add...]│[+ Add...] │ [+ Add...]   │                        │
│          │  └──────────┴────────────┴──────────────┘                        │
│          │                                                                    │
│          │  ┌─────────────────────────────────────────────────────────────┐ │
│          │  │  PREDICTIONS                                              [clear] │
│          │  │  10.76.64.11 → AME_CORP US-NY-CORP | AME_DC US-NY-DC  ⒟   │ │
│          │  └─────────────────────────────────────────────────────────────┘ │
│          │                                                                    │
│          │  [+ Add Rule]                                                      │
│          │  ┌─────────────────────────────────────────────────────────────┐ │
│          │  │Clone│Source│Dest│Domain│Package│Section│Pos│Act│Track│Serv│ │
│          │  │[📋] │[tags]│[tag│[▼]  │[▼]   │[▼]   │Top│Acc│Log  │https│ │
│          │  └─────┴──────┴────┴──────┴───────┴───────┴───┴───┴─────┴────┘ │
│          │                                          [Submit Rules]         │
│          └──────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Hierarchy

```
Domains2.tsx (new page)
├── IpInputPanel (new)
│   ├── SourceIpTagsInput (Select mode="tags")
│   ├── DestIpTagsInput (Select mode="tags")
│   └── ServicesInput (Select mode="tags")
├── PredictionsPanel (new)
│   └── PredictionItem (draggable)
├── AddRuleButton
├── RulesTable (new - Ant Design Table)
│   ├── Column: Clone (Button)
│   ├── Column: Source IPs (Select mode="multiple")
│   ├── Column: Dest IPs (Select mode="multiple")
│   ├── Column: Domain (Select, cascades)
│   ├── Column: Package (Select, cascades)
│   ├── Column: Section (Select)
│   ├── Column: Position (Radio + InputNumber)
│   ├── Column: Action (Select)
│   ├── Column: Track (Select)
│   └── Column: Services (Select mode="multiple")
└── SubmitButton
```

## Data Flow

```
User Paste (Source/Dest/Services)
    ↓
IpInputPanel (validate & normalize)
    ↓
sourcePool, destPool, servicesPool (state)
    ↓
PredictionsPanel (match IPs to topology)
    ↓
predictions (candidates list)
    ↓
Drag & Drop (smart fill empty fields)
    ↓
RulesTable (rule rows)
    ↓
Submit → /api/v1/domains2/rules/batch
```

## TypeScript Types

```typescript
export interface ServiceEntry {
  original: string;
  normalized: string;
  type: 'protocol' | 'port' | 'any' | 'named';
}

export interface Prediction {
  ip: IpEntry;
  candidates: PredictionCandidate[];
}

export interface PredictionCandidate {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnet: string;
}

export interface RuleRow {
  id: string;
  sourceIps: IpEntry[];
  destIps: IpEntry[];
  domain: DomainItem | null;
  package: PackageItem | null;
  section: SectionItem | null;
  position: PositionChoice;
  action: 'accept' | 'drop';
  track: 'log' | 'none';
  services: ServiceEntry[];
}
```

## API Endpoints

### GET /api/v1/domains/topology

Returns subnet topology for prediction engine.

**Response:**

```typescript
interface TopologyResponse {
  topology: Array<{
    domain: DomainItem;
    package: PackageItem;
    firewall: string;
    subnets: string[];
  }>;
}
```

### POST /api/v1/domains2/rules/batch

Creates multiple firewall rules.

**Request:**

```typescript
interface Domains2BatchRequest {
  rules: Array<{
    source_ips: string[];
    dest_ips: string[];
    services: string[];
    domain_uid: string;
    package_uid: string;
    section_uid: string | null;
    position: PositionChoice;
    action: 'accept' | 'drop';
    track: 'log' | 'none';
  }>;
}
```

## Key Features

### 1. Tag-Based Input

Source, Destination, and Services use Ant Design `Select` with `mode="tags"`.

- Paste any format → auto-normalized to space-separated
- Tags show `[x]` for removal
- Editable after paste
- Invalid entries show error state

### 2. Prediction Engine

Matches IPs to gateway subnets from mock_data.yaml topology.

```typescript
function generatePredictions(
  sourcePool: IpEntry[],
  destPool: IpEntry[],
  topology: TopologyEntry[]
): Prediction[]
```

**Display format:** `10.76.64.11 → AME_CORP US-NY-CORP | AME_DC US-NY-DC`

Combined display for multiple candidates.

### 3. Drag-and-Drop Smart Fill

Drag prediction item to table row → fill empty fields only.

```typescript
if (!rule.domain) rule.domain = candidate.domain;
if (!rule.package) rule.package = candidate.package;
if (rule.sourceIps.length === 0) rule.sourceIps.push(ip);
// Never overwrite existing values
```

### 4. Multi-Select IPs

Each rule row supports multiple source and destination IPs.

- `Select mode="multiple"` with tag styling
- Used IPs: blue background
- Unused IPs: gray background with dashed border

### 5. Clone Button

Copies entire rule row with all IPs.

- Domain, Package, Section must be selected manually
- Useful for multi-gateway traffic scenarios

### 6. Unused IP Highlighting

Tags styled differently based on usage.

```css
.usedTag { background: #1677ff; }   /* Used in at least one rule */
.unusedTag { background: #d9d9d9; } /* Not used */
```

### 7. Validation

Required fields: domain, package, at least one source IP, one dest IP.

Warning: unused IPs detected (modal confirmation).

Error: highlight problematic rows with red border.

## File Structure

```
webui/src/
├── pages/
│   └── Domains2.tsx             (new)
├── components/
│   ├── IpInputPanel.tsx         (new)
│   ├── PredictionsPanel.tsx     (new)
│   └── RulesTable.tsx           (new)
├── utils/
│   ├── serviceValidator.ts      (new)
│   ├── predictionEngine.ts      (new)
│   └── ruleValidator.ts         (new)
├── types/
│   └── index.ts                 (update)
├── api/
│   └── endpoints.ts             (update)
└── styles/
    ├── pages/
    │   └── domains2.module.css  (new)
    └── components/
        ├── ipInputPanel.module.css    (new)
        ├── predictionsPanel.module.css (new)
        └── rulesTable.module.css       (new)
```

## Implementation Phases

### Phase 1: Foundation (MVP)

Basic page with input and table, no predictions.

- Create route and menu item
- IP input panel with tags
- Rules table with basic columns
- Add/delete row functionality

### Phase 2: Prediction Engine

Add topology-aware predictions.

- Topology API endpoint
- Prediction matching logic
- Predictions panel display

### Phase 3: Drag-and-Drop

Enable drag from predictions to table rows.

- Draggable prediction items
- Table row drop zones
- Smart fill logic

### Phase 4: Clone & Unused IPs

Clone functionality and unused IP highlighting.

- Clone button and handler
- Unused IP tracking
- Tag styling based on usage

### Phase 5: Submit & Validation

Full submission flow with error handling.

- Rule validation
- Submit handler
- Batch API endpoint
- Error display

### Phase 6: Polish (Optional)

Production-ready refinements.

- Persistence (localStorage)
- Bulk operations
- Export functionality
- Keyboard shortcuts

## Styling

Consistent with Ant Design and existing `/domains` page.

- Primary: `#1677ff` (blue)
- Success: `#52c41a` (green)
- Warning: `#faad14` (orange)
- Error: `#ff4d4f` (red)
- Unused tags: `#d9d9d9` (gray with dashed border)

## Dependencies

No new npm packages required.

- `antd`: Select, Table, Tag components
- `ipaddr.js`: IP subnet matching (already exists)
- HTML5 Drag and Drop API: Native browser API

## Notes

- Separate page from `/domains` for A/B comparison of different UX approaches
- Mock data structure from `mock_data.yaml` used for topology during development
- Production: Topology data from Check Point API queries
- Each rule row creates one rule (not two like `/domains` cards)
