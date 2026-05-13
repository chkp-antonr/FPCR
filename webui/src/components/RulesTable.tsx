import React, { useMemo, useRef } from 'react';
import { Table, Button, Select, InputNumber, Input, Tag, Space, Spin } from 'antd';
import { DeleteOutlined, CopyOutlined, CloseOutlined } from '@ant-design/icons';
import type { ColumnsType, TableProps } from 'antd/es/table';
import type { DomainInfo, SectionInfo } from '../types';
import styles from '../styles/components/rulesTable.module.css';

const { Option } = Select;

export interface Rule {
  key: string;
  uid: string;
  clone?: string;
  comments?: string;
  rule_name?: string;
  source_ips?: string[];
  dest_ips?: string[];
  service?: string[];
  services?: string[];
  domain?: string | null;
  package?: string | null;
  section?: string | null;
  action?: string;
  track?: string;
  position?: string;
  position_top?: string;
  position_bottom?: string;
  enabled?: boolean;
  add_x_forwarded_for?: boolean;
  error?: string;
}

interface RulesTableProps {
  rules: Rule[];
  domains: DomainInfo[];
  availableServices?: string[];
  availableSourceIps?: string[];
  availableDestIps?: string[];
  disabled?: boolean;
  loading?: boolean;
  updateRule: (rule: Rule) => void;
  handleClone: (rule: Rule) => void;
  onDelete: (rule: Rule) => void;
  onFetchPackages?: (domain: string, rule?: Rule) => void | Promise<void>;
  onFetchSections?: (domain: string, pkg: string, rule?: Rule) => void | Promise<void>;
  loadingPackageRules?: string[];
  loadingSectionRules?: string[];
  onDragOver?: (e: React.DragEvent, rule: Rule) => void;
  onDrop?: (e: React.DragEvent, rule: Rule) => void;
}

const RulesTable: React.FC<RulesTableProps> = ({
  rules,
  domains,
  availableServices = [],
  availableSourceIps = [],
  availableDestIps = [],
  disabled = false,
  loading = false,
  updateRule,
  handleClone,
  onDelete,
  onFetchPackages,
  onFetchSections,
  loadingPackageRules = [],
  loadingSectionRules = [],
  onDragOver,
  onDrop,
}) => {
  const dropTargetRef = useRef<string | null>(null);

  // Memoize calculation of used IPs
  const usedIps = useMemo(() => {
    const used = new Set<string>();
    rules.forEach(rule => {
      rule.source_ips?.forEach(ip => used.add(ip.toLowerCase()));
      rule.dest_ips?.forEach(ip => used.add(ip.toLowerCase()));
    });
    return Array.from(used);
  }, [rules]);

  // Group IPs by used/unused status
  const getIpTagStyle = (ip: string, usedIps: string[]) => {
    if (!ip) return styles.unusedTag;
    return usedIps.includes(ip.toLowerCase()) ? styles.usedTag : styles.unusedTag;
  };

  // Handle domain change
  const handleDomainChange = (value: string | undefined, rule: Rule) => {
    const updatedRule = {
      ...rule,
      domain: value ?? null,
      package: null,
      section: null,
    };
    updateRule(updatedRule);
    if (onFetchPackages && value) {
      onFetchPackages(value, rule);
    }
  };

  // Handle package change
  const handlePackageChange = (value: string | undefined, rule: Rule) => {
    const updatedRule = {
      ...rule,
      package: value ?? null,
      section: null,
    };
    updateRule(updatedRule);
    if (onFetchSections && rule.domain && value) {
      onFetchSections(rule.domain, value, rule);
    }
  };

  // Handle section change
  const handleSectionChange = (value: string | undefined, rule: Rule) => {
    const updatedRule = {
      ...rule,
      section: value ?? null,
    };
    updateRule(updatedRule);
  };

  // Handle position change
  const handlePositionChange = (field: 'position' | 'position_top' | 'position_bottom', value: string | number | null | undefined, rule: Rule) => {
    let updatedRule = { ...rule };

    if (field === 'position') {
      updatedRule.position_top = undefined;
      updatedRule.position_bottom = undefined;
    } else if (field === 'position_top' || field === 'position_bottom') {
      updatedRule.position = undefined;
    }

    updatedRule[field] = value as string;

    updateRule(updatedRule);
  };

  // Handle drag events
  const handleDragOverInternal = (e: React.DragEvent, rule: Rule) => {
    e.preventDefault();
    dropTargetRef.current = rule.key;
    if (onDragOver) {
      onDragOver(e, rule);
    }
  };

  const handleDropInternal = (e: React.DragEvent, rule: Rule) => {
    e.preventDefault();
    dropTargetRef.current = null;

    // Check for direct IP drag from input panel
    const directIpData = e.dataTransfer.getData('application/ip-drag');
    if (directIpData) {
      try {
        const data = JSON.parse(directIpData);
        if (data.isDirectIpDrag) {
          // Direct IP drag - just add the IP without modifying domain/package
          const targetField = data.source === 'source' ? 'source_ips' : 'dest_ips';
          const currentIps = targetField === 'source_ips' ? (rule.source_ips || []) : (rule.dest_ips || []);

          if (currentIps.includes(data.ip)) {
            // IP already exists - do nothing (or could show a message)
            return;
          }

          const updatedRule = {
            ...rule,
            [targetField]: [...currentIps, data.ip],
          };
          updateRule(updatedRule);
          return;
        }
      } catch {
        // Not a valid direct IP drag, fall through to prediction handling
      }
    }

    // Handle prediction drag
    if (onDrop) {
      onDrop(e, rule);
    }
  };

  const handleDragLeave = () => {
    dropTargetRef.current = null;
  };

  // Get available packages for selected domain
  const getAvailablePackages = (rule: Rule): string[] => {
    if (!rule.domain) return [];
    const domain = domains.find(d => d.name === rule.domain);
    return domain?.packages.map(p => p.name) || [];
  };

  // Get available sections for selected package
  const getAvailableSections = (rule: Rule): SectionInfo[] => {
    if (!rule.domain || !rule.package) return [];
    const domain = domains.find(d => d.name === rule.domain);
    const pkg = domain?.packages.find(p => p.name === rule.package);
    return pkg?.sections || [];
  };

  const columns: ColumnsType<Rule> = [
    {
      title: 'Source IPs',
      dataIndex: 'source_ips',
      key: 'source_ips',
      width: 280,
      render: (ips: string[] | undefined, record: Rule) => (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '4px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Select
              mode="multiple"
              value={ips || []}
              onChange={(value) => updateRule({ ...record, source_ips: value })}
              disabled={disabled}
              style={{ width: '100%' }}
              placeholder="Select source IPs"
              options={availableSourceIps.map(ip => ({
                label: (
                  <Tag className={getIpTagStyle(ip, usedIps)}>{ip}</Tag>
                ),
                value: ip,
              }))}
              maxTagCount={1}
              tagRender={(props) => {
                const { label, value, onClose } = props;
                return (
                  <Tag
                    className={getIpTagStyle(value as string, usedIps)}
                    closable={onClose !== undefined}
                    onClose={onClose}
                    style={{ marginInlineEnd: 4 }}
                  >
                    {label}
                  </Tag>
                );
              }}
            />
            {(ips?.length ?? 0) > 1 && (
              <div style={{ fontSize: '11px', color: '#8c8c8c', marginTop: '4px', wordWrap: 'break-word', whiteSpace: 'pre-wrap' }}>
                {ips?.join(', ')}
              </div>
            )}
          </div>
          {(ips?.length ?? 0) > 0 && (
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => updateRule({ ...record, source_ips: [] })}
              style={{ minWidth: 'auto', padding: '4px', height: 'auto', marginTop: '2px' }}
              title="Clear selection"
            />
          )}
        </div>
      ),
    },
    {
      title: 'Dest IPs',
      dataIndex: 'dest_ips',
      key: 'dest_ips',
      width: 280,
      render: (ips: string[] | undefined, record: Rule) => (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '4px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Select
              mode="multiple"
              value={ips || []}
              onChange={(value) => updateRule({ ...record, dest_ips: value })}
              disabled={disabled}
              style={{ width: '100%' }}
              placeholder="Select dest IPs"
              options={availableDestIps.map(ip => ({
                label: (
                  <Tag className={getIpTagStyle(ip, usedIps)}>{ip}</Tag>
                ),
                value: ip,
              }))}
              maxTagCount={1}
              tagRender={(props) => {
                const { label, value, onClose } = props;
                return (
                  <Tag
                    className={getIpTagStyle(value as string, usedIps)}
                    closable={onClose !== undefined}
                    onClose={onClose}
                    style={{ marginInlineEnd: 4 }}
                  >
                    {label}
                  </Tag>
                );
              }}
            />
            {(ips?.length ?? 0) > 1 && (
              <div style={{ fontSize: '11px', color: '#8c8c8c', marginTop: '4px', wordWrap: 'break-word', whiteSpace: 'pre-wrap' }}>
                {ips?.join(', ')}
              </div>
            )}
          </div>
          {(ips?.length ?? 0) > 0 && (
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => updateRule({ ...record, dest_ips: [] })}
              style={{ minWidth: 'auto', padding: '4px', height: 'auto', marginTop: '2px' }}
              title="Clear selection"
            />
          )}
        </div>
      ),
    },
    {
      title: 'Domain',
      dataIndex: 'domain',
      key: 'domain',
      width: 150,
      render: (domain: string | undefined, record: Rule) => (
        <Select
          value={domain}
          onChange={(value) => handleDomainChange(value, record)}
          disabled={disabled}
          style={{ width: '100%' }}
          placeholder="Select domain"
          allowClear
        >
          {domains.map(d => (
            <Option key={d.name} value={d.name}>{d.name}</Option>
          ))}
        </Select>
      ),
    },
    {
      title: 'Package',
      dataIndex: 'package',
      key: 'package',
      width: 200,
      render: (pkg: string | undefined, record: Rule) => {
        const packages = getAvailablePackages(record);
        const hasDomainSelected = record.domain && packages.length === 0;
        const isLoadingPackages = loadingPackageRules.includes(record.uid);

        return (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '4px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Select
                value={pkg}
                onChange={(value) => handlePackageChange(value, record)}
                disabled={disabled || !record.domain}
                loading={isLoadingPackages}
                style={{ width: '100%' }}
                placeholder="Select package"
                allowClear
                notFoundContent={hasDomainSelected ? (
                  <div style={{ padding: '4px 8px' }}>
                    {isLoadingPackages ? (
                      <Space size="small">
                        <Spin size="small" />
                        <span>Loading packages...</span>
                      </Space>
                    ) : (
                      <div>No packages loaded</div>
                    )}
                    {onFetchPackages && !isLoadingPackages && (
                      <Button
                        type="link"
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          // Clear package selection before reloading
                          updateRule({ ...record, package: null, section: null });
                          if (onFetchPackages && record.domain) {
                            onFetchPackages(record.domain, record);
                          }
                        }}
                        style={{ padding: 0, height: 'auto', fontSize: '12px' }}
                      >
                        Click to load
                      </Button>
                    )}
                  </div>
                ) : 'Select a domain first'}
              >
                {packages.map(p => (
                  <Option key={p} value={p}>{p}</Option>
                ))}
              </Select>
            </div>
            {record.domain && (
              <Button
                type="text"
                size="small"
                disabled={isLoadingPackages}
                onClick={(e) => {
                  e.stopPropagation();
                  // Clear package selection before reloading
                  updateRule({ ...record, package: null, section: null });
                  if (onFetchPackages) {
                    onFetchPackages(record.domain!, record);
                  }
                }}
                style={{ minWidth: 'auto', padding: '4px', height: 'auto' }}
                title="Reload packages"
              >
                ↻
              </Button>
            )}
          </div>
        );
      },
    },
    {
      title: 'Section',
      dataIndex: 'section',
      key: 'section',
      width: 280,
      render: (section: string | undefined, record: Rule) => {
        // Find the section object to get its rulebase range
        const sections = getAvailableSections(record);
        const hasPackageSelected = record.package && sections.length === 0;
        const isLoadingSections = loadingSectionRules.includes(record.uid);

        return (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '4px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Select
                value={section}
                onChange={(value) => handleSectionChange(value, record)}
                disabled={disabled || !record.package}
                loading={isLoadingSections}
                style={{ width: '100%' }}
                placeholder="Select section"
                allowClear
                popupMatchSelectWidth={false}
                optionLabelProp="label"
                notFoundContent={hasPackageSelected ? (
                  <div style={{ padding: '4px 8px' }}>
                    {isLoadingSections ? (
                      <Space size="small">
                        <Spin size="small" />
                        <span>Loading sections...</span>
                      </Space>
                    ) : (
                      <div>No sections loaded</div>
                    )}
                    {onFetchSections && !isLoadingSections && (
                      <Button
                        type="link"
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          // Clear section selection before reloading
                          updateRule({ ...record, section: null });
                          if (onFetchSections && record.domain && record.package) {
                            onFetchSections(record.domain, record.package, record);
                          }
                        }}
                        style={{ padding: 0, height: 'auto', fontSize: '12px' }}
                      >
                        Click to load
                      </Button>
                    )}
                  </div>
                ) : 'Select a package first'}
                tagRender={(props) => {
                  const { value } = props;
                  const s = sections.find(sec => sec.name === value);
                  const displayText = s ? `${s.rulebase_range[0]}-${s.rulebase_range[1]} ${s.name}` : value;
                  return (
                    <span style={{ fontSize: '12px' }}>{displayText}</span>
                  );
                }}
              >
                {sections.map(s => {
                  const label = `${s.rulebase_range[0]}-${s.rulebase_range[1]} ${s.name}`;
                  return (
                    <Option key={s.name} value={s.name} label={label}>
                      {label}
                    </Option>
                  );
                })}
              </Select>
            </div>
            {record.package && (
              <Button
                type="text"
                size="small"
                disabled={isLoadingSections}
                onClick={(e) => {
                  e.stopPropagation();
                  // Clear section selection before reloading
                  updateRule({ ...record, section: null });
                  if (onFetchSections && record.domain && record.package) {
                    onFetchSections(record.domain, record.package, record);
                  }
                }}
                style={{ minWidth: 'auto', padding: '4px', height: 'auto' }}
                title="Reload sections"
              >
                ↻
              </Button>
            )}
          </div>
        );
      },
    },
    {
      title: 'Position',
      key: 'position',
      width: 200,
      render: (_: unknown, record: Rule) => (
        <Space.Compact style={{ width: '100%' }}>
          <Select
            value={record.position || 'bottom'}
            onChange={(value) => handlePositionChange('position', value, record)}
            disabled={disabled}
            className={styles.smallSelect}
            optionLabelProp="label"
          >
            <Option value="top" label="Top">Top</Option>
            <Option value="bottom" label="Bottom">Bottom</Option>
            <Option value="before" label="Before">Before</Option>
            <Option value="after" label="After">After</Option>
          </Select>
          {record.position !== 'top' && record.position !== 'bottom' && (
            <InputNumber
              value={record.position_top || record.position_bottom ? Number(record.position_top || record.position_bottom) : undefined}
              onChange={(value) => {
                if (record.position === 'before') {
                  handlePositionChange('position_top', value, record);
                } else {
                  handlePositionChange('position_bottom', value, record);
                }
              }}
              disabled={disabled}
              placeholder="#"
              min={1}
              style={{ width: '100%' }}
            />
          )}
        </Space.Compact>
      ),
    },
    {
      title: 'Comments',
      dataIndex: 'comments',
      key: 'comments',
      width: 200,
      render: (text: string, record: Rule) => (
        <Input
          value={text || ''}
          onChange={(e) => updateRule({ ...record, comments: e.target.value })}
          disabled={disabled}
          placeholder="Comments"
          size="small"
        />
      ),
    },
    {
      title: 'Rule Name',
      dataIndex: 'rule_name',
      key: 'rule_name',
      width: 150,
      render: (text: string, record: Rule) => (
        <Input
          value={text || ''}
          onChange={(e) => updateRule({ ...record, rule_name: e.target.value })}
          disabled={disabled}
          placeholder="Rule name"
          size="small"
        />
      ),
    },
    {
      title: 'Action',
      dataIndex: 'action',
      key: 'action',
      width: 120,
      render: (action: string | undefined, record: Rule) => (
        <Select
          value={action || 'accept'}
          onChange={(value) => updateRule({ ...record, action: value })}
          disabled={disabled}
          style={{ width: '100%' }}
        >
          <Option value="accept">Accept</Option>
          <Option value="drop">Drop</Option>
          <Option value="reject">Reject</Option>
          <Option value="authenticate">Authenticate</Option>
        </Select>
      ),
    },
    {
      title: 'Track',
      dataIndex: 'track',
      key: 'track',
      width: 120,
      render: (track: string | undefined, record: Rule) => (
        <Select
          value={track || 'None'}
          onChange={(value) => updateRule({ ...record, track: value })}
          disabled={disabled}
          style={{ width: '100%' }}
        >
          <Option value="None">None</Option>
          <Option value="Log">Log</Option>
          <Option value="Alert">Alert</Option>
          <Option value="Accounting">Accounting</Option>
        </Select>
      ),
    },
    {
      title: 'Services',
      dataIndex: 'services',
      key: 'services',
      width: 200,
      render: (services: string[] | undefined, record: Rule) => (
        <Select
          mode="multiple"
          value={services || record.service || []}
          onChange={(value) => updateRule({ ...record, services: value, service: value })}
          disabled={disabled}
          style={{ width: '100%' }}
          placeholder="Select services"
          allowClear
        >
          {availableServices.map(service => (
            <Option key={service} value={service}>{service}</Option>
          ))}
        </Select>
      ),
    },
    {
      key: 'actions',
      width: 70,
      fixed: 'right' as const,
      render: (_: unknown, record: Rule) => (
        <Space size="small">
          <Button
            type="text"
            icon={<CopyOutlined />}
            onClick={() => handleClone(record)}
            disabled={disabled}
            title="Clone rule"
          />
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={() => onDelete(record)}
            disabled={disabled}
            title="Delete rule"
          />
        </Space>
      ),
    },
  ];

  const rowClassName = (record: Rule): string => {
    let className = styles.clickable;
    if (record.error) {
      className += ` ${styles.errorRow}`;
    }
    if (dropTargetRef.current === record.key) {
      className += ` ${styles.dropTarget}`;
    }
    return className;
  };

  const onRow: TableProps<Rule>['onRow'] = (record) => ({
    onDragOver: (e) => handleDragOverInternal(e, record),
    onDrop: (e) => handleDropInternal(e, record),
    onDragLeave: handleDragLeave,
  });

  return (
    <div className={styles.tableContainer}>
      <Table<Rule>
        className={styles.table}
        columns={columns}
        dataSource={rules}
        rowClassName={rowClassName}
        onRow={onRow}
        pagination={false}
        scroll={{ x: 'max-content', y: 400 }}
        size="small"
        loading={loading}
        rowKey="key"
      />
    </div>
  );
};

export default RulesTable;
