# Domains Rule Cards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the `/domains` page from a sequential form to a card-based interface for creating firewall rules across multiple domains.

**Architecture:** Single-page React application using Ant Design components. IP pools defined in a collapsible panel, cards displayed horizontally with draggable repositioning. Each card generates two rules (source and destination) with independent domain/package selections.

**Tech Stack:** React 19, TypeScript 5.6, Ant Design 6.1, Vite 6, ipaddr.js for IP validation

---

## Task 1: Add IP Validation Dependency

**Files:**

- Modify: `webui/package.json`

**Step 1: Add ipaddr.js dependency**

Run:

```bash
cd webui && npm install ipaddr.js
```

Expected: package.json updated with ipaddr.js dependency

**Step 2: Verify installation**

Run:

```bash
cd webui && npm list ipaddr.js
```

Expected: ipaddr.js@2.x.x listed

**Step 3: Commit**

```bash
git add webui/package.json webui/package-lock.json
git commit -m "feat: add ipaddr.js for IP validation"
```

---

## Task 2: Define New TypeScript Types

**Files:**

- Modify: `webui/src/types/index.ts`
- Test: N/A (types only)

**Step 1: Add IP entry and pool types**

Add to `webui/src/types/index.ts` after existing types:

```typescript
export interface IpEntry {
  original: string;
  type: 'ipv4' | 'ipv6' | 'ipv4-cidr' | 'ipv6-cidr' | 'fqdn' | 'range' | 'any';
  normalized: string;
}

export interface IpPool {
  raw: string;
  validated: IpEntry[];
  invalid: string[];
  errors: string[];
}

export interface RuleLine {
  ip: IpEntry | null;
  domain: DomainItem | null;
  package: PackageItem | null;
  section: SectionItem | null;
  position: PositionChoice;
  action: 'accept' | 'drop';
  track: 'log' | 'none';
}

export interface RuleCard {
  id: string;
  source: RuleLine;
  destination: RuleLine;
  samePackage: boolean;
}

export interface CreateRuleRequest {
  source: {
    domain_uid: string;
    package_uid: string;
    section_uid: string | null;
    position: PositionChoice;
    action: 'accept' | 'drop';
    track: 'log' | 'none';
    source_ip: string;
    dest_ip: string;
  };
  destination: {
    domain_uid: string;
    package_uid: string;
    section_uid: string | null;
    position: PositionChoice;
    action: 'accept' | 'drop';
    track: 'log' | 'none';
    source_ip: string;
    dest_ip: string;
  };
}

export interface BatchRulesResponse {
  success: boolean;
  created: number;
  failed: number;
  errors: Array<{ rule_id: string; message: string }>;
}
```

**Step 2: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 3: Commit**

```bash
git add webui/src/types/index.ts
git commit -m "feat: add types for rule cards and IP pools"
```

---

## Task 3: Create IP Validation Utility

**Files:**

- Create: `webui/src/utils/ipValidator.ts`
- Test: N/A (utility tested through component integration)

**Step 1: Create IP validator utility**

Create `webui/src/utils/ipValidator.ts`:

```typescript
import ipaddr from 'ipaddr.js';
import type { IpEntry } from '../types';

const SEPARATORS = /[\n,;\s\t]+/;

export function validateIpInput(input: string): IpEntry[] {
  if (!input.trim()) {
    return [];
  }

  const entries: IpEntry[] = [];
  const rawEntries = input.split(SEPARATORS).filter(e => e.trim());

  for (const raw of rawEntries) {
    const entry = parseIpEntry(raw.trim());
    if (entry) {
      entries.push(entry);
    }
  }

  return entries;
}

function parseIpEntry(input: string): IpEntry | null {
  const lower = input.toLowerCase();

  // Handle 'any'
  if (lower === 'any') {
    return { original: input, type: 'any', normalized: 'any' };
  }

  // Handle FQDN with wildcard
  if (lower.startsWith('*.')) {
    return { original: input, type: 'fqdn', normalized: input };
  }

  // Handle FQDN
  if (/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$/i.test(input)) {
    return { original: input, type: 'fqdn', normalized: input };
  }

  // Handle range (x.x.x.x-y.y.y.y)
  if (input.includes('-')) {
    const parts = input.split('-');
    if (parts.length === 2) {
      try {
        ipaddr.parse(parts[0].trim());
        ipaddr.parse(parts[1].trim());
        return { original: input, type: 'range', normalized: input };
      } catch {
        return null;
      }
    }
  }

  // Handle CIDR
  if (input.includes('/')) {
    try {
      const addr = ipaddr.parseCIDR(input);
      return {
        original: input,
        type: addr[0].kind() === 'ipv4' ? 'ipv4-cidr' : 'ipv6-cidr',
        normalized: input
      };
    } catch {
      return null;
    }
  }

  // Handle plain IP
  try {
    const addr = ipaddr.parse(input);
    return {
      original: input,
      type: addr.kind() === 'ipv4' ? 'ipv4' : 'ipv6',
      normalized: input
    };
  } catch {
    return null;
  }
}

export function findDuplicates(entries: IpEntry[]): string[] {
  const seen = new Set<string>();
  const duplicates: string[] = [];

  for (const entry of entries) {
    const normalized = entry.normalized.toLowerCase();
    if (seen.has(normalized)) {
      if (!duplicates.includes(normalized)) {
        duplicates.push(normalized);
      }
    } else {
      seen.add(normalized);
    }
  }

  return duplicates;
}

export function getFirstUnusedIp(pool: IpEntry[], usedIps: Set<string>): IpEntry | null {
  for (const entry of pool) {
    if (!usedIps.has(entry.normalized.toLowerCase())) {
      return entry;
    }
  }
  return null;
}
```

**Step 2: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 3: Commit**

```bash
git add webui/src/utils/ipValidator.ts
git commit -m "feat: add IP validation utility"
```

---

## Task 4: Create IP Pools Panel Component

**Files:**

- Create: `webui/src/components/IpPoolsPanel.tsx`
- Create: `webui/src/styles/components/ipPoolsPanel.module.css`

**Step 1: Create IpPoolsPanel component**

Create `webui/src/components/IpPoolsPanel.tsx`:

```typescript
import { Collapse, Input, Badge, Alert } from 'antd';
import { useState, useEffect } from 'react';
import { debounce } from '@ant-design/utils';
import { validateIpInput, findDuplicates } from '../utils/ipValidator';
import type { IpPool, IpEntry } from '../types';
import styles from '../styles/components/ipPoolsPanel.module.css';

const { TextArea } = Input;

interface IpPoolsPanelProps {
  sourcePool: IpPool;
  destPool: IpPool;
  services: string;
  onSourceChange: (pool: IpPool) => void;
  onDestChange: (pool: IpPool) => void;
  onServicesChange: (services: string) => void;
}

export default function IpPoolsPanel({
  sourcePool,
  destPool,
  services,
  onSourceChange,
  onDestChange,
  onServicesChange,
}: IpPoolsPanelProps) {
  const [sourceInput, setSourceInput] = useState(sourcePool.raw);
  const [destInput, setDestInput] = useState(destPool.raw);
  const [servicesInput, setServicesInput] = useState(services);

  const validateAndSetSource = debounce((value: string) => {
    const validated = validateIpInput(value);
    const invalid = extractInvalid(value, validated);
    const duplicates = findDuplicates(validated);
    const errors: string[] = [];

    if (invalid.length > 0) {
      errors.push(`${invalid.length} invalid entries`);
    }
    if (duplicates.length > 0) {
      errors.push(`${duplicates.length} duplicates`);
    }

    onSourceChange({
      raw: value,
      validated,
      invalid,
      errors,
    });
  }, 500);

  const validateAndSetDest = debounce((value: string) => {
    const validated = validateIpInput(value);
    const invalid = extractInvalid(value, validated);
    const duplicates = findDuplicates(validated);
    const errors: string[] = [];

    if (invalid.length > 0) {
      errors.push(`${invalid.length} invalid entries`);
    }
    if (duplicates.length > 0) {
      errors.push(`${duplicates.length} duplicates`);
    }

    onDestChange({
      raw: value,
      validated,
      invalid,
      errors,
    });
  }, 500);

  function extractInvalid(raw: string, validated: IpEntry[]): string[] {
    const validatedSet = new Set(validated.map(v => v.original));
    const allEntries = raw.split(/[\n,;\s\t]+/).filter(e => e.trim());
    return allEntries.filter(e => !validatedSet.has(e.trim()));
  }

  const panelHeader = (
    <div className={styles.header}>
      <span>IP Pools</span>
      <Badge count={`Source: ${sourcePool.validated.length}, Dest: ${destPool.validated.length}`} />
    </div>
  );

  return (
    <Collapse
      defaultActiveKey={['pools']}
      className={styles.panel}
      items={[
        {
          key: 'pools',
          label: panelHeader,
          children: (
            <div className={styles.content}>
              <div className={styles.inputGroup}>
                <label className={styles.label}>Source IPs:</label>
                <TextArea
                  value={sourceInput}
                  onChange={(e) => {
                    setSourceInput(e.target.value);
                    validateAndSetSource(e.target.value);
                  }}
                  placeholder="Paste source IPs (one per line, comma, semicolon, or space separated)..."
                  className={sourcePool.errors.length > 0 ? styles.textareaError : styles.textarea}
                  rows={4}
                />
                {sourcePool.errors.length > 0 && (
                  <Alert
                    type="warning"
                    message={sourcePool.errors.join(', ')}
                    showIcon
                    className={styles.alert}
                  />
                )}
                {sourcePool.invalid.length > 0 && (
                  <Alert
                    type="error"
                    message={`Invalid entries: ${sourcePool.invalid.slice(0, 3).join(', ')}${sourcePool.invalid.length > 3 ? '...' : ''}`}
                    showIcon
                    className={styles.alert}
                  />
                )}
              </div>

              <div className={styles.inputGroup}>
                <label className={styles.label}>Destination IPs:</label>
                <TextArea
                  value={destInput}
                  onChange={(e) => {
                    setDestInput(e.target.value);
                    validateAndSetDest(e.target.value);
                  }}
                  placeholder="Paste destination IPs (one per line, comma, semicolon, or space separated)..."
                  className={destPool.errors.length > 0 ? styles.textareaError : styles.textarea}
                  rows={4}
                />
                {destPool.errors.length > 0 && (
                  <Alert
                    type="warning"
                    message={destPool.errors.join(', ')}
                    showIcon
                    className={styles.alert}
                  />
                )}
                {destPool.invalid.length > 0 && (
                  <Alert
                    type="error"
                    message={`Invalid entries: ${destPool.invalid.slice(0, 3).join(', ')}${destPool.invalid.length > 3 ? '...' : ''}`}
                    showIcon
                    className={styles.alert}
                  />
                )}
              </div>

              <div className={styles.inputGroup}>
                <label className={styles.label}>Services (optional):</label>
                <TextArea
                  value={servicesInput}
                  onChange={(e) => onServicesChange(e.target.value)}
                  placeholder="Paste services here (no processing yet)..."
                  className={styles.textarea}
                  rows={2}
                />
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}
```

**Step 2: Create CSS module**

Create `webui/src/styles/components/ipPoolsPanel.module.css`:

```css
.panel {
  margin-bottom: 16px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.inputGroup {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.label {
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
}

.textarea {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.textareaError {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  border-color: #ff4d4f !important;
}

.alert {
  margin-top: 4px;
}
```

**Step 3: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 4: Commit**

```bash
git add webui/src/components/IpPoolsPanel.tsx webui/src/styles/components/ipPoolsPanel.module.css
git commit -m "feat: add IP pools panel component"
```

---

## Task 5: Create Rule Card Component

**Files:**

- Create: `webui/src/components/RuleCard.tsx`
- Create: `webui/src/styles/components/ruleCard.module.css`

**Step 1: Create RuleCard component**

Create `webui/src/components/RuleCard.tsx`:

```typescript
import { Card, Select, Radio, InputNumber, Checkbox, Button, Space } from 'antd';
import { UpOutlined, DownOutlined, DeleteOutlined } from '@ant-design/icons';
import type { SelectProps } from 'antd/es/select';
import type { RuleCard as RuleCardType, RuleLine, IpEntry, DomainItem, PackageItem, SectionItem, PositionChoice } from '../types';
import styles from '../styles/components/ruleCard.module.css';

interface RuleCardProps {
  card: RuleCardType;
  sourcePool: IpEntry[];
  destPool: IpEntry[];
  domains: DomainItem[];
  packages: PackageItem[];
  sections: SectionItem[];
  selected: boolean;
  onSelect: () => void;
  onUpdate: (card: RuleCardType) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  onFetchPackages: (domainUid: string) => void;
  onFetchSections: (domainUid: string, pkgUid: string) => void;
}

export default function RuleCard({
  card,
  sourcePool,
  destPool,
  domains,
  packages,
  sections,
  selected,
  onSelect,
  onUpdate,
  onMoveUp,
  onMoveDown,
  onDelete,
  onFetchPackages,
  onFetchSections,
}: RuleCardProps) {
  const domainOptions: SelectProps['options'] = domains.map(d => ({ value: d.uid, label: d.name }));

  function updateLine(line: 'source' | 'destination', updates: Partial<RuleLine>) {
    const updated = { ...card[line], ...updates };
    const updatedCard = { ...card, [line]: updated };

    // If samePackage is checked, sync destination to source
    if (card.samePackage && line === 'source') {
      updatedCard.destination = { ...updated };
    }

    onUpdate(updatedCard);
  }

  function handleSamePackageChange(checked: boolean) {
    const updated = { ...card, samePackage: checked };

    if (checked) {
      // Copy source to destination
      updated.destination = { ...card.source };
    }

    onUpdate(updated);
  }

  function renderLine(line: RuleLine, lineKey: 'source' | 'destination', pool: IpEntry[], label: string) {
    const isDestination = lineKey === 'destination';
    const isDisabled = isDestination && card.samePackage;

    const packageOptions: SelectProps['options'] = packages
      .filter(p => !line.domain || p.domain_uid === line.domain?.uid)
      .map(p => ({ value: p.uid, label: p.name }));

    const sectionOptions: SelectProps['options'] = sections.map(s => ({
      value: s.uid,
      label: `${s.rulebase_range[0]}-${s.rulebase_range[1]} ${s.name}`
    }));

    const ipOptions: SelectProps['options'] = pool.map(ip => ({
      value: ip.normalized,
      label: ip.original
    }));

    return (
      <div className={styles.line}>
        <span className={styles.lineLabel}>{label}:</span>
        <Space size="small" className={styles.lineFields}>
          <Select
            value={line.ip?.normalized}
            onChange={(value) => {
              const ip = pool.find(i => i.normalized === value);
              if (ip) updateLine(lineKey, { ip });
            }}
            options={ipOptions}
            placeholder="Select IP"
            className={styles.select}
            disabled={isDisabled}
            showSearch
            allowClear
          />
          <Select
            value={line.domain?.uid}
            onChange={(value) => {
              const domain = domains.find(d => d.uid === value);
              if (domain) {
                updateLine(lineKey, { domain, package: null, section: null });
                onFetchPackages(domain.uid);
              }
            }}
            options={domainOptions}
            placeholder="Domain"
            className={styles.select}
            disabled={isDisabled}
            showSearch
          />
          <Select
            value={line.package?.uid}
            onChange={(value) => {
              const pkg = packages.find(p => p.uid === value);
              if (pkg && line.domain) {
                updateLine(lineKey, { package: pkg, section: null });
                onFetchSections(line.domain.uid, pkg.uid);
              }
            }}
            options={packageOptions}
            placeholder="Package"
            className={styles.select}
            disabled={isDisabled || !line.domain}
            showSearch
          />
          <Select
            value={line.section?.uid}
            onChange={(value) => {
              const section = sections.find(s => s.uid === value);
              if (section) updateLine(lineKey, { section });
            }}
            options={sectionOptions}
            placeholder="Section"
            className={styles.select}
            disabled={isDisabled || !line.package}
            showSearch
            allowClear
          />
          <Radio.Group
            value={line.position.type}
            onChange={(e) => updateLine(lineKey, { position: { type: e.target.value } })}
            disabled={isDisabled || !line.package}
          >
            <Radio value="top">Top</Radio>
            <Radio value="bottom">Bottom</Radio>
            <Radio value="custom">#</Radio>
          </Radio.Group>
          {line.position.type === 'custom' && (
            <InputNumber
              min={1}
              max={999}
              value={line.position.custom_number}
              onChange={(value) => updateLine(lineKey, { position: { type: 'custom', custom_number: value } })}
              placeholder="#"
              size="small"
              className={styles.customInput}
              disabled={isDisabled}
            />
          )}
          <Select
            value={line.action}
            onChange={(value) => updateLine(lineKey, { action: value })}
            options={[{ value: 'accept', label: 'Accept' }, { value: 'drop', label: 'Drop' }]}
            className={styles.smallSelect}
            disabled={isDisabled}
          />
          <Select
            value={line.track}
            onChange={(value) => updateLine(lineKey, { track: value })}
            options={[{ value: 'log', label: 'Log' }, { value: 'none', label: 'None' }]}
            className={styles.smallSelect}
            disabled={isDisabled}
          />
        </Space>
      </div>
    );
  }

  return (
    <Card
      className={`${styles.card} ${selected ? styles.selected : ''}`}
      onClick={onSelect}
      bodyStyle={{ padding: '12px' }}
    >
      <div className={styles.header}>
        <Space>
          <Button
            type="text"
            icon={<UpOutlined />}
            onClick={(e) => { e.stopPropagation(); onMoveUp(); }}
            size="small"
          />
          <Button
            type="text"
            icon={<DownOutlined />}
            onClick={(e) => { e.stopPropagation(); onMoveDown(); }}
            size="small"
          />
          <Button
            type="text"
            icon={<DeleteOutlined />}
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            size="small"
            danger
          />
        </Space>
      </div>

      {renderLine(card.source, 'source', sourcePool, 'Source')}

      <Checkbox
        checked={card.samePackage}
        onChange={(e) => handleSamePackageChange(e.target.checked)}
        className={styles.samePackageCheckbox}
      >
        Same package for destination
      </Checkbox>

      {renderLine(card.destination, 'destination', destPool, 'Destination')}
    </Card>
  );
}
```

**Step 2: Create CSS module**

Create `webui/src/styles/components/ruleCard.module.css`:

```css
.card {
  min-width: 400px;
  max-width: 400px;
  border: 1px solid #d9d9d9;
  cursor: pointer;
  transition: border-color 0.3s;
}

.card:hover {
  border-color: #1677ff;
}

.selected {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.2);
}

.header {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.lineLabel {
  font-weight: 500;
  min-width: 70px;
  color: rgba(0, 0, 0, 0.65);
}

.lineFields {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.select {
  min-width: 100px;
}

.smallSelect {
  min-width: 70px;
}

.customInput {
  width: 60px;
}

.samePackageCheckbox {
  margin: 8px 0;
  font-size: 12px;
}
```

**Step 3: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 4: Commit**

```bash
git add webui/src/components/RuleCard.tsx webui/src/styles/components/ruleCard.module.css
git commit -m "feat: add rule card component"
```

---

## Task 6: Create Cards Container Component

**Files:**

- Create: `webui/src/components/CardsContainer.tsx`
- Create: `webui/src/styles/components/cardsContainer.module.css`

**Step 1: Create CardsContainer component**

Create `webui/src/components/CardsContainer.tsx`:

```typescript
import { Button, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useEffect, useCallback } from 'react';
import RuleCard from './RuleCard';
import type { RuleCard as RuleCardType, IpEntry, DomainItem, PackageItem, SectionItem } from '../types';
import styles from '../styles/components/cardsContainer.module.css';

interface CardsContainerProps {
  cards: RuleCardType[];
  sourcePool: IpEntry[];
  destPool: IpEntry[];
  domains: DomainItem[];
  packages: PackageItem[];
  sections: SectionItem[];
  selectedCardId: string | null;
  onCardsChange: (cards: RuleCardType[]) => void;
  onSelectedCardIdChange: (id: string | null) => void;
  onFetchPackages: (domainUid: string) => void;
  onFetchSections: (domainUid: string, pkgUid: string) => void;
}

export default function CardsContainer({
  cards,
  sourcePool,
  destPool,
  domains,
  packages,
  sections,
  selectedCardId,
  onCardsChange,
  onSelectedCardIdChange,
  onFetchPackages,
  onFetchSections,
}: CardsContainerProps) {
  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (selectedCardId === null) return;

    const currentIndex = cards.findIndex(c => c.id === selectedCardId);
    if (currentIndex === -1) return;

    if (e.ctrlKey && e.key === 'ArrowUp') {
      e.preventDefault();
      moveCard(currentIndex, currentIndex - 1);
    } else if (e.ctrlKey && e.key === 'ArrowDown') {
      e.preventDefault();
      moveCard(currentIndex, currentIndex + 1);
    } else if (e.key === 'Delete') {
      e.preventDefault();
      deleteCard(currentIndex);
    } else if (e.key === 'Tab') {
      e.preventDefault();
      const nextIndex = e.shiftKey
        ? (currentIndex - 1 + cards.length) % cards.length
        : (currentIndex + 1) % cards.length;
      onSelectedCardIdChange(cards[nextIndex].id);
    }
  }, [selectedCardId, cards]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  function addCard() {
    const usedSourceIps = new Set(cards.map(c => c.source.ip?.normalized.toLowerCase()).filter(Boolean));
    const usedDestIps = new Set(cards.map(c => c.destination.ip?.normalized.toLowerCase()).filter(Boolean));

    // Find first unused IPs
    const firstUnusedSource = sourcePool.find(ip => !usedSourceIps.has(ip.normalized.toLowerCase()));
    const firstUnusedDest = destPool.find(ip => !usedDestIps.has(ip.normalized.toLowerCase()));

    const newCard: RuleCardType = {
      id: Date.now().toString() + Math.random().toString(36).substr(2, 5),
      source: {
        ip: firstUnusedSource || null,
        domain: null,
        package: null,
        section: null,
        position: { type: 'bottom' },
        action: 'accept',
        track: 'log',
      },
      destination: {
        ip: firstUnusedDest || null,
        domain: null,
        package: null,
        section: null,
        position: { type: 'bottom' },
        action: 'accept',
        track: 'log',
      },
      samePackage: false,
    };

    onCardsChange([...cards, newCard]);
    onSelectedCardIdChange(newCard.id);
  }

  function updateCard(index: number, updated: RuleCardType) {
    const newCards = [...cards];
    newCards[index] = updated;
    onCardsChange(newCards);
  }

  function moveCard(fromIndex: number, toIndex: number) {
    if (toIndex < 0 || toIndex >= cards.length) return;

    const newCards = [...cards];
    const [moved] = newCards.splice(fromIndex, 1);
    newCards.splice(toIndex, 0, moved);
    onCardsChange(newCards);
  }

  function deleteCard(index: number) {
    const newCards = cards.filter((_, i) => i !== index);
    onCardsChange(newCards);

    if (newCards.length === 0) {
      onSelectedCardIdChange(null);
    } else if (selectedCardId === cards[index].id) {
      onSelectedCardIdChange(newCards[Math.min(index, newCards.length - 1)].id);
    }
  }

  return (
    <div className={styles.container}>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={addCard}
        className={styles.addButton}
        disabled={sourcePool.length === 0 || destPool.length === 0}
      >
        Add Card
      </Button>

      {cards.length === 0 ? (
        <Empty
          description="No cards yet. Add IPs to pools and click Add Card."
          className={styles.empty}
        />
      ) : (
        <div className={styles.cardsWrapper}>
          <div className={styles.cardsScroll}>
            {cards.map((card, index) => (
              <RuleCard
                key={card.id}
                card={card}
                sourcePool={sourcePool}
                destPool={destPool}
                domains={domains}
                packages={packages}
                sections={sections}
                selected={selectedCardId === card.id}
                onSelect={() => onSelectedCardIdChange(card.id)}
                onUpdate={(updated) => updateCard(index, updated)}
                onMoveUp={() => moveCard(index, index - 1)}
                onMoveDown={() => moveCard(index, index + 1)}
                onDelete={() => deleteCard(index)}
                onFetchPackages={onFetchPackages}
                onFetchSections={onFetchSections}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Create CSS module**

Create `webui/src/styles/components/cardsContainer.module.css`:

```css
.container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.addButton {
  align-self: flex-start;
}

.empty {
  padding: 40px 0;
}

.cardsWrapper {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
}

.cardsScroll {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  overflow-y: visible;
  padding-bottom: 8px;
}

.cardsScroll::-webkit-scrollbar {
  height: 8px;
}

.cardsScroll::-webkit-scrollbar-track {
  background: #f0f0f0;
  border-radius: 4px;
}

.cardsScroll::-webkit-scrollbar-thumb {
  background: #bfbfbf;
  border-radius: 4px;
}

.cardsScroll::-webkit-scrollbar-thumb:hover {
  background: #999;
}
```

**Step 3: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 4: Commit**

```bash
git add webui/src/components/CardsContainer.tsx webui/src/styles/components/cardsContainer.module.css
git commit -m "feat: add cards container component"
```

---

## Task 7: Update API Endpoints

**Files:**

- Modify: `webui/src/api/endpoints.ts`

**Step 1: Add batch rules endpoint**

Add to `webui/src/api/endpoints.ts`:

```typescript
import type {
  AuthResponse,
  DomainsResponse,
  LoginRequest,
  PackagesResponse,
  SectionsResponse,
  UserInfo,
  CreateRuleRequest,
  BatchRulesResponse
} from '../types';

// ... existing exports ...

export const rulesApi = {
  createBatch: async (rules: CreateRuleRequest[]): Promise<BatchRulesResponse> => {
    const response = await apiClient.post<BatchRulesResponse>(
      '/api/v1/domains/rules/batch',
      rules
    );
    return response.data;
  },
};
```

**Step 2: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 3: Commit**

```bash
git add webui/src/api/endpoints.ts
git commit -m "feat: add batch rules API endpoint"
```

---

## Task 8: Update Backend Models

**Files:**

- Modify: `src/fa/models.py`

**Step 1: Add batch rules models**

Add to `src/fa/models.py`:

```python
from pydantic import BaseModel
from typing import List, Optional


class PositionChoice(BaseModel):
    type: str  # 'top', 'bottom', 'custom'
    custom_number: Optional[int] = None


class RuleDefinition(BaseModel):
    domain_uid: str
    package_uid: str
    section_uid: Optional[str] = None
    position: PositionChoice
    action: str  # 'accept' or 'drop'
    track: str  # 'log' or 'none'
    source_ip: str
    dest_ip: str


class CreateRuleRequest(BaseModel):
    source: RuleDefinition
    destination: RuleDefinition


class BatchRulesResponse(BaseModel):
    success: bool
    created: int
    failed: int
    errors: List[dict]
```

**Step 2: Verify Python syntax**

Run:

```bash
cd . && python -m py_compile src/fa/models.py
```

Expected: No syntax errors

**Step 3: Commit**

```bash
git add src/fa/models.py
git commit -m "feat: add batch rules models"
```

---

## Task 9: Add Backend Endpoint

**Files:**

- Modify: `src/fa/routes/domains.py`

**Step 1: Add batch rules endpoint**

Add to `src/fa/routes/domains.py`:

```python
@router.post("/domains/rules/batch")
async def create_rules_batch(
    rules: List[CreateRuleRequest],
    session: SessionData | None = Depends(get_session_data_optional)
):
    """
    MOCK: Create multiple firewall rules across domains.

    TODO: Implement actual Check Point API calls.
    Currently validates and returns success.
    """
    logger.info(f"Received batch rules request: {len(rules)} rules")

    # Validate request structure
    for i, rule in enumerate(rules):
        if not rule.source.domain_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: Source domain_uid is required")
        if not rule.source.package_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: Source package_uid is required")
        if not rule.destination.domain_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: Destination domain_uid is required")
        if not rule.destination.package_uid:
            raise HTTPException(status_code=400, detail=f"Rule {i}: Destination package_uid is required")

        # Validate position
        for line_name, line in [("source", rule.source), ("destination", rule.destination)]:
            if line.position.type == "custom" and line.position.custom_number is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rule {i} {line_name}: Custom position requires custom_number"
                )

    # MOCK: Return success without creating rules
    return {
        "success": True,
        "created": len(rules) * 2,  # 2 rules per card
        "failed": 0,
        "errors": []
    }
```

**Step 2: Verify Python syntax**

Run:

```bash
cd . && python -m py_compile src/fa/routes/domains.py
```

Expected: No syntax errors

**Step 3: Commit**

```bash
git add src/fa/routes/domains.py
git commit -m "feat: add mock batch rules endpoint"
```

---

## Task 10: Refactor Domains Page

**Files:**

- Modify: `webui/src/pages/Domains.tsx`
- Modify: `webui/src/styles/pages/domains.module.css`

**Step 1: Replace Domains page content**

Replace entire `webui/src/pages/Domains.tsx` with:

```typescript
import { useState, useEffect } from 'react';
import { Button, message, Spin } from 'antd';
import { domainsApi, packagesApi, rulesApi } from '../api/endpoints';
import IpPoolsPanel from '../components/IpPoolsPanel';
import CardsContainer from '../components/CardsContainer';
import type {
  DomainItem,
  PackageItem,
  SectionItem,
  RuleCard as RuleCardType,
  IpPool,
} from '../types';
import styles from '../styles/pages/domains.module.css';

export default function Domains() {
  // Domain/package/section data
  const [domains, setDomains] = useState<DomainItem[]>([]);
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [sections, setSections] = useState<SectionItem[]>([]);

  // IP pools
  const [sourcePool, setSourcePool] = useState<IpPool>({
    raw: '',
    validated: [],
    invalid: [],
    errors: [],
  });
  const [destPool, setDestPool] = useState<IpPool>({
    raw: '',
    validated: [],
    invalid: [],
    errors: [],
  });
  const [services, setServices] = useState('');

  // Cards
  const [cards, setCards] = useState<RuleCardType[]>([]);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);

  // Loading
  const [initialLoading, setInitialLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

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

  // Fetch packages for a domain
  function handleFetchPackages(domainUid: string) {
    const fetchPackages = async () => {
      try {
        const response = await packagesApi.list(domainUid);
        setPackages(response.packages);
      } catch {
        message.error('Failed to load packages');
      }
    };

    fetchPackages();
  }

  // Fetch sections for a package
  function handleFetchSections(domainUid: string, pkgUid: string) {
    const fetchSections = async () => {
      try {
        const response = await packagesApi.getSections(domainUid, pkgUid);
        setSections(response.sections);
      } catch {
        message.error('Failed to load sections');
      }
    };

    fetchSections();
  }

  // Validate cards before submission
  function validateCards(): boolean {
    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];

      if (!card.source.ip) {
        message.error(`Card ${i + 1}: Source IP is required`);
        return false;
      }
      if (!card.destination.ip) {
        message.error(`Card ${i + 1}: Destination IP is required`);
        return false;
      }
      if (!card.source.domain || !card.source.package) {
        message.error(`Card ${i + 1}: Source domain and package are required`);
        return false;
      }
      if (!card.destination.domain || !card.destination.package) {
        message.error(`Card ${i + 1}: Destination domain and package are required`);
        return false;
      }
      if (card.source.position.type === 'custom' && !card.source.position.custom_number) {
        message.error(`Card ${i + 1}: Source custom position number is required`);
        return false;
      }
      if (card.destination.position.type === 'custom' && !card.destination.position.custom_number) {
        message.error(`Card ${i + 1}: Destination custom position number is required`);
        return false;
      }
    }

    return true;
  }

  // Submit batch rules
  async function handleSubmit() {
    if (cards.length === 0) {
      message.warning('Please add at least one card');
      return;
    }

    if (!validateCards()) {
      return;
    }

    setSubmitting(true);

    try {
      const rules = cards.map(card => ({
        source: {
          domain_uid: card.source.domain!.uid,
          package_uid: card.source.package!.uid,
          section_uid: card.source.section?.uid || null,
          position: card.source.position,
          action: card.source.action,
          track: card.source.track,
          source_ip: card.source.ip!.normalized,
          dest_ip: card.destination.ip!.normalized,
        },
        destination: {
          domain_uid: card.destination.domain!.uid,
          package_uid: card.destination.package!.uid,
          section_uid: card.destination.section?.uid || null,
          position: card.destination.position,
          action: card.destination.action,
          track: card.destination.track,
          source_ip: card.source.ip!.normalized,
          dest_ip: card.destination.ip!.normalized,
        },
      }));

      const response = await rulesApi.createBatch(rules);

      if (response.success) {
        message.success(`Successfully created ${response.created} rules`);
        setCards([]);
        setSelectedCardId(null);
      } else {
        message.error(`Failed: ${response.failed} rules had errors`);
      }
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : 'Failed to submit rules');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.pageContainer}>
      <Spin spinning={initialLoading}>
        <IpPoolsPanel
          sourcePool={sourcePool}
          destPool={destPool}
          services={services}
          onSourceChange={setSourcePool}
          onDestChange={setDestPool}
          onServicesChange={setServices}
        />

        <CardsContainer
          cards={cards}
          sourcePool={sourcePool.validated}
          destPool={destPool.validated}
          domains={domains}
          packages={packages}
          sections={sections}
          selectedCardId={selectedCardId}
          onCardsChange={setCards}
          onSelectedCardIdChange={setSelectedCardId}
          onFetchPackages={handleFetchPackages}
          onFetchSections={handleFetchSections}
        />

        {cards.length > 0 && (
          <div className={styles.submitSection}>
            <Button
              type="primary"
              size="large"
              onClick={handleSubmit}
              loading={submitting}
            >
              Submit Rules
            </Button>
          </div>
        )}
      </Spin>
    </div>
  );
}
```

**Step 2: Update domains CSS**

Update `webui/src/styles/pages/domains.module.css`:

```css
.pageContainer {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px;
}

.submitSection {
  display: flex;
  justify-content: flex-end;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}
```

**Step 3: Verify TypeScript compilation**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 4: Commit**

```bash
git add webui/src/pages/Domains.tsx webui/src/styles/pages/domains.module.css
git commit -m "feat: refactor domains page to use card-based layout"
```

---

## Task 11: Fix Type Imports and Final Polish

**Files:**

- Modify: `src/fa/routes/domains.py`

**Step 1: Add missing imports**

Ensure `src/fa/routes/domains.py` has these imports:

```python
from typing import List
from ..models import CreateRuleRequest, PositionChoice
```

**Step 2: Verify Python syntax**

Run:

```bash
cd . && python -m py_compile src/fa/routes/domains.py
```

Expected: No syntax errors

**Step 3: Run type check**

Run:

```bash
cd . && uv run mypy src/fa/routes/domains.py
```

Expected: No type errors (or acceptable ones)

**Step 4: Commit**

```bash
git add src/fa/routes/domains.py
git commit -m "fix: add missing imports to domains route"
```

---

## Task 12: Final Testing

**Files:**

- Test all components

**Step 1: Start dev server**

Run:

```bash
cd webui && npm run dev
```

Expected: Vite dev server starts

**Step 2: Run type check**

Run:

```bash
cd webui && npx tsc --noEmit
```

Expected: No type errors

**Step 3: Run backend server**

Run:

```bash
cd . && uv run uvicorn src.fa.main:app --reload
```

Expected: FastAPI server starts

**Step 4: Manual testing checklist**

1. Navigate to `/domains`
2. Paste valid IPs into Source field
3. Paste valid IPs into Destination field
4. Verify validation works (try invalid IPs)
5. Click "Add Card"
6. Verify card appears with first unused IP selected
7. Select domain, verify packages load
8. Select package, verify sections load
9. Test "Same package" checkbox
10. Add second card, verify IP tracking
11. Test card repositioning (↑↓ buttons)
12. Test keyboard shortcuts (Ctrl+↑/Ctrl+↓, Delete, Tab)
13. Test card deletion
14. Fill all required fields
15. Click "Submit Rules"
16. Verify success message and cards clear

**Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "fix: final polish and bug fixes"
```

---

## Task 13: Update Documentation

**Files:**

- Modify: `docs/CONTEXT.md`
- Create: `docs/internal/features/260306-domains-rule-cards/IMPLEMENTATION_SUMMARY.md`

**Step 1: Update CONTEXT.md**

Add to `docs/CONTEXT.md`:

```markdown
## Domains Rule Cards (2026-03-06)

**Status:** Implemented
**Design:** [260306-domains-rule-cards-design.md](../plans/260306-domains-rule-cards-design.md)
**Plan:** [260306-domains-rule-cards-plan.md](../plans/260306-domains-rule-cards-plan.md)

Card-based interface for creating firewall rules across multiple domains.
IP pools panel with validation, horizontal card container, keyboard shortcuts.

**Key Files:**
- `webui/src/pages/Domains.tsx` - Main page
- `webui/src/components/IpPoolsPanel.tsx` - IP input panel
- `webui/src/components/RuleCard.tsx` - Individual rule card
- `webui/src/components/CardsContainer.tsx` - Cards wrapper
- `webui/src/utils/ipValidator.ts` - IP validation logic
- `src/fa/routes/domains.py` - Backend endpoint
```

**Step 2: Create implementation summary**

Create `docs/internal/features/260306-domains-rule-cards/IMPLEMENTATION_SUMMARY.md`:

```markdown
# Domains Rule Cards - Implementation Summary

**Date:** 2026-03-06
**Status:** Complete

## What Was Built

Transformed the `/domains` page from a sequential form to a card-based interface
for creating firewall rules across multiple domains.

## Key Components

### Frontend
- **IpPoolsPanel**: Collapsible panel for pasting and validating IPs
- **RuleCard**: Single card with source/destination lines, 7 fields each
- **CardsContainer**: Horizontal scroll container with keyboard shortcuts
- **ipValidator**: Utility for parsing IPv4, IPv6, CIDR, FQDN, ranges

### Backend
- **POST /api/v1/domains/rules/batch**: Mock endpoint for batch rule creation

## Features

- Real-time IP validation with inline errors
- Smart IP defaulting (first unused IP)
- "Same package" checkbox to copy source settings to destination
- Card repositioning via buttons or Ctrl+↑/Ctrl+↓
- Keyboard navigation (Tab, Delete)
- Each card generates two rules (source-side and destination-side)

## Testing

Manual testing completed:
- IP validation (IPv4, IPv6, CIDR, FQDN, ranges, invalid entries)
- Card creation and deletion
- IP pool usage tracking
- Domain/package/section cascading
- Keyboard shortcuts
- Batch submission

## Future Enhancements

- Drag-and-drop IP reordering
- Persistence across refresh
- Actual Check Point API integration
- Rule preview before submission
```

**Step 3: Commit documentation**

```bash
git add docs/CONTEXT.md docs/internal/features/260306-domains-rule-cards/IMPLEMENTATION_SUMMARY.md
git commit -m "docs: add domains rule cards implementation summary"
```

---

## Task 14: Final Commit and Tag

**Step 1: Review all changes**

Run:

```bash
git log --oneline -10
```

Expected: All commits from this plan visible

**Step 2: Format code**

Run:

```bash
cd webui && npm run build
```

Expected: Build succeeds

**Step 3: Run linter**

Run:

```bash
cd . && uv run ruff check src/fa/
```

Expected: No errors (or acceptable ones)

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete domains rule cards implementation"
```

**Step 5: Create tag**

```bash
git tag -a v0.603.0 -m "Domains rule cards feature"
```

---

## Summary

This plan implements a card-based interface for creating firewall rules across multiple domains. The implementation follows TDD principles, uses existing Ant Design components, and includes comprehensive IP validation.

**Total Tasks:** 14
**Estimated Time:** 4-6 hours
**Dependencies:** ipaddr.js (added)
**Breaking Changes:** None (new feature)
