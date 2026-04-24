# Hostname Display in Predictions - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display hostnames alongside IPs in the Predictions panel when a match is found in mock_data.yaml

**Architecture:** Backend parses hosts from mock_data.yaml, matches IPs to subnets, includes hosts in TopologyEntry. Frontend receives hosts in topology, passes through prediction engine, displays hostname next to IP.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, ipaddr.js, TypeScript, React, Vitest

---

## Task 1: Backend - Add hosts field to TopologyEntry model

**Files:**
- Modify: `src/fa/models.py`

**Step 1: Update TopologyEntry model**

```python
class TopologyEntry(BaseModel):
    domain: DomainItem
    package: PackageItem
    firewall: str
    subnets: list[str]
    hosts: list[str] = []  # Hostnames whose IPs match these subnets
```

**Step 2: Run type check**

Run: `uv run mypy src/fa/models.py`
Expected: PASS (no errors)

**Step 3: Run existing tests**

Run: `uv run pytest src/fa/tests/ -v`
Expected: PASS (existing tests still pass, default empty list)

**Step 4: Commit**

```bash
git add src/fa/models.py
git commit -m "feat: add hosts field to TopologyEntry model"
```

---

## Task 2: Backend - Write failing test for hostname population

**Files:**
- Modify: `src/fa/tests/test_mock_source.py`

**Step 1: Write failing test for single host in subnet**

Create test file if it doesn't exist, then add:

```python
import pytest
from fa.mock_source import MockDataSource
from fa.models import DomainItem, PackageItem


def test_topology_with_single_host_in_subnet(tmp_path):
    """Single host IP within subnet gets added to TopologyEntry.hosts"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24

hosts:
  USNY-CORP-WST-1: 10.76.64.10
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert topology[0].firewall == "USNY-CORP-FW-1"
    assert topology[0].hosts == ["USNY-CORP-WST-1"]


def test_topology_with_multiple_hosts_in_subnet(tmp_path):
    """Multiple hosts in same subnet all added to hosts array"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24

hosts:
  USNY-CORP-WST-1: 10.76.64.10
  USNY-CORP-WST-2: 10.76.64.11
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert set(topology[0].hosts) == {"USNY-CORP-WST-1", "USNY-CORP-WST-2"}


def test_topology_host_not_in_any_subnet(tmp_path):
    """Host IP not matching any subnet is not included"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24

hosts:
  DIFFERENT-HOST: 192.168.1.10
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert topology[0].hosts == []


def test_topology_with_no_hosts_section(tmp_path):
    """Missing hosts section returns empty hosts arrays"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert topology[0].hosts == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest src/fa/tests/test_mock_source.py -v`
Expected: FAIL (tests fail because get_topology() doesn't populate hosts yet)

**Step 3: Commit**

```bash
git add src/fa/tests/test_mock_source.py
git commit -m "test: add failing tests for hostname population in topology"
```

---

## Task 3: Backend - Implement hostname population in get_topology()

**Files:**
- Modify: `src/fa/mock_source.py`

**Step 1: Add helper method to check if IP is in subnet**

Add this method after `_ensure_uids()`:

```python
def _ip_in_subnet(self, ip: str, subnet: str) -> bool:
    """Check if an IP is within a subnet (CIDR or single IP)."""
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(ip)
        if '/' in subnet:
            network = ipaddress.ip_network(subnet, strict=False)
            return ip_obj in network
        else:
            return ip == subnet
    except ValueError:
        logger.warning(f"Invalid IP or subnet: ip={ip}, subnet={subnet}")
        return False
```

**Step 2: Update get_topology() to populate hosts**

Replace the existing `get_topology()` method with:

```python
def get_topology(self) -> list[TopologyEntry]:
    """Extract topology from mock data for prediction engine."""
    topology = []

    if not self.data or "domains" not in self.data:
        return topology

    # Build IP -> hostname mapping from hosts section
    hosts_map = self.data.get("hosts", {})

    for domain_name, domain_data in self.data["domains"].items():
        domain = DomainItem(
            name=domain_name,
            uid=self._get_domain_uid(domain_name)
        )

        if "policies" not in domain_data:
            continue

        for policy_name, policy_data in domain_data["policies"].items():
            package = PackageItem(
                name=policy_name,
                uid=self._get_policy_uid(domain_name, policy_name),
                access_layer="network"
            )

            if "firewalls" not in policy_data:
                continue

            for fw_name, fw_data in policy_data["firewalls"].items():
                subnets = fw_data.get("subnets", [])

                # Find hosts whose IPs are within this entry's subnets
                hosts = []
                for hostname, host_ip in hosts_map.items():
                    for subnet in subnets:
                        if self._ip_in_subnet(host_ip, subnet):
                            hosts.append(hostname)
                            break

                entry = TopologyEntry(
                    domain=domain,
                    package=package,
                    firewall=fw_name,
                    subnets=subnets,
                    hosts=hosts
                )
                topology.append(entry)

    return topology
```

**Step 3: Run tests to verify they pass**

Run: `uv run pytest src/fa/tests/test_mock_source.py -v`
Expected: PASS (all new tests pass)

**Step 4: Run all tests**

Run: `uv run pytest src/fa/tests/ -v`
Expected: PASS (no regressions)

**Step 5: Commit**

```bash
git add src/fa/mock_source.py
git commit -m "feat: populate hosts field in topology from mock_data.yaml"
```

---

## Task 4: Frontend - Add hosts to TopologyEntry type

**Files:**
- Modify: `webui/src/types/index.ts`

**Step 1: Update TopologyEntry interface**

Find the `TopologyEntry` interface and add the `hosts` field:

```typescript
export interface TopologyEntry {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnets: string[];
  hosts: string[];  // Hostnames matching this topology entry
}
```

**Step 2: Run type check**

Run: `cd webui && npm run type-check`
Expected: PASS (no errors)

**Step 3: Commit**

```bash
git add webui/src/types/index.ts
git commit -m "feat: add hosts field to TopologyEntry type"
```

---

## Task 5: Frontend - Update PredictionCandidate and Prediction types

**Files:**
- Modify: `webui/src/types/index.ts`

**Step 1: Update PredictionCandidate interface**

Add `hostnames` field:

```typescript
export interface PredictionCandidate {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnet: string;
  hostnames: string[];  // Copied from TopologyEntry.hosts
}
```

**Step 2: Update Prediction interface**

Add `hostname` field:

```typescript
export interface Prediction {
  ip: IpEntry;
  candidates: PredictionCandidate[];
  source: 'source' | 'dest';
  hostname: string | null;  // First matching hostname, or null
}
```

**Step 3: Commit**

```bash
git add webui/src/types/index.ts
git commit -m "feat: add hostname fields to Prediction types"
```

---

## Task 6: Frontend - Write failing test for hostname in predictions

**Files:**
- Modify: `webui/src/utils/__tests__/predictionEngine.test.ts`

**Step 1: Add failing tests for hostname handling**

Add these tests to the existing test file:

```typescript
describe('generatePredictions with hostnames', () => {
  const topologyWithHosts: TopologyEntry[] = [
    {
      domain: { name: 'AME_CORP', uid: '1' },
      package: { name: 'US-NY-CORP', uid: '2', access_layer: 'network' },
      firewall: 'USNY-CORP-FW-1',
      subnets: ['10.76.64.0/24'],
      hosts: ['USNY-CORP-WST-1', 'USNY-CORP-WST-2']
    }
  ];

  it('includes hostname when IP matches topology entry with hosts', () => {
    const sourcePool: IpEntry[] = [
      { original: '10.76.64.10', type: 'ipv4', normalized: '10.76.64.10' }
    ];
    const destPool: IpEntry[] = [];

    const predictions = generatePredictions(sourcePool, destPool, topologyWithHosts);

    expect(predictions).toHaveLength(1);
    expect(predictions[0].hostname).toBe('USNY-CORP-WST-1');
    expect(predictions[0].candidates[0].hostnames).toEqual(['USNY-CORP-WST-1', 'USNY-CORP-WST-2']);
  });

  it('returns null hostname when no hosts match', () => {
    const topologyWithoutHosts: TopologyEntry[] = [
      {
        domain: { name: 'AME_CORP', uid: '1' },
        package: { name: 'US-NY-CORP', uid: '2', access_layer: 'network' },
        firewall: 'USNY-CORP-FW-1',
        subnets: ['10.76.64.0/24'],
        hosts: []
      }
    ];

    const sourcePool: IpEntry[] = [
      { original: '10.76.64.10', type: 'ipv4', normalized: '10.76.64.10' }
    ];
    const destPool: IpEntry[] = [];

    const predictions = generatePredictions(sourcePool, destPool, topologyWithoutHosts);

    expect(predictions).toHaveLength(1);
    expect(predictions[0].hostname).toBeNull();
  });

  it('handles empty hosts array', () => {
    const predictions = generatePredictions([], [], topologyWithHosts);
    expect(predictions).toHaveLength(0);
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd webui && npm test -- predictionEngine.test.ts`
Expected: FAIL (tests fail because generatePredictions doesn't handle hostnames yet)

**Step 3: Commit**

```bash
git add webui/src/utils/__tests__/predictionEngine.test.ts
git commit -m "test: add failing tests for hostname in predictions"
```

---

## Task 7: Frontend - Implement hostname handling in predictionEngine

**Files:**
- Modify: `webui/src/utils/predictionEngine.ts`

**Step 1: Update generatePredictions to handle hostnames**

Replace the existing `generatePredictions()` function with:

```typescript
export function generatePredictions(
  sourcePool: IpEntry[],
  destPool: IpEntry[],
  topology: TopologyEntry[]
): Prediction[] {
  const predictions: Prediction[] = [];

  // Process source pool
  for (const ip of sourcePool) {
    const candidates: Prediction['candidates'] = [];

    for (const entry of topology) {
      if (ipMatchesSubnet(ip, entry.subnets)) {
        candidates.push({
          domain: entry.domain,
          package: entry.package,
          firewall: entry.firewall,
          subnet: entry.subnets.find(s => ipMatchesSubnet(ip, [s])) || '',
          hostnames: entry.hosts || [],
        });
      }
    }

    if (candidates.length > 0) {
      // Extract first hostname from any matching candidate
      const hostname = candidates.find(c => c.hostnames.length > 0)?.hostnames[0] || null;
      predictions.push({ ip, candidates, source: 'source', hostname });
    }
  }

  // Process dest pool
  for (const ip of destPool) {
    const candidates: Prediction['candidates'] = [];

    for (const entry of topology) {
      if (ipMatchesSubnet(ip, entry.subnets)) {
        candidates.push({
          domain: entry.domain,
          package: entry.package,
          firewall: entry.firewall,
          subnet: entry.subnets.find(s => ipMatchesSubnet(ip, [s])) || '',
          hostnames: entry.hosts || [],
        });
      }
    }

    if (candidates.length > 0) {
      // Extract first hostname from any matching candidate
      const hostname = candidates.find(c => c.hostnames.length > 0)?.hostnames[0] || null;
      predictions.push({ ip, candidates, source: 'dest', hostname });
    }
  }

  return predictions;
}
```

**Step 2: Run tests to verify they pass**

Run: `cd webui && npm test -- predictionEngine.test.ts`
Expected: PASS (all tests pass)

**Step 3: Run all frontend tests**

Run: `cd webui && npm test`
Expected: PASS (no regressions)

**Step 4: Commit**

```bash
git add webui/src/utils/predictionEngine.ts
git commit -m "feat: add hostname handling to prediction engine"
```

---

## Task 8: Frontend - Add CSS style for hostname text

**Files:**
- Modify: `webui/src/styles/components/predictionsPanel.module.css`

**Step 1: Add hostnameText style**

Add this to the CSS file:

```css
.hostnameText {
  color: var(--color-text-secondary);
  font-weight: normal;
  font-size: 0.9em;
  margin-left: 4px;
}
```

**Step 2: Commit**

```bash
git add webui/src/styles/components/predictionsPanel.module.css
git commit -m "style: add hostnameText style for predictions panel"
```

---

## Task 9: Frontend - Update PredictionsPanel to display hostname

**Files:**
- Modify: `webui/src/components/PredictionsPanel.tsx`

**Step 1: Import the CSS module**

Ensure the styles are imported (already should be):

```typescript
import styles from '../styles/components/predictionsPanel.module.css';
```

**Step 2: Update the prediction item rendering**

Find the prediction item rendering inside `renderPredictionColumn()` and update it:

```typescript
{preds.map((prediction, idx) => (
  <div
    key={idx}
    className={styles.predictionItem}
    draggable
    onDragStart={(e) => handleDragStart(prediction, e)}
  >
    <div>
      <span className={styles.ipText}>
        {prediction.ip.original}
        {prediction.hostname && (
          <span className={styles.hostnameText}>
            {' ('}{prediction.hostname}{')'}
          </span>
        )}
      </span>
      <span className={styles.candidatesText}>
        → {prediction.candidates.map(c =>
          `${c.domain.name} ${c.package.name}`
        ).join(' | ')}
      </span>
    </div>
    <HolderOutlined className={styles.dragHandle} />
  </div>
))}
```

**Step 3: Run type check**

Run: `cd webui && npm run type-check`
Expected: PASS

**Step 4: Commit**

```bash
git add webui/src/components/PredictionsPanel.tsx
git commit -m "feat: display hostname next to IP in predictions panel"
```

---

## Task 10: Integration test with actual mock_data.yaml

**Files:**
- Test: Integration test using existing mock_data.yaml

**Step 1: Start backend with mock data**

Run: `export MOCK_DATA=mock_data.yaml && uv run uvicorn src.fa.main:app --reload`
Expected: Server starts on port 8080

**Step 2: Start frontend**

Run: `cd webui && npm run dev`
Expected: Vite dev server starts

**Step 3: Test in browser**

1. Open browser to http://localhost:8080
2. Navigate to Domains page
3. Add IP `10.76.64.10` to source pool
4. Verify prediction displays: `10.76.64.10 (USNY-CORP-WST-1) → AME_CORP US-NY-CORP`

**Step 4: Test edge cases**

1. Add IP `10.76.67.10` - should show: `10.76.67.10 (AMUS-WEB-SRV) → ...`
2. Add IP `1.2.3.4` - should show: `1.2.3.4 → ...` (no hostname)

**Step 5: Stop servers**

Press Ctrl+C in both terminals

**Step 6: Commit final integration notes**

```bash
git add docs/plans/260307-hostname-in-predictions-implementation.md
git commit -m "docs: complete implementation plan for hostname display"
```

---

## Verification Checklist

After completing all tasks:

- [ ] All backend tests pass: `uv run pytest src/fa/tests/ -v`
- [ ] All frontend tests pass: `cd webui && npm test`
- [ ] Type checks pass: `uv run mypy src/` and `cd webui && npm run type-check`
- [ ] Manual test with mock_data.yaml shows hostnames correctly
- [ ] Edge cases handled (no hostname, multiple hosts, invalid IPs)
- [ ] No console errors in browser
- [ ] Display format matches: `10.76.64.10 (USNY-CORP-WST-1) → AME_CORP US-NY-CORP`
