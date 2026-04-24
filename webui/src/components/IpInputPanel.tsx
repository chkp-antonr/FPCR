import { Select, Badge, Tag } from 'antd';
import { HolderOutlined } from '@ant-design/icons';
import type { IpEntry, ServiceEntry } from '../types';
import { validateIpInput } from '../utils/ipValidator';
import { validateServiceInput } from '../utils/serviceValidator';
import styles from '../styles/components/ipInputPanel.module.css';
import rulesTableStyles from '../styles/components/rulesTable.module.css';

interface IpInputPanelProps {
  sourcePool: IpEntry[];
  destPool: IpEntry[];
  servicesPool: ServiceEntry[];
  usedSourceIps?: string[];
  usedDestIps?: string[];
  onSourceChange: (entries: IpEntry[]) => void;
  onDestChange: (entries: IpEntry[]) => void;
  onServicesChange: (entries: ServiceEntry[]) => void;
}

interface DraggableIpTagProps {
  ip: string;
  isUsed: boolean;
  sourceType: 'source' | 'dest';
  onClose?: (e: React.MouseEvent<HTMLElement>) => void;
}

// Draggable IP Tag Component
function DraggableIpTag({ ip, isUsed, sourceType, onClose }: DraggableIpTagProps) {
  const handleDragStart = (e: React.DragEvent) => {
    // Don't drag if clicking on close button
    if ((e.target as HTMLElement).closest('.anticon-close')) {
      e.preventDefault();
      return;
    }
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('application/ip-drag', JSON.stringify({
      ip,
      source: sourceType,
      isDirectIpDrag: true,
    }));
  };

  return (
    <Tag
      draggable
      onDragStart={handleDragStart}
      onClose={onClose}
      closable={onClose !== undefined}
      className={isUsed ? rulesTableStyles.usedTag : rulesTableStyles.unusedTag}
      style={{ cursor: 'grab', marginInlineEnd: 4 }}
    >
      <HolderOutlined style={{ marginRight: 4, fontSize: 10 }} />
      {ip}
    </Tag>
  );
}

export default function IpInputPanel({
  sourcePool,
  destPool,
  servicesPool,
  usedSourceIps = [],
  usedDestIps = [],
  onSourceChange,
  onDestChange,
  onServicesChange,
}: IpInputPanelProps) {
  const parseTagValues = (values: Array<string | number>): IpEntry[] => {
    const entries: IpEntry[] = [];
    for (const raw of values) {
      const token = String(raw).trim();
      if (!token) {
        continue;
      }
      const parsed = validateIpInput(token);
      if (parsed.length > 0) {
        entries.push(parsed[0]);
      }
    }
    return entries;
  };

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

  // Calculate unused IPs
  const unusedSourceCount = sourcePool.filter(ip => !usedSourceIps.includes(ip.normalized.toLowerCase())).length;
  const unusedDestCount = destPool.filter(ip => !usedDestIps.includes(ip.normalized.toLowerCase())).length;

  // Check if IP is used
  const isSourceUsed = (ip: string) => ip ? usedSourceIps.includes(ip.toLowerCase()) : false;
  const isDestUsed = (ip: string) => ip ? usedDestIps.includes(ip.toLowerCase()) : false;

  return (
    <div className={styles.inputPanel}>
      <div className={styles.inputColumn}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <label className={styles.label}>Source IPs:</label>
          {unusedSourceCount > 0 && (
            <Badge count={unusedSourceCount} size="small" style={{ backgroundColor: '#ffbb96', color: '#d46b08' }} />
          )}
        </div>
        <Select
          mode="tags"
          value={sourcePool.map(ip => ip.normalized)}
          options={sourceOptions}
          onChange={(values) => {
            const entries = parseTagValues(values);
            onSourceChange(entries);
          }}
          placeholder="Paste or type source IPs..."
          className={styles.tagsInput}
          tokenSeparators={[' ', ',', '\n', '\t', ';']}
          tagRender={(props) => {
            const { value, onClose } = props;
            const isUsed = isSourceUsed(value);
            return (
              <DraggableIpTag ip={value} isUsed={isUsed} sourceType="source" onClose={onClose} />
            );
          }}
          optionRender={(option) => {
            const isUsed = isSourceUsed(option.data.value as string);
            return (
              <div className={isUsed ? rulesTableStyles.usedTag : rulesTableStyles.unusedTag} style={{ margin: 4 }}>
                {option.data.label}
              </div>
            );
          }}
        />
      </div>

      <div className={styles.inputColumn}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <label className={styles.label}>Destination IPs:</label>
          {unusedDestCount > 0 && (
            <Badge count={unusedDestCount} size="small" style={{ backgroundColor: '#ffbb96', color: '#d46b08' }} />
          )}
        </div>
        <Select
          mode="tags"
          value={destPool.map(ip => ip.normalized)}
          options={destOptions}
          onChange={(values) => {
            const entries = parseTagValues(values);
            onDestChange(entries);
          }}
          placeholder="Paste or type destination IPs..."
          className={styles.tagsInput}
          tokenSeparators={[' ', ',', '\n', '\t', ';']}
          tagRender={(props) => {
            const { value, onClose } = props;
            const isUsed = isDestUsed(value);
            return (
              <DraggableIpTag ip={value} isUsed={isUsed} sourceType="dest" onClose={onClose} />
            );
          }}
          optionRender={(option) => {
            const isUsed = isDestUsed(option.data.value as string);
            return (
              <div className={isUsed ? rulesTableStyles.usedTag : rulesTableStyles.unusedTag} style={{ margin: 4 }}>
                {option.data.label}
              </div>
            );
          }}
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
