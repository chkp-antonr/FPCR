# Domains Rule Cards Design

**Date:** 2026-03-06

**Status:** Approved

**Author:** AI-Assisted Design

## Overview

Transform the `/domains` page from a sequential form to a card-based interface for creating firewall rules across multiple domains. Users define IP pools once, then create rule cards that each generate two rules (source-side and destination-side).

## Motivation

Traffic often traverses two firewalls: one at the source, one at the destination. Security teams need a efficient way to create matching rules on both firewalls simultaneously. The current sequential form is inefficient for this workflow.

## Architecture

### Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [▼ IP POOLS] Source: 5, Dest: 3                            │  ← collapsible, expanded by default
│  ┌─────────────┬─────────────┬──────────────┐               │
│  │ Source IPs  │ Dest IPs    │ Services     │               │
│  │ [textarea]  │ [textarea]  │ [textarea]   │               │
│  └─────────────┴─────────────┴──────────────┘               │
├─────────────────────────────────────────────────────────────┤
│  [+ Add Card]                                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ → (horizontal scroll)     │
│  │ Card 1 │ │ Card 2 │ │ Card 3 │                           │
│  └────────┘ └────────┘ └────────┘                           │
├─────────────────────────────────────────────────────────────┤
│  [Submit Rules]                                             │
└─────────────────────────────────────────────────────────────┘
```

### Component Structure

```
Domains.tsx
├── IpPoolsPanel (new)
│   ├── Collapsible header with badge
│   ├── SourceIpInput (TextArea)
│   ├── DestIpInput (TextArea)
│   └── ServicesInput (TextArea)
├── AddCardButton
├── CardsContainer (horizontal scroll)
│   └── RuleCard (repeated)
│       ├── CardHeader ([↑] [↓] [🗑])
│       ├── SourceLine
│       │   ├── Label: "Source:"
│       │   ├── IP dropdown (from pool)
│       │   ├── Domain dropdown
│       │   ├── Package dropdown (cascades)
│       │   ├── Section dropdown (cascades)
│       │   ├── Position: Top/Bottom/Custom
│       │   ├── Action: Accept/Drop
│       │   └── Track: Log/None
│       ├── SamePackageCheckbox
│       └── DestinationLine (same fields)
└── SubmitButton
```

## Card Internal Layout

Each card displays two lines with 7 fields each:

**Source Line:** `Source: [IP] [Domain] [Package] [Section] [Position] [Action] [Track]`

**Destination Line:** `Destination: [IP] [Domain] [Package] [Section] [Position] [Action] [Track]`

**Same Package Checkbox:** When checked, destination settings copy from source. Auto-unchecks if domains differ.

## Card Controls

### Per-Card Header Buttons

| Button | Action |
|--------|--------|
| ↑ | Move card one position earlier (left) |
| ↓ | Move card one position later (right) |
| 🗑 | Delete this card |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Click card | Select (blue border) |
| Ctrl + ↑ | Move selected card earlier |
| Ctrl + ↓ | Move selected card later |
| Delete | Delete selected card |
| Tab / Shift + Tab | Navigate between cards |

### Add Card Button

Single "+ Add Card" button above container. Appends new card to right.

## IP Validation

### Accepted Formats

- IPv4: `10.1.1.1`
- IPv4 CIDR: `10.1.1.0/24`
- IPv6: `2001:db8::1`
- IPv6 CIDR: `2001:db8::/32`
- FQDN: `server.example.com`, `*.example.com`
- Range: `10.1.1.1-10.1.1.10`
- Any: `any`

### Separators

Newline, comma, semicolon, space, tab. Multiple consecutive separators treated as one.

### Validation Triggers

- On paste (Ctrl+V)
- On blur (leaving textarea)
- On keystroke (debounced, 500ms)

### Smart IP Defaulting

Each new card defaults to the first **unused** IP from each pool. Usage tracks across all cards. Deleting a card frees its IPs back to the pool.

## TypeScript Types

```typescript
interface IpEntry {
  original: string;
  type: 'ipv4' | 'ipv6' | 'ipv4-cidr' | 'ipv6-cidr' | 'fqdn' | 'range' | 'any';
  normalized: string;
}

interface IpPool {
  raw: string;
  validated: IpEntry[];
  invalid: string[];
  errors: string[];
}

interface RuleCard {
  id: string;
  source: RuleLine;
  destination: RuleLine;
  samePackage: boolean;
}

interface RuleLine {
  ip: IpEntry | null;
  domain: DomainItem | null;
  package: PackageItem | null;
  section: SectionItem | null;
  position: PositionChoice;
  action: 'accept' | 'drop';
  track: 'log' | 'none';
}
```

## API Integration

### New Endpoint

```
POST /api/v1/domains/rules/batch
```

**Request Body:** Array of rule objects containing source and destination rule definitions.

**Response:**

```typescript
interface BatchRulesResponse {
  success: boolean;
  created: number;
  failed: number;
  errors: Array<{ rule_id: string; message: string }>;
}
```

**Note:** Mock implementation only. No actual Check Point API calls yet. Validates and returns success.

## Submission Flow

1. User clicks "Submit Rules"
2. Validate all cards (required fields, position ranges)
3. Transform cards to request format
4. POST to `/api/v1/domains/rules/batch`
5. Show success message
6. Clear all cards

## Error Handling

### IP Validation

- Invalid format: Inline error below textarea, red highlight
- Duplicates: Warning badge, allow but highlight
- Empty pool: Disable dropdowns, show "No valid IPs"

### Card Validation

- Missing fields: Disable Submit, inline "Required" label
- Invalid position: Error message, disable Submit
- Cascading clears: Reset dependent fields

### API Errors

- Network failure: Toast error, keep cards for retry
- 401: Redirect to login
- Partial success: Show "X created, Y failed", keep failed cards

## Visual States

- Selected: Blue border (#1677ff)
- Errors: Red border (#ff4d4f)
- Disabled (same package): Grayed out fields

## Future Enhancements

- Drag-and-drop IP reordering within cards
- Persistence across page refresh
- Bulk edit operations
- Rule preview before submission
- Actual Check Point API integration
