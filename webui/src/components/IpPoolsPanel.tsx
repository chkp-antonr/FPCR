import { Collapse, Input, Badge, Alert } from 'antd';
import { useState } from 'react';
import { validateIpInput, findDuplicates } from '../utils/ipValidator';
import type { IpPool } from '../types';
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

  const validateAndSetSource = (value: string) => {
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
  };

  const validateAndSetDest = (value: string) => {
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
  };

  function extractInvalid(raw: string, validated: import('../types').IpEntry[]): string[] {
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
                  rows={3}
                />
                {sourcePool.errors.length > 0 && (
                  <Alert type="warning" message={sourcePool.errors.join(', ')} showIcon className={styles.alert} />
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
                  <Alert type="warning" message={destPool.errors.join(', ')} showIcon className={styles.alert} />
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
                  value={services}
                  onChange={(e) => onServicesChange(e.target.value)}
                  placeholder="Paste services here (no processing yet)..."
                  className={styles.textarea}
                  rows={3}
                />
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}
