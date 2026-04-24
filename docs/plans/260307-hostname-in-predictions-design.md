# Hostname Display in Predictions - Design

**Date:** 2026-03-07

## Overview

Enhance the Predictions panel to display hostnames alongside IPs when a match is found in the mock data. When an IP from the source or destination pool matches a hostname defined in `mock_data.yaml`, the prediction will display as:

```
10.76.64.10 (USNY-CORP-WST-1) → AME_CORP US-NY-CORP
```

## Background

The current PredictionsPanel displays IP addresses matched against topology entries (domains/packages/firewalls/subnets) but does not show associated hostnames. The `mock_data.yaml` file contains a `hosts` section mapping hostnames to IPs, but this data is not utilized in the prediction display.

## Requirements

1. Parse the `hosts` section from `mock_data.yaml`
2. Match host IPs to topology subnet ranges
3. Include hostname in prediction display when a match is found
4. Handle edge cases gracefully (no match, multiple hosts, invalid data)

## Architecture

### Backend Changes

#### Model Update (`src/fa/models.py`)

Add `hosts` field to `TopologyEntry`:

```python
class TopologyEntry(BaseModel):
    domain: DomainItem
    package: PackageItem
    firewall: str
    subnets: list[str]
    hosts: list[str]  # Hostnames whose IPs match these subnets
```

#### MockDataSource Update (`src/fa/mock_source.py`)

Update `get_topology()` method to:

1. Load `hosts` section from `mock_data.yaml` (hostname → IP mapping)
2. For each TopologyEntry, check which host IPs fall within its subnets
3. Add matching hostnames to the `hosts` field

Example data flow:

```yaml
# mock_data.yaml
hosts:
  USNY-CORP-WST-1: 10.76.64.10
  USNY-CORP-WST-2: 10.76.64.11

domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets: [10.76.64.0/24]
```

Result: TopologyEntry for `USNY-CORP-FW-1` gets `hosts: ["USNY-CORP-WST-1", "USNY-CORP-WST-2"]`

### Frontend Changes

#### Type Updates (`webui/src/types/index.ts`)

```typescript
export interface TopologyEntry {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnets: string[];
  hosts: string[];  // NEW: Hostnames matching this topology entry
}

export interface PredictionCandidate {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnet: string;
  hostnames: string[];  // NEW: Copied from TopologyEntry.hosts
}

export interface Prediction {
  ip: IpEntry;
  candidates: PredictionCandidate[];
  source: 'source' | 'dest';
  hostname: string | null;  // NEW: First matching hostname, or null
}
```

#### Prediction Engine Update (`webui/src/utils/predictionEngine.ts`)

Update `generatePredictions()` to:

1. Copy `hosts` from TopologyEntry to PredictionCandidate
2. Extract the first hostname (if any) for the Prediction object

#### Display Update (`webui/src/components/PredictionsPanel.tsx`)

Update rendering to show hostname when available:

```typescript
<span className={styles.ipText}>
  {prediction.ip.original}
  {prediction.hostname && (
    <span className={styles.hostnameText}>
      {' ('}{prediction.hostname}{')'}
    </span>
  )}
</span>
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Host IP not in any subnet | Hostname not displayed, topology still works |
| Multiple hosts in one subnet | All added to TopologyEntry.hosts array |
| Host IP matches multiple subnets | Added to all matching TopologyEntry.hosts |
| Host entry has invalid IP | Logged, skipped (graceful degradation) |
| Mock data missing hosts section | Empty arrays, no errors |
| IP type is CIDR/range/FQDN | Only plain IPs matched against hosts |

## Testing

### Backend Tests

- Single host IP within subnet
- Multiple hosts in same subnet
- Host IP not matching any subnet
- Missing hosts section in mock data

### Frontend Tests

- Hostname included when IP matches topology entry with hosts
- Null hostname when no hosts match
- Multiple hostnames in candidate
- Empty hosts array

## Files to Change

| File | Change |
|------|--------|
| `src/fa/models.py` | Add `hosts: list[str]` to `TopologyEntry` |
| `src/fa/mock_source.py` | Update `get_topology()` to populate hosts |
| `webui/src/types/index.ts` | Add hosts-related fields to types |
| `webui/src/utils/predictionEngine.ts` | Copy hosts, extract hostname |
| `webui/src/components/PredictionsPanel.tsx` | Display hostname next to IP |
| `src/fa/tests/test_mock_source.py` | Add hostname population tests |
| `webui/src/utils/__tests__/predictionEngine.test.ts` | Add hostname handling tests |
