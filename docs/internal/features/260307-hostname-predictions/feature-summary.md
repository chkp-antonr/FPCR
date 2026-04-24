# Hostname Display in Predictions Panel

## Overview

Enhanced the Predictions panel to display hostnames alongside IPs when a match is found in the mock data. This provides better context for firewall rule predictions by showing which specific host an IP belongs to.

## Implementation Date

2026-01-07

## Problem Statement

Previously, the Predictions panel only displayed IP addresses without hostname context. Users had to manually cross-reference IPs with the `hosts` section in `mock_data.yaml` to identify specific hosts.

## Solution

### Backend Changes

**`src/fa/models.py`**
- Added `ip_hostnames: dict[str, str]` field to `TopologyEntry` for exact IP-to-hostname mapping
- Retained `hosts: List[str]` field for backward compatibility

**`src/fa/mock_source.py`**
- Added `_ip_in_subnet()` helper method for CIDR/single IP matching using Python's `ipaddress` module
- Updated `get_topology()` to populate `ip_hostnames` dictionary from `mock_data.yaml`

### Frontend Changes

**`webui/src/types/index.ts`**
- Added `ip_hostnames: Record<string, string>` to `TopologyEntry` and `PredictionCandidate`
- Added `hostname: string | null` to `Prediction` interface

**`webui/src/utils/predictionEngine.ts`**
- Modified to copy `ip_hostnames` from topology entries to prediction candidates
- Implemented exact IP lookup to determine hostname for each prediction

**`webui/src/components/PredictionsPanel.tsx`**
- Displays hostname in parentheses next to IP when available
- Domain names are bolded for better visual hierarchy

**`webui/src/styles/components/predictionsPanel.module.css`**
- Added `.hostnameText` class for secondary color styling

## Display Format

```
10.76.64.10 (USNY-CORP-WST-1) → AME_CORP US-NY-CORP
10.76.64.11 → AME_CORP US-NY-CORP
```

- IPs with exact hostname matches show the hostname in parentheses
- IPs without matches display only the IP address
- Domain names are bold for emphasis

## Mock Data Format

The `hosts` section in `mock_data.yaml` maps hostnames to IPs:

```yaml
hosts:
  USNY-CORP-WST-1: 10.76.64.10
  AMUS-WEB-SRV: 10.76.67.10
  EMLD-WEB-SRV: 10.76.131.10
  APTON-CORP-WST1: 10.76.192.10
```

## Key Design Decisions

1. **Exact IP Matching**: Uses dictionary lookup instead of array iteration for O(1) performance
2. **Dual Storage**: Keeps both `hosts` array and `ip_hostnames` dict for flexibility
3. **Snake_case Field Names**: Backend returns `ip_hostnames`, frontend matches (not camelCase)
4. **Graceful Degradation**: Predictions without hostname matches still display correctly

## Testing

**`src/fa/tests/test_mock_source.py`**
- Test basic hostname population from mock data
- Test CIDR subnet matching
- Test single IP matching
- Test invalid IP/subnet handling

## Related Files

- `mock_data.yaml` - Source of hostname mappings
- `src/fa/mock_source.py` - Topology data extraction
- `webui/src/utils/predictionEngine.ts` - Prediction generation
- `webui/src/components/PredictionsPanel.tsx` - Display rendering
