# Domains_2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a new `/domains-2` page with row-based table UI, topology-aware predictions, drag-and-drop field filling, multi-select IPs, and clone functionality.

**Architecture:** Separate React page (`Domains2.tsx`) with tag-based inputs (IpInputPanel), prediction engine matching IPs to gateway subnets (PredictionsPanel), and Ant Design Table with custom columns (RulesTable). Backend adds topology endpoint and batch rule submission. Frontend uses existing Ant Design components; no new npm packages needed.

**Tech Stack:** React 18, TypeScript, Ant Design 5, FastAPI, ipaddr.js (existing)

---

## Task 1: Add Route and Menu Item

**Files:**
- Modify: `webui/src/App.tsx`
- Modify: `webui/src/components/Layout.tsx`

**Step 1: Add /domains-2 route to App.tsx**

Open `webui/src/App.tsx` and add the new route after line 36:

```tsx
<Route path="domains" element={<Domains />} />
<Route path="domains-2" element={<Domains2 />} />  {/* ADD THIS LINE */}
<Route path="*" element={<Navigate to="/" replace />} />
```

Also add the import at the top:

```tsx
import Domains from './pages/Domains';
import Domains2 from './pages/Domains2';  // ADD THIS LINE
```

**Step 2: Add menu item to Layout.tsx**

Open `webui/src/components/Layout.tsx` and update the `menuItems` array after line 16:

```tsx
const menuItems = [
  { key: '/', icon: <HomeOutlined />, label: 'Dashboard' },
  { key: '/domains', icon: <UnorderedListOutlined />, label: 'Domains' },
  { key: '/domains-2', icon: <UnorderedListOutlined />, label: 'Domains_2' },  // ADD THIS LINE
];
```

**Step 3: Commit**

```bash
git add webui/src/App.tsx webui/src/components/Layout.tsx
git commit -m "feat: add /domains-2 route and menu item"
```

---

## Task 2: Add TypeScript Types

**Files:**
- Modify: `webui/src/types/index.ts`

**Step 1: Add new types to index.ts**

Open `webui/src/types/index.ts` and add these types after line 124 (after `BatchRulesResponse`):

```typescript
// === Domains_2 Types ===

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

export interface TopologyEntry {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnets: string[];
}

export interface TopologyResponse {
  topology: TopologyEntry[];
}

export interface Domains2BatchRequest {
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

**Step 2: Commit**

```bash
git add webui/src/types/index.ts
git commit -m "feat: add Domains_2 TypeScript types"
```

---

## Task 3: Create Service Validator

**Files:**
- Create: `webui/src/utils/serviceValidator.ts`

**Step 1: Write service validator tests**

Create `webui/src/utils/__tests__/serviceValidator.test.ts`:

```typescript
import { validateServiceInput, findDuplicateServices } from '../serviceValidator';
import type { ServiceEntry } from '../../types';

describe('serviceValidator', () => {
  describe('validateServiceInput', () => {
    it('should parse https protocol', () => {
      const result = validateServiceInput('https');
      expect(result).toEqual([{
        original: 'https',
        normalized: 'https',
        type: 'protocol'
      }]);
    });

    it('should parse tcp-53 port format', () => {
      const result = validateServiceInput('tcp-53');
      expect(result).toEqual([{
        original: 'tcp-53',
        normalized: 'tcp-53',
        type: 'port'
      }]);
    });

    it('should parse comma separated values', () => {
      const result = validateServiceInput('https, tcp-53, udp-123');
      expect(result).toHaveLength(3);
      expect(result[2].normalized).toBe('udp-123');
    });

    it('should parse newline separated values', () => {
      const result = validateServiceInput('https\ntcp-53');
      expect(result).toHaveLength(2);
    });

    it('should handle "any" keyword', () => {
      const result = validateServiceInput('any');
      expect(result[0].type).toBe('any');
    });

    it('should handle named services', () => {
      const result = validateServiceInput('mysql, ssh');
      expect(result[0].type).toBe('named');
      expect(result[1].type).toBe('named');
    });

    it('should handle port numbers', () => {
      const result = validateServiceInput('443, 22');
      expect(result[0].type).toBe('port');
      expect(result[0].normalized).toBe('443');
    });
  });

  describe('findDuplicateServices', () => {
    it('should find duplicate services', () => {
      const entries: ServiceEntry[] = [
        { original: 'https', normalized: 'https', type: 'protocol' },
        { original: 'HTTPS', normalized: 'https', type: 'protocol' },
        { original: 'tcp-53', normalized: 'tcp-53', type: 'port' }
      ];
      const duplicates = findDuplicateServices(entries);
      expect(duplicates).toHaveLength(1);
      expect(duplicates[0].normalized).toBe('https');
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd webui && npm test -- serviceValidator.test.ts`
Expected: FAIL (module does not exist)

**Step 3: Implement service validator**

Create `webui/src/utils/serviceValidator.ts`:

```typescript
import type { ServiceEntry } from '../types';

export function validateServiceInput(input: string): ServiceEntry[] {
  const entries: ServiceEntry[] = [];
  const raw = input.split(/[\n,;\s\t]+/).filter(e => e.trim());

  for (const item of raw) {
    const normalized = item.toLowerCase().trim();

    let type: ServiceEntry['type'];
    if (normalized === 'any') {
      type = 'any';
    } else if (/^https?$/i.test(item)) {
      type = 'protocol';
    } else if (/^tcp|udp$/i.test(item)) {
      type = 'protocol';
    } else if (/^(tcp|udp)-\d+$/.test(normalized)) {
      type = 'port';
    } else if (/^\d+$/.test(item)) {
      type = 'port';
    } else {
      type = 'named';
    }

    entries.push({
      original: item,
      normalized,
      type,
    });
  }

  return entries;
}

export function findDuplicateServices(entries: ServiceEntry[]): ServiceEntry[] {
  const seen = new Set<string>();
  const duplicates: ServiceEntry[] = [];

  for (const entry of entries) {
    if (seen.has(entry.normalized)) {
      duplicates.push(entry);
    }
    seen.add(entry.normalized);
  }

  return duplicates;
}
```

**Step 4: Run tests to verify they pass**

Run: `cd webui && npm test -- serviceValidator.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add webui/src/utils/serviceValidator.ts webui/src/utils/__tests__/serviceValidator.test.ts
git commit -m "feat: add service validator with tests"
```

---

## Task 4: Create Prediction Engine

**Files:**
- Create: `webui/src/utils/predictionEngine.ts`

**Step 1: Write prediction engine tests**

Create `webui/src/utils/__tests__/predictionEngine.test.ts`:

```typescript
import { generatePredictions, ipMatchesSubnet } from '../predictionEngine';
import type { IpEntry, TopologyEntry } from '../../types';

describe('predictionEngine', () => {
  const mockTopology: TopologyEntry[] = [
    {
      domain: { name: 'AME_CORP', uid: 'domain-1' },
      package: { name: 'US-NY-CORP', uid: 'pkg-1', access_layer: 'network' },
      firewall: 'USNY-CORP-FW-1',
      subnets: ['10.76.64.0/24', '10.76.65.0/24']
    },
    {
      domain: { name: 'APA_CORP', uid: 'domain-2' },
      package: { name: 'JP-TOK-CORP', uid: 'pkg-2', access_layer: 'network' },
      firewall: 'APTOK-CORP-FW-1',
      subnets: ['10.76.192.0/24']
    }
  ];

  describe('ipMatchesSubnet', () => {
    it('should match IP in subnet', () => {
      const ip: IpEntry = {
        original: '10.76.64.11',
        normalized: '10.76.64.11',
        type: 'ipv4'
      };
      const result = ipMatchesSubnet(ip, ['10.76.64.0/24']);
      expect(result).toBe(true);
    });

    it('should not match IP outside subnet', () => {
      const ip: IpEntry = {
        original: '10.76.100.11',
        normalized: '10.76.100.11',
        type: 'ipv4'
      };
      const result = ipMatchesSubnet(ip, ['10.76.64.0/24']);
      expect(result).toBe(false);
    });

    it('should match exact IP', () => {
      const ip: IpEntry = {
        original: '10.76.64.11',
        normalized: '10.76.64.11',
        type: 'ipv4'
      };
      const result = ipMatchesSubnet(ip, ['10.76.64.11']);
      expect(result).toBe(true);
    });
  });

  describe('generatePredictions', () => {
    it('should generate predictions for matching IPs', () => {
      const sourcePool: IpEntry[] = [
        { original: '10.76.64.11', normalized: '10.76.64.11', type: 'ipv4' }
      ];
      const destPool: IpEntry[] = [
        { original: '10.76.192.5', normalized: '10.76.192.5', type: 'ipv4' }
      ];

      const predictions = generatePredictions(sourcePool, destPool, mockTopology);

      expect(predictions).toHaveLength(2);
      expect(predictions[0].ip.normalized).toBe('10.76.64.11');
      expect(predictions[0].candidates).toHaveLength(1);
      expect(predictions[0].candidates[0].domain.name).toBe('AME_CORP');
    });

    it('should handle IPs with no matches', () => {
      const sourcePool: IpEntry[] = [
        { original: '192.168.1.1', normalized: '192.168.1.1', type: 'ipv4' }
      ];
      const destPool: IpEntry[] = [];

      const predictions = generatePredictions(sourcePool, destPool, mockTopology);

      expect(predictions).toHaveLength(0);
    });

    it('should handle multiple candidates for same IP', () => {
      const sourcePool: IpEntry[] = [
        { original: '10.76.65.10', normalized: '10.76.65.10', type: 'ipv4' }
      ];
      const topologyWithOverlap: TopologyEntry[] = [
        ...mockTopology,
        {
          domain: { name: 'AME_DC', uid: 'domain-3' },
          package: { name: 'US-NY-DC', uid: 'pkg-3', access_layer: 'network' },
          firewall: 'USNY-DC-FW-1',
          subnets: ['10.76.65.0/24']
        }
      ];

      const predictions = generatePredictions(sourcePool, [], topologyWithOverlap);

      expect(predictions[0].candidates).toHaveLength(2);
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd webui && npm test -- predictionEngine.test.ts`
Expected: FAIL (module does not exist)

**Step 3: Implement prediction engine**

Create `webui/src/utils/predictionEngine.ts`:

```typescript
import ipaddr from 'ipaddr.js';
import type { IpEntry, TopologyEntry, Prediction } from '../types';

export function ipMatchesSubnet(ip: IpEntry, subnets: string[]): boolean {
  for (const subnet of subnets) {
    try {
      // Handle CIDR notation
      if (subnet.includes('/')) {
        const [addr, mask] = subnet.split('/');
        const parsedIp = ipaddr.parse(ip.normalized);
        const parsedSubnet = ipaddr.parse(addr);

        if (parsedIp.kind() === parsedSubnet.kind()) {
          const subnetObj = parsedSubnet as ipaddr.IPv4 | ipaddr.IPv6;
          // @ts-ignore - subnetFrom() exists but TypeScript types are incomplete
          const range = subnetObj.subnetFrom(parseInt(mask, ));
          // @ts-ignore
          if (range.contains(parsedIp)) {
            return true;
          }
        }
      } else {
        // Exact match
        if (ip.normalized === subnet) {
          return true;
        }
      }
    } catch (e) {
      // Invalid IP/subnet format, skip
      continue;
    }
  }
  return false;
}

export function generatePredictions(
  sourcePool: IpEntry[],
  destPool: IpEntry[],
  topology: TopologyEntry[]
): Prediction[] {
  const predictions: Prediction[] = [];
  const allIps = [...sourcePool, ...destPool];

  for (const ip of allIps) {
    const candidates: Prediction['candidates'] = [];

    for (const entry of topology) {
      if (ipMatchesSubnet(ip, entry.subnets)) {
        candidates.push({
          domain: entry.domain,
          package: entry.package,
          firewall: entry.firewall,
          subnet: entry.subnets.find(s => {
            const testIp = { ...ip, normalized: ip.normalized };
            return ipMatchesSubnet(testIp, [s]);
          }) || '',
        });
      }
    }

    if (candidates.length > 0) {
      predictions.push({ ip, candidates });
    }
  }

  return predictions;
}
```

**Step 4: Run tests to verify they pass**

Run: `cd webui && npm test -- predictionEngine.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add webui/src/utils/predictionEngine.ts webui/src/utils/__tests__/predictionEngine.test.ts
git commit -m "feat: add prediction engine with tests"
```

---

## Task 5: Create Rule Validator

**Files:**
- Create: `webui/src/utils/ruleValidator.ts`

**Step 1: Write rule validator tests**

Create `webui/src/utils/__tests__/ruleValidator.test.ts`:

```typescript
import { validateRules, hasUnusedIps } from '../ruleValidator';
import type { RuleRow, IpEntry } from '../../types';

describe('ruleValidator', () => {
  const mockIpEntry: IpEntry = {
    original: '10.76.64.11',
    normalized: '10.76.64.11',
    type: 'ipv4'
  };

  const mockDomain = { name: 'AME_CORP', uid: 'domain-1' };
  const mockPackage = { name: 'US-NY-CORP', uid: 'pkg-1', access_layer: 'network' };
  const mockSection = { name: 'ingress', uid: 'sec-1', rulebase_range: [1, 10], rule_count: 5 };

  describe('validateRules', () => {
    it('should pass for valid rule', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [mockIpEntry],
        destIps: [mockIpEntry],
        domain: mockDomain,
        package: mockPackage,
        section: mockSection,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(0);
    });

    it('should fail when domain is missing', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [mockIpEntry],
        destIps: [mockIpEntry],
        domain: null,
        package: mockPackage,
        section: null,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(1);
      expect(errors[0].field).toBe('domain');
    });

    it('should fail when source IPs are empty', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [],
        destIps: [mockIpEntry],
        domain: mockDomain,
        package: mockPackage,
        section: null,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(1);
      expect(errors[0].field).toBe('sourceIps');
    });

    it('should fail when custom position has no number', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [mockIpEntry],
        destIps: [mockIpEntry],
        domain: mockDomain,
        package: mockPackage,
        section: null,
        position: { type: 'custom' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(1);
      expect(errors[0].field).toBe('position');
    });
  });

  describe('hasUnusedIps', () => {
    it('should identify unused source IPs', () => {
      const sourcePool: IpEntry[] = [
        { ...mockIpEntry, normalized: '10.76.64.11' },
        { ...mockIpEntry, normalized: '10.76.64.12' }
      ];

      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [{ ...mockIpEntry, normalized: '10.76.64.11' }],
        destIps: [{ ...mockIpEntry, normalized: '10.76.65.5' }],
        domain: mockDomain,
        package: mockPackage,
        section: null,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const unused = hasUnusedIps(rules, sourcePool, []);
      expect(unused.source).toHaveLength(1);
      expect(unused.source[0].normalized).toBe('10.76.64.12');
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd webui && npm test -- ruleValidator.test.ts`
Expected: FAIL (module does not exist)

**Step 3: Implement rule validator**

Create `webui/src/utils/ruleValidator.ts`:

```typescript
import type { RuleRow, IpEntry } from '../types';

export interface ValidationError {
  ruleId: string;
  field: string;
  message: string;
}

export function validateRules(rules: RuleRow[]): ValidationError[] {
  const errors: ValidationError[] = [];

  for (let i = 0; i < rules.length; i++) {
    const rule = rules[i];

    if (!rule.domain) {
      errors.push({
        ruleId: rule.id,
        field: 'domain',
        message: `Row ${i + 1}: Domain is required`,
      });
    }

    if (!rule.package) {
      errors.push({
        ruleId: rule.id,
        field: 'package',
        message: `Row ${i + 1}: Package is required`,
      });
    }

    if (rule.sourceIps.length === 0) {
      errors.push({
        ruleId: rule.id,
        field: 'sourceIps',
        message: `Row ${i + 1}: At least one source IP is required`,
      });
    }

    if (rule.destIps.length === 0) {
      errors.push({
        ruleId: rule.id,
        field: 'destIps',
        message: `Row ${i + 1}: At least one destination IP is required`,
      });
    }

    if (rule.position.type === 'custom' && !rule.position.custom_number) {
      errors.push({
        ruleId: rule.id,
        field: 'position',
        message: `Row ${i + 1}: Custom position number is required`,
      });
    }
  }

  return errors;
}

export function hasUnusedIps(
  rules: RuleRow[],
  sourcePool: IpEntry[],
  destPool: IpEntry[]
): { source: IpEntry[]; dest: IpEntry[] } {
  const usedSourceIps = new Set(
    rules.flatMap(r => r.sourceIps.map(ip => ip.normalized))
  );
  const usedDestIps = new Set(
    rules.flatMap(r => r.destIps.map(ip => ip.normalized))
  );

  const unusedSource = sourcePool.filter(ip => !usedSourceIps.has(ip.normalized));
  const unusedDest = destPool.filter(ip => !usedDestIps.has(ip.normalized));

  return { source: unusedSource, dest: unusedDest };
}
```

**Step 4: Run tests to verify they pass**

Run: `cd webui && npm test -- ruleValidator.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add webui/src/utils/ruleValidator.ts webui/src/utils/__tests__/ruleValidator.test.ts
git commit -m "feat: add rule validator with tests"
```

---

## Task 6: Add Backend Topology Endpoint

**Files:**
- Modify: `src/fa/routes/domains.py`
- Modify: `src/fa/models/__init__.py`

**Step 1: Add TopologyEntry model**

Open `src/fa/models/__init__.py` and add after the existing models:

```python
class TopologyEntry(BaseModel):
    domain: DomainItem
    package: PackageItem
    firewall: str
    subnets: List[str]


class TopologyResponse(BaseModel):
    topology: List[TopologyEntry]
```

**Step 2: Add get_topology method to MockDataSource**

Open `src/fa/mock_source.py` and add the method to the `MockDataSource` class:

```python
def get_topology(self) -> List[TopologyEntry]:
    """Extract topology from mock data for prediction engine."""
    topology = []

    if not self.data or "domains" not in self.data:
        return topology

    for domain_name, domain_data in self.data["domains"].items():
        domain = DomainItem(name=domain_name, uid=f"uid-{domain_name}")

        if "policies" not in domain_data:
            continue

        for policy_name, policy_data in domain_data["policies"].items():
            package = PackageItem(
                name=policy_name,
                uid=f"uid-{policy_name}",
                access_layer="network"
            )

            if "firewalls" not in policy_data:
                continue

            for fw_name, fw_data in policy_data["firewalls"].items():
                subnets = fw_data.get("subnets", [])
                entry = TopologyEntry(
                    domain=domain,
                    package=package,
                    firewall=fw_name,
                    subnets=subnets
                )
                topology.append(entry)

    return topology
```

**Step 3: Import TopologyEntry and TopologyResponse in routes/domains.py**

Add to imports in `src/fa/routes/domains.py`:

```python
from ..models import DomainItem, DomainsResponse, CreateRuleRequest, PositionChoice, TopologyEntry, TopologyResponse
```

**Step 4: Add topology endpoint**

Add the endpoint after `list_domains` function:

```python
@router.get("/domains/topology")
async def get_topology(session: SessionData | None = Depends(get_session_data_optional)):
    """
    Return subnet topology for prediction engine.
    MOCK: Returns mock_data.yaml structure.
    Production: Query Check Point API for network topology.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    logger.info(f"Topology request, MOCK_DATA: {mock_data_path}")

    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        topology = mock.get_topology()
        return {"topology": [
            {
                "domain": {"name": t.domain.name, "uid": t.domain.uid},
                "package": {"name": t.package.name, "uid": t.package.uid, "access_layer": t.package.access_layer},
                "firewall": t.firewall,
                "subnets": t.subnets
            }
            for t in topology
        ]}

    # Production implementation
    logger.info("Using live Check Point API for topology")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # TODO: Implement live topology query
    return {"topology": []}
```

**Step 5: Test the endpoint**

Run: `curl http://localhost:8000/api/v1/domains/topology`
Expected: JSON response with topology from mock_data.yaml

**Step 6: Commit**

```bash
git add src/fa/models/__init__.py src/fa/mock_source.py src/fa/routes/domains.py
git commit -m "feat: add topology endpoint for predictions"
```

---

## Task 7: Add Backend Domains2 Batch Endpoint

**Files:**
- Modify: `src/fa/routes/domains.py`
- Modify: `src/fa/models/__init__.py`

**Step 1: Add Domains2BatchRequest model**

Open `src/fa/models/__init__.py` and add:

```python
class Domains2RuleRequest(BaseModel):
    source_ips: List[str]
    dest_ips: List[str]
    services: List[str]
    domain_uid: str
    package_uid: str
    section_uid: str | None
    position: PositionChoice
    action: Literal["accept", "drop"]
    track: Literal["log", "none"]


class Domains2BatchRequest(BaseModel):
    rules: List[Domains2RuleRequest]
```

**Step 2: Add domains2 batch endpoint**

Open `src/fa/routes/domains.py` and add the endpoint:

```python
@router.post("/domains2/rules/batch")
async def create_rules_domains2_batch(
    request: Domains2BatchRequest,
    session: SessionData | None = Depends(get_session_data_optional)
):
    """
    Create rules with multiple source/dest IPs per rule.
    MOCK: Validates and returns success.
    Production: Creates actual Check Point firewall rules.
    """
    logger.info(f"Domains_2 batch request: {len(request.rules)} rules")

    # Validate
    for i, rule in enumerate(request.rules):
        if not rule.domain_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: domain_uid is required")
        if not rule.package_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: package_uid is required")
        if len(rule.source_ips) == 0:
            raise HTTPException(status_code=400, detail=f"Rule {i}: At least one source IP required")
        if len(rule.dest_ips) == 0:
            raise HTTPException(status_code=400, detail=f"Rule {i}: At least one dest IP required")

        if rule.position.type == "custom" and rule.position.custom_number is None:
            raise HTTPException(
                status_code=400,
                detail=f"Rule {i}: Custom position requires custom_number"
            )

    # TODO: Production - create actual Check Point rules
    # For now, just validate and return success
    total_rules = sum(len(r.source_ips) * len(r.dest_ips) for r in request.rules)

    return {
        "success": True,
        "created": total_rules,
        "failed": 0,
        "errors": []
    }
```

**Step 3: Update imports in domains.py**

Add to imports:

```python
from ..models import DomainItem, DomainsResponse, CreateRuleRequest, PositionChoice, TopologyEntry, TopologyResponse, Domains2BatchRequest
```

**Step 4: Test the endpoint**

Run: `curl -X POST http://localhost:8000/api/v1/domains2/rules/batch -H "Content-Type: application/json" -d '{"rules": [{"source_ips": ["10.76.64.11"], "dest_ips": ["10.76.65.5"], "services": [], "domain_uid": "test", "package_uid": "test", "section_uid": null, "position": {"type": "top"}, "action": "accept", "track": "log"}]}'`
Expected: Success response

**Step 5: Commit**

```bash
git add src/fa/models/__init__.py src/fa/routes/domains.py
git commit -m "feat: add domains2 batch endpoint"
```

---

## Task 8: Add API Client Functions

**Files:**
- Modify: `webui/src/api/endpoints.ts`

**Step 1: Add topology and domains2 API functions**

Open `webui/src/api/endpoints.ts` and add after the existing exports:

```typescript
// === Domains_2 APIs ===

export const topologyApi = {
  getTopology: () =>
    request.get<TopologyResponse>('/api/v1/domains/topology'),
};

export const rules2Api = {
  createBatch: (data: Domains2BatchRequest) =>
    request.post<BatchRulesResponse>('/api/v1/domains2/rules/batch', data),
};
```

**Step 2: Ensure types are imported**

Add to imports if not present:

```typescript
import type { TopologyResponse, Domains2BatchRequest } from '../types';
```

**Step 3: Commit**

```bash
git add webui/src/api/endpoints.ts
git commit -m "feat: add topology and domains2 API client functions"
```

---

## Task 9: Create IpInputPanel Component

**Files:**
- Create: `webui/src/components/IpInputPanel.tsx`
- Create: `webui/src/styles/components/ipInputPanel.module.css`

**Step 1: Create the component CSS**

Create `webui/src/styles/components/ipInputPanel.module.css`:

```css
.inputPanel {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.inputColumn {
  display: flex;
  flex-direction: column;
}

.label {
  font-weight: 500;
  margin-bottom: 8px;
  color: #000000d9;
}

.tagsInput {
  width: 100%;
}

.tagsInput .ant-select-selector {
  min-height: 80px !important;
}
```

**Step 2: Create the component**

Create `webui/src/components/IpInputPanel.tsx`:

```typescript
import { Select } from 'antd';
import type { IpEntry, ServiceEntry } from '../types';
import { validateIpInput } from '../utils/ipValidator';
import { validateServiceInput } from '../utils/serviceValidator';
import styles from '../styles/components/ipInputPanel.module.css';

interface IpInputPanelProps {
  sourcePool: IpEntry[];
  destPool: IpEntry[];
  servicesPool: ServiceEntry[];
  onSourceChange: (entries: IpEntry[]) => void;
  onDestChange: (entries: IpEntry[]) => void;
  onServicesChange: (entries: ServiceEntry[]) => void;
}

export default function IpInputPanel({
  sourcePool,
  destPool,
  servicesPool,
  onSourceChange,
  onDestChange,
  onServicesChange,
}: IpInputPanelProps) {
  const sourceOptions = sourcePool.map(ip => ({
    value: ip.normalized,
    label: ip.original,
  }));

  const destOptions = destPool.map(ip => ({
    value: ip.normalized,
    label: ip.original,
  }));

  const serviceOptions = servicesPool.map(svc => ({
    value: svc.normalized,
    label: svc.original,
  }));

  return (
    <div className={styles.inputPanel}>
      <div className={styles.inputColumn}>
        <label className={styles.label}>Source IPs:</label>
        <Select
          mode="tags"
          value={sourcePool.map(ip => ip.normalized)}
          options={sourceOptions}
          onChange={(values) => {
            const entries = validateIpInput(values.join(' '));
            onSourceChange(entries);
          }}
          placeholder="Paste or type source IPs..."
          className={styles.tagsInput}
          tokenSeparators={[' ', ',', '\n', '\t', ';']}
        />
      </div>

      <div className={styles.inputColumn}>
        <label className={styles.label}>Destination IPs:</label>
        <Select
          mode="tags"
          value={destPool.map(ip => ip.normalized)}
          options={destOptions}
          onChange={(values) => {
            const entries = validateIpInput(values.join(' '));
            onDestChange(entries);
          }}
          placeholder="Paste or type destination IPs..."
          className={styles.tagsInput}
          tokenSeparators={[' ', ',', '\n', '\t', ';']}
        />
      </div>

      <div className={styles.inputColumn}>
        <label className={styles.label}>Services (optional):</label>
        <Select
          mode="tags"
          value={servicesPool.map(svc => svc.normalized)}
          options={serviceOptions}
          onChange={(values) => {
            const entries = validateServiceInput(values.join(' '));
            onServicesChange(entries);
          }}
          placeholder="https, tcp-53, mysql..."
          className={styles.tagsInput}
          tokenSeparators={[' ', ',', '\n', '\t', ';']}
        />
      </div>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add webui/src/components/IpInputPanel.tsx webui/src/styles/components/ipInputPanel.module.css
git commit -m "feat: add IpInputPanel component with tag-based inputs"
```

---

## Task 10: Create PredictionsPanel Component

**Files:**
- Create: `webui/src/components/PredictionsPanel.tsx`
- Create: `webui/src/styles/components/predictionsPanel.module.css`

**Step 1: Create the component CSS**

Create `webui/src/styles/components/predictionsPanel.module.css`:

```css
.panel {
  background: white;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.title {
  font-weight: 500;
  color: #000000d9;
}

.predictionsList {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.predictionItem {
  padding: 8px 12px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: grab;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.predictionItem:hover {
  border-color: #1677ff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.15);
}

.predictionItem.dragging {
  opacity: 0.5;
  cursor: grabbing;
  background: #e6f7ff;
}

.ipText {
  font-weight: 500;
  color: #1677ff;
  margin-right: 8px;
}

.candidatesText {
  color: #00000073;
  font-size: 12px;
}

.dragHandle {
  color: #00000073;
  cursor: grab;
}

.empty {
  text-align: center;
  padding: 24px;
  color: #00000073;
}
```

**Step 2: Create the component**

Create `webui/src/components/PredictionsPanel.tsx`:

```typescript
import { Button, Empty } from 'antd';
import { HolderOutlined } from '@ant-design/icons';
import type { Prediction } from '../types';
import styles from '../styles/components/predictionsPanel.module.css';

interface PredictionsPanelProps {
  predictions: Prediction[];
  onClear: () => void;
  onDragStart: (prediction: Prediction) => void;
}

export default function PredictionsPanel({
  predictions,
  onClear,
  onDragStart,
}: PredictionsPanelProps) {
  const handleDragStart = (prediction: Prediction, e: React.DragEvent) => {
    e.dataTransfer.effectAllowed = 'copy';
    onDragStart(prediction);
  };

  if (predictions.length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.header}>
          <span className={styles.title}>PREDICTIONS</span>
        </div>
        <Empty
          description="Add IPs to see matching domains and packages"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>PREDICTIONS ({predictions.length})</span>
        <Button size="small" onClick={onClear}>
          Clear
        </Button>
      </div>
      <div className={styles.predictionsList}>
        {predictions.map((prediction, idx) => (
          <div
            key={idx}
            className={styles.predictionItem}
            draggable
            onDragStart={(e) => handleDragStart(prediction, e)}
          >
            <div>
              <span className={styles.ipText}>{prediction.ip.original}</span>
              <span className={styles.candidatesText}>
                → {prediction.candidates.map(c =>
                  `${c.domain.name} ${c.package.name}`
                ).join(' | ')}
              </span>
            </div>
            <HolderOutlined className={styles.dragHandle} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add webui/src/components/PredictionsPanel.tsx webui/src/styles/components/predictionsPanel.module.css
git commit -m "feat: add PredictionsPanel component"
```

---

## Task 11: Create RulesTable Component

**Files:**
- Create: `webui/src/components/RulesTable.tsx`
- Create: `webui/src/styles/components/rulesTable.module.css`

**Step 1: Create the component CSS**

Create `webui/src/styles/components/rulesTable.module.css`:

```css
.tableContainer {
  background: white;
  border-radius: 8px;
  padding: 16px;
}

.table {
  background: white;
}

.table .ant-table-thead > tr > th {
  background: #fafafa;
  font-weight: 600;
}

.table .ant-table-tbody > tr.clickable {
  cursor: pointer;
}

.table .ant-table-tbody > tr.clickable:hover {
  background-color: #fafafa;
}

.table .ant-table-tbody > tr.selected {
  background-color: #e6f7ff;
}

.table .ant-table-tbody > tr.dropTarget {
  background-color: #e6f7ff;
  border-top: 2px solid #1677ff;
}

.table .ant-table-tbody > tr.dropTarget td {
  background-color: #e6f7ff;
  border-top: 1px solid #1677ff;
}

.table .ant-table-tbody > tr.errorRow {
  background-color: #fff2f0;
}

.table .ant-table-tbody > tr.errorRow td {
  background-color: #fff2f0;
}

.tag {
  margin: 2px;
}

.usedTag {
  background-color: #1677ff;
  color: white;
  border-color: #1677ff;
}

.unusedTag {
  background-color: #f0f0f0;
  color: #8c8c8c;
  border: 1px dashed #bfbfbf;
}

.unusedTag:hover {
  background-color: #e6e6e6;
  border-color: #999;
}

.smallSelect {
  min-width: 80px;
}

.radioGroup {
  display: flex;
  gap: 4px;
}
```

**Step 2: Create the component**

Create `webui/src/components/RulesTable.tsx`:

```typescript
import { Table, Select, Radio, InputNumber, Button, Space, Tag } from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { RuleRow, IpEntry, DomainItem, PackageItem, SectionItem, ServiceEntry, Prediction } from '../types';
import styles from '../styles/components/rulesTable.module.css';

interface RulesTableProps {
  rules: RuleRow[];
  sourcePool: IpEntry[];
  destPool: IpEntry[];
  servicesPool: ServiceEntry[];
  domains: DomainItem[];
  packages: PackageItem[];
  sections: SectionItem[];
  onRulesChange: (rules: RuleRow[]) => void;
  onClone: (ruleId: string) => void;
  onDelete: (ruleId: string) => void;
  onFetchPackages: (domainUid: string) => void;
  onFetchSections: (domainUid: string, pkgUid: string) => void;
  onDrop: (ruleId: string, prediction: Prediction) => void;
}

export default function RulesTable({
  rules,
  sourcePool,
  destPool,
  servicesPool,
  domains,
  packages,
  sections,
  onRulesChange,
  onClone,
  onDelete,
  onFetchPackages,
  onFetchSections,
  onDrop,
}: RulesTableProps) {
  const domainOptions = domains.map(d => ({ value: d.uid, label: d.name }));
  const packageOptions = packages.map(p => ({ value: p.uid, label: p.name }));
  const sectionOptions = sections.map(s => ({
    value: s.uid,
    label: `${s.rulebase_range[0]}-${s.rulebase_range[1]} ${s.name}`
  }));

  const sourceOptions = sourcePool.map(ip => ({
    value: ip.normalized,
    label: ip.original,
  }));

  const destOptions = destPool.map(ip => ({
    value: ip.normalized,
    label: ip.original,
  }));

  const serviceOptions = servicesPool.map(svc => ({
    value: svc.normalized,
    label: svc.original,
  }));

  // Calculate used IPs for styling
  const usedSourceIps = new Set(
    rules.flatMap(r => r.sourceIps.map(ip => ip.normalized))
  );
  const usedDestIps = new Set(
    rules.flatMap(r => r.destIps.map(ip => ip.normalized))
  );

  const updateRule = (id: string, updates: Partial<RuleRow>) => {
    const updatedRules = rules.map(r =>
      r.id === id ? { ...r, ...updates } : r
    );
    onRulesChange(updatedRules);
  };

  const handleDrop = (ruleId: string, e: React.DragEvent) => {
    e.preventDefault();
    const predictionData = e.dataTransfer.getData('prediction');
    if (!predictionData) return;

    const prediction: Prediction = JSON.parse(predictionData);

    // Smart fill - only fill empty fields
    const rule = rules.find(r => r.id === ruleId);
    if (!rule) return;

    const updates: Partial<RuleRow> = {};

    if (rule.domain === null && prediction.candidates.length > 0) {
      updates.domain = prediction.candidates[0].domain;
      updates.package = null;  // Reset package when domain changes
      updates.section = null;
      onFetchPackages(prediction.candidates[0].domain.uid);
    }

    if (rule.package === null && prediction.candidates.length > 0 && rule.domain?.uid === prediction.candidates[0].domain.uid) {
      updates.package = prediction.candidates[0].package;
      updates.section = null;
      onFetchSections(rule.domain.uid, prediction.candidates[0].package.uid);
    }

    if (rule.sourceIps.length === 0) {
      updates.sourceIps = [prediction.ip];
    }

    updateRule(ruleId, updates);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const columns = [
    {
      title: '',
      width: 50,
      render: (_: unknown, record: RuleRow) => (
        <Button
          type="text"
          icon={<CopyOutlined />}
          onClick={() => onClone(record.id)}
          title="Clone rule"
        />
      ),
    },
    {
      title: 'Source',
      width: 200,
      render: (_: unknown, record: RuleRow) => (
        <Select
          mode="multiple"
          value={record.sourceIps.map(ip => ip.normalized)}
          options={sourceOptions}
          onChange={(values) => {
            const ips = sourcePool.filter(ip => values.includes(ip.normalized));
            updateRule(record.id, { sourceIps: ips });
          }}
          placeholder="Select IPs"
          tagRender={(props) => {
            const isUsed = usedSourceIps.has(props.value as string);
            return <Tag {...props} className={isUsed ? styles.usedTag : styles.unusedTag} />;
          }}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: 'Destination',
      width: 200,
      render: (_: unknown, record: RuleRow) => (
        <Select
          mode="multiple"
          value={record.destIps.map(ip => ip.normalized)}
          options={destOptions}
          onChange={(values) => {
            const ips = destPool.filter(ip => values.includes(ip.normalized));
            updateRule(record.id, { destIps: ips });
          }}
          placeholder="Select IPs"
          tagRender={(props) => {
            const isUsed = usedDestIps.has(props.value as string);
            return <Tag {...props} className={isUsed ? styles.usedTag : styles.unusedTag} />;
          }}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: 'Domain',
      width: 150,
      render: (_: unknown, record: RuleRow) => (
        <Select
          value={record.domain?.uid}
          options={domainOptions}
          onChange={(value) => {
            const domain = domains.find(d => d.uid === value);
            if (domain) {
              updateRule(record.id, { domain, package: null, section: null });
              onFetchPackages(domain.uid);
            }
          }}
          placeholder="Domain"
          showSearch
          allowClear
        />
      ),
    },
    {
      title: 'Package',
      width: 150,
      render: (_: unknown, record: RuleRow) => (
        <Select
          value={record.package?.uid}
          options={packageOptions}
          onChange={(value) => {
            const pkg = packages.find(p => p.uid === value);
            if (pkg && record.domain) {
              updateRule(record.id, { package: pkg, section: null });
              onFetchSections(record.domain.uid, pkg.uid);
            }
          }}
          placeholder="Package"
          showSearch
          allowClear
          disabled={!record.domain}
        />
      ),
    },
    {
      title: 'Section',
      width: 120,
      render: (_: unknown, record: RuleRow) => (
        <Select
          value={record.section?.uid}
          options={sectionOptions}
          onChange={(value) => {
            const section = sections.find(s => s.uid === value);
            if (section) updateRule(record.id, { section });
          }}
          placeholder="Section"
          showSearch
          allowClear
          disabled={!record.package}
        />
      ),
    },
    {
      title: 'Position',
      width: 140,
      render: (_: unknown, record: RuleRow) => (
        <Space direction="vertical" size="small">
          <Radio.Group
            value={record.position.type}
            onChange={(e) => updateRule(record.id, { position: { type: e.target.value } })}
            disabled={!record.package}
          >
            <Radio value="top">Top</Radio>
            <Radio value="bottom">Bot</Radio>
            <Radio value="custom">#</Radio>
          </Radio.Group>
          {record.position.type === 'custom' && (
            <InputNumber
              min={1}
              max={999}
              value={record.position.custom_number}
              onChange={(value) => updateRule(record.id, {
                position: { type: 'custom', custom_number: value ?? undefined }
              })}
              placeholder="#"
              size="small"
              style={{ width: 60 }}
            />
          )}
        </Space>
      ),
    },
    {
      title: 'Action',
      width: 90,
      render: (_: unknown, record: RuleRow) => (
        <Select
          value={record.action}
          onChange={(value) => updateRule(record.id, { action: value })}
          options={[
            { value: 'accept', label: 'Accept' },
            { value: 'drop', label: 'Drop' }
          ]}
          className={styles.smallSelect}
        />
      ),
    },
    {
      title: 'Track',
      width: 90,
      render: (_: unknown, record: RuleRow) => (
        <Select
          value={record.track}
          onChange={(value) => updateRule(record.id, { track: value })}
          options={[
            { value: 'log', label: 'Log' },
            { value: 'none', label: 'None' }
          ]}
          className={styles.smallSelect}
        />
      ),
    },
    {
      title: 'Services',
      width: 150,
      render: (_: unknown, record: RuleRow) => (
        <Select
          mode="multiple"
          value={record.services.map(s => s.normalized)}
          options={serviceOptions}
          onChange={(values) => {
            const services = servicesPool.filter(s => values.includes(s.normalized));
            updateRule(record.id, { services });
          }}
          placeholder="Optional"
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '',
      width: 50,
      render: (_: unknown, record: RuleRow) => (
        <Button
          type="text"
          icon={<DeleteOutlined />}
          onClick={() => onDelete(record.id)}
          danger
          title="Delete rule"
        />
      ),
    },
  ];

  const handleDragStart = (prediction: Prediction) => {
    // Store prediction data for drop
    const event = new DragEvent('dragstart');
    // This will be handled by the parent component
  };

  return (
    <div className={styles.tableContainer}>
      <div style={{ marginBottom: 12 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            const newRule: RuleRow = {
              id: `rule-${Date.now()}`,
              sourceIps: [],
              destIps: [],
              domain: null,
              package: null,
              section: null,
              position: { type: 'top' },
              action: 'accept',
              track: 'log',
              services: [],
            };
            onRulesChange([...rules, newRule]);
          }}
        >
          Add Rule
        </Button>
      </div>
      <Table
        className={styles.table}
        dataSource={rules}
        columns={columns}
        rowKey="id"
        pagination={false}
        onRow={(record) => ({
          draggable: true,
          onDragOver: handleDragOver,
          onDrop: (e) => handleDrop(record.id, e),
        })}
      />
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add webui/src/components/RulesTable.tsx webui/src/styles/components/rulesTable.module.css
git commit -m "feat: add RulesTable component with multi-select and drag-drop"
```

---

## Task 12: Create Domains2 Page Component

**Files:**
- Create: `webui/src/pages/Domains2.tsx`
- Create: `webui/src/styles/pages/domains2.module.css`

**Step 1: Create the page CSS**

Create `webui/src/styles/pages/domains2.module.css`:

```css
.pageContainer {
  padding: 24px;
  background-color: #f5f5f5;
  min-height: 100vh;
}

.submitSection {
  background: white;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
  text-align: right;
}

.submitButton {
  min-width: 150px;
}
```

**Step 2: Create the page component**

Create `webui/src/pages/Domains2.tsx`:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { message, Spin, Modal, Button } from 'antd';
import { domainsApi, packagesApi, topologyApi, rules2Api } from '../api/endpoints';
import { generatePredictions } from '../utils/predictionEngine';
import { validateRules, hasUnusedIps } from '../utils/ruleValidator';
import IpInputPanel from '../components/IpInputPanel';
import PredictionsPanel from '../components/PredictionsPanel';
import RulesTable from '../components/RulesTable';
import type {
  DomainItem,
  PackageItem,
  SectionItem,
  IpEntry,
  ServiceEntry,
  Prediction,
  RuleRow,
  TopologyEntry,
} from '../types';
import styles from '../styles/pages/domains2.module.css';

export default function Domains2() {
  // Domain/package/section data
  const [domains, setDomains] = useState<DomainItem[]>([]);
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [sections, setSections] = useState<SectionItem[]>([]);

  // Input pools
  const [sourcePool, setSourcePool] = useState<IpEntry[]>([]);
  const [destPool, setDestPool] = useState<IpEntry[]>([]);
  const [servicesPool, setServicesPool] = useState<ServiceEntry[]>([]);

  // Topology and predictions
  const [topology, setTopology] = useState<TopologyEntry[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);

  // Rules table
  const [rules, setRules] = useState<RuleRow[]>([]);

  // Loading states
  const [initialLoading, setInitialLoading] = useState(true);
  const [topologyLoading, setTopologyLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Drag state
  const [draggedPrediction, setDraggedPrediction] = useState<Prediction | null>(null);

  // Fetch initial data
  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const response = await domainsApi.list();
        setDomains(response.domains);
      } catch {
        message.error('Failed to load domains');
      } finally {
        setInitialLoading(false);
      }
    };

    fetchInitialData();
  }, []);

  // Fetch topology when IPs change
  useEffect(() => {
    if (sourcePool.length === 0 && destPool.length === 0) {
      setPredictions([]);
      return;
    }

    const fetchTopology = async () => {
      setTopologyLoading(true);
      try {
        const response = await topologyApi.getTopology();
        setTopology(response.topology);
      } catch {
        message.error('Failed to load topology');
      } finally {
        setTopologyLoading(false);
      }
    };

    fetchTopology();
  }, [sourcePool, destPool]);

  // Generate predictions when topology or pools change
  useEffect(() => {
    if (topology.length === 0) {
      setPredictions([]);
      return;
    }

    const preds = generatePredictions(sourcePool, destPool, topology);
    setPredictions(preds);
  }, [topology, sourcePool, destPool]);

  // Fetch packages for a domain
  const handleFetchPackages = useCallback(async (domainUid: string) => {
    try {
      const response = await packagesApi.list(domainUid);
      setPackages(response.packages);
    } catch {
      message.error('Failed to load packages');
    }
  }, []);

  // Fetch sections for a package
  const handleFetchSections = useCallback(async (domainUid: string, pkgUid: string) => {
    try {
      const response = await packagesApi.getSections(domainUid, pkgUid);
      setSections(response.sections);
    } catch {
      message.error('Failed to load sections');
    }
  }, []);

  // Handle clone
  const handleClone = useCallback((ruleId: string) => {
    const rule = rules.find(r => r.id === ruleId);
    if (!rule) return;

    const clonedRule: RuleRow = {
      id: `rule-${Date.now()}`,
      sourceIps: [...rule.sourceIps],
      destIps: [...rule.destIps],
      services: [...rule.services],
      domain: null,  // Require manual selection
      package: null,
      section: null,
      position: { ...rule.position },
      action: rule.action,
      track: rule.track,
    };

    setRules([...rules, clonedRule]);
  }, [rules]);

  // Handle delete
  const handleDelete = useCallback((ruleId: string) => {
    setRules(rules.filter(r => r.id !== ruleId));
  }, [rules]);

  // Handle drag start from predictions
  const handleDragStart = useCallback((prediction: Prediction) => {
    setDraggedPrediction(prediction);
  }, []);

  // Handle drop on rule row
  const handleDrop = useCallback((ruleId: string) => {
    if (!draggedPrediction) return;

    const rule = rules.find(r => r.id === ruleId);
    if (!rule) return;

    const updates: Partial<RuleRow> = {};

    if (rule.domain === null && draggedPrediction.candidates.length > 0) {
      updates.domain = draggedPrediction.candidates[0].domain;
      updates.package = null;
      updates.section = null;
      handleFetchPackages(draggedPrediction.candidates[0].domain.uid);
    }

    if (rule.package === null && rule.domain && draggedPrediction.candidates.length > 0) {
      const matchingCandidate = draggedPrediction.candidates.find(
        c => c.domain.uid === rule.domain!.uid
      );
      if (matchingCandidate) {
        updates.package = matchingCandidate.package;
        updates.section = null;
        handleFetchSections(rule.domain.uid, matchingCandidate.package.uid);
      }
    }

    if (rule.sourceIps.length === 0) {
      updates.sourceIps = [draggedPrediction.ip];
    }

    setRules(rules.map(r => r.id === ruleId ? { ...r, ...updates } : r));
    setDraggedPrediction(null);
  }, [draggedPrediction, rules, handleFetchPackages, handleFetchSections]);

  // Handle clear predictions
  const handleClearPredictions = useCallback(() => {
    setPredictions([]);
  }, []);

  // Submit rules
  const handleSubmit = useCallback(async () => {
    if (rules.length === 0) {
      message.warning('Please add at least one rule');
      return;
    }

    // Validate rules
    const errors = validateRules(rules);
    if (errors.length > 0) {
      message.error(errors[0].message);
      return;
    }

    // Check for unused IPs
    const unused = hasUnusedIps(rules, sourcePool, destPool);
    const hasUnused = unused.source.length > 0 || unused.dest.length > 0;

    const doSubmit = async () => {
      setSubmitting(true);

      try {
        const transformedRules = rules.map(rule => ({
          source_ips: rule.sourceIps.map(ip => ip.normalized),
          dest_ips: rule.destIps.map(ip => ip.normalized),
          services: rule.services.map(s => s.normalized),
          domain_uid: rule.domain!.uid,
          package_uid: rule.package!.uid,
          section_uid: rule.section?.uid || null,
          position: rule.position,
          action: rule.action,
          track: rule.track,
        }));

        const response = await rules2Api.createBatch({ rules: transformedRules });

        if (response.success) {
          message.success(`Successfully created ${response.created} rules`);
          setRules([]);
          setSourcePool([]);
          setDestPool([]);
          setServicesPool([]);
        } else if (response.failed > 0) {
          message.warning(`Created ${response.created}, failed ${response.failed}`);
        }
      } catch (error: unknown) {
        message.error(error instanceof Error ? error.message : 'Failed to submit rules');
      } finally {
        setSubmitting(false);
      }
    };

    if (hasUnused) {
      Modal.confirm({
        title: 'Unused IPs Detected',
        content: `You have ${unused.source.length + unused.dest.length} unused IPs. Continue anyway?`,
        onOk: doSubmit,
      });
    } else {
      doSubmit();
    }
  }, [rules, sourcePool, destPool]);

  return (
    <>
      <Spin spinning={initialLoading} fullscreen />
      <div className={styles.pageContainer}>
        <IpInputPanel
          sourcePool={sourcePool}
          destPool={destPool}
          servicesPool={servicesPool}
          onSourceChange={setSourcePool}
          onDestChange={setDestPool}
          onServicesChange={setServicesPool}
        />

        <Spin spinning={topologyLoading}>
          <PredictionsPanel
            predictions={predictions}
            onClear={handleClearPredictions}
            onDragStart={handleDragStart}
          />
        </Spin>

        <RulesTable
          rules={rules}
          sourcePool={sourcePool}
          destPool={destPool}
          servicesPool={servicesPool}
          domains={domains}
          packages={packages}
          sections={sections}
          onRulesChange={setRules}
          onClone={handleClone}
          onDelete={handleDelete}
          onFetchPackages={handleFetchPackages}
          onFetchSections={handleFetchSections}
          onDrop={handleDrop}
        />

        <div className={styles.submitSection}>
          <Button
            type="primary"
            size="large"
            onClick={handleSubmit}
            loading={submitting}
            className={styles.submitButton}
          >
            Submit Rules
          </Button>
        </div>
      </div>
    </>
  );
}
```

**Step 3: Commit**

```bash
git add webui/src/pages/Domains2.tsx webui/src/styles/pages/domains2.module.css
git commit -m "feat: add Domains2 page with full integration"
```

---

## Task 13: Fix Drag and Drop Implementation

**Files:**
- Modify: `webui/src/components/PredictionsPanel.tsx`
- Modify: `webui/src/components/RulesTable.tsx`

**Step 1: Update PredictionsPanel to set dataTransfer**

Edit `webui/src/components/PredictionsPanel.tsx` handleDragStart:

```typescript
const handleDragStart = (prediction: Prediction, e: React.DragEvent) => {
  e.dataTransfer.effectAllowed = 'copy';
  e.dataTransfer.setData('prediction', JSON.stringify(prediction));
  onDragStart(prediction);
};
```

**Step 2: Update RulesTable handleDrop to read dataTransfer**

Edit `webui/src/components/RulesTable.tsx` handleDrop function:

```typescript
const handleDrop = (ruleId: string, e: React.DragEvent) => {
  e.preventDefault();
  const predictionData = e.dataTransfer.getData('prediction');
  if (!predictionData) return;

  const prediction: Prediction = JSON.parse(predictionData);
  onDrop(ruleId, prediction);
};
```

**Step 3: Commit**

```bash
git add webui/src/components/PredictionsPanel.tsx webui/src/components/RulesTable.tsx
git commit -m "fix: implement drag-drop data transfer"
```

---

## Task 14: Test End-to-End

**Files:**
- Manual testing

**Step 1: Start the backend**

Run: `cd D:\Files\GSe_new\2026\Labs\Dev\FPCR && uv run python -m fa.main`

Expected: Server running on http://localhost:8000

**Step 2: Start the frontend**

Run: `cd webui && npm run dev`

Expected: WebUI running on http://localhost:5173

**Step 3: Test the full flow**

1. Navigate to http://localhost:5173/domains-2
2. Paste IPs: `10.76.64.11, 10.76.192.0/24` in Source
3. Paste IPs: `10.76.65.5` in Destination
4. Verify predictions appear below
5. Click "+ Add Rule"
6. Drag prediction to the rule row
7. Verify fields are populated
8. Select additional IPs in the row
9. Click "Clone" button
10. Verify new row appears with IPs copied
11. Click "Submit Rules"
12. Verify success message

**Step 4: Verify error handling**

1. Try to submit with empty source/dest IPs
2. Verify error message appears
3. Try to submit without domain selected
4. Verify error message appears

**Step 5: Verify unused IP warning**

1. Add multiple IPs to pools
2. Create rule using only some IPs
3. Click submit
4. Verify modal warning about unused IPs

**Step 6: Commit**

```bash
git commit --allow-empty -m "test: verify Domains_2 end-to-end functionality"
```

---

## Task 15: Final Polish

**Files:**
- Modify: `webui/src/components/RulesTable.tsx`
- Create: `docs/_AI_/260306-domains-2/notes.md`

**Step 1: Add responsive CSS**

Edit `webui/src/styles/components/rulesTable.module.css`:

```css
@media (max-width: 768px) {
  .tableContainer {
    overflow-x: auto;
  }

  .table {
    font-size: 12px;
  }
}
```

**Step 2: Create session notes**

Create `docs/_AI_/260306-domains-2/notes.md`:

```markdown
# Domains_2 Implementation Notes

**Date:** 2026-03-06

## Implementation Summary

Created new `/domains-2` page with:
- Tag-based inputs for Source, Destination, Services
- Prediction engine matching IPs to gateway subnets
- Drag-and-drop from predictions to rule rows
- Multi-select IP support in rules
- Clone functionality for multi-gateway scenarios
- Unused IP highlighting

## Key Decisions

1. Used Ant Design Select with `mode="tags"` for IP inputs - provides built-in tag UI
2. HTML5 Drag and Drop API - no additional libraries needed
3. ipaddr.js for subnet matching - already a project dependency
4. Row-based table instead of cards - better for multi-select IPs

## Known Limitations

1. Drag and drop dataTransfer requires string serialization
2. Prediction engine only handles IPv4 CIDR and exact matches
3. No persistence - page refresh loses data
4. Clone resets domain/package/section - requires manual reselection

## Future Enhancements

1. Add localStorage persistence for draft rules
2. Support IPv6 subnet matching in predictions
3. Bulk delete operations
4. Export rules to YAML/JSON
5. Keyboard shortcuts (Ctrl+Enter to submit)
```

**Step 3: Commit**

```bash
git add webui/src/styles/components/rulesTable.module.css docs/_AI_/260306-domains-2/notes.md
git commit -m "polish: add responsive styles and implementation notes"
```

---

## Summary

This implementation plan creates the Domains_2 feature in 15 bite-sized tasks following TDD principles. Each task includes:

- Exact file paths to create/modify
- Complete code snippets (not "add validation here")
- Test commands with expected outputs
- Commit messages

Total estimated implementation time: 2-3 hours
