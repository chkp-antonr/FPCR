import { Card, Select, Radio, InputNumber, Checkbox, Button, Space } from 'antd';
import { UpOutlined, DownOutlined, DeleteOutlined } from '@ant-design/icons';
import type { SelectProps } from 'antd/es/select';
import type { RuleCard as RuleCardType, RuleLine, IpEntry, DomainItem, PackageItem, SectionItem } from '../types';
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

    const packageOptions: SelectProps['options'] = packages.map(p => ({ value: p.uid, label: p.name }));

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
              value={line.position.custom_number ?? undefined}
              onChange={(value) => updateLine(lineKey, { position: { type: 'custom', custom_number: value ?? undefined } })}
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
