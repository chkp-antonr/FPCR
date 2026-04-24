import React, { useState, useEffect } from 'react';
import { Alert, Spin, Progress, message, Modal, Button } from 'antd';
import { LoadingOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { domainsApi, packagesApi, rules2Api, cacheApi } from '../api/endpoints';
import { validateRules, hasUnusedIps } from '../utils/ruleValidator';
import type { RuleRow, IpEntry, ServiceEntry, CacheStatusResponse } from '../types';
import IpInputPanel from '../components/IpInputPanel';
import RulesTable from '../components/RulesTable';
import styles from '../styles/pages/domains2.module.css';

interface Package {
  name: string;
  uid: string;
  access_layer: string;
  sections: Section[];
}

interface Section {
  name: string;
  uid: string;
  rulebase_range: [number, number];
  rule_count: number;
}

interface Domain {
  name: string;
  uid: string;
  packages: Package[];
}

const Domains: React.FC = () => {
  const navigate = useNavigate();

  // Domains state
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainsLoading, setDomainsLoading] = useState(false);
  const [domainsError, setDomainsError] = useState<string | null>(null);

  // Sections state (sections are stored per package, which is in domain)
  const [sections, setSections] = useState<Section[]>([]);

  // Pool state
  const [sourcePool, setSourcePool] = useState<IpEntry[]>([]);
  const [destPool, setDestPool] = useState<IpEntry[]>([]);
  const [servicesPool, setServicesPool] = useState<ServiceEntry[]>([]);

  // Rules state
  const [rules, setRules] = useState<RuleRow[]>([]);

  // Loading states
  const [submitting, setSubmitting] = useState(false);
  const [manualCoreRefreshing, setManualCoreRefreshing] = useState(false);

  // Modal state
  const [unusedIpsModal, setUnusedIpsModal] = useState<{
    visible: boolean;
    unusedIps: string[];
  }>({ visible: false, unusedIps: [] });

  const [submitConfirmModal, setSubmitConfirmModal] = useState(false);

  // Cache state
  const [cacheStatus, setCacheStatus] = useState<CacheStatusResponse>({
    domains_cached_at: null,
    packages_cached_at: null,
    sections_cached_at: null,
    is_empty: true,
    refreshing: false,
    core_refreshing: false,
    sections_refreshing: false,
    domains_progress: { processed: 0, total: 0 },
    current_domain_name: null,
    packages_progress: { processed: 0, total: 0 },
    sections_progress: { processed: 0, total: 0 },
  });

  const fetchCacheStatus = async () => {
    try {
      const status = await cacheApi.getStatus();
      setCacheStatus(status);
      return status;
    } catch (error) {
      console.error('Failed to fetch cache status:', error);
      return null;
    }
  };

  // Fetch domains on mount
  useEffect(() => {
    const fetchDomains = async () => {
      setDomainsLoading(true);
      setDomainsError(null);
      try {
        const response = await domainsApi.list();
        // Convert DomainItem[] to Domain[] with empty packages array
        const domainsWithPackages: Domain[] = (response.domains || []).map(domain => ({
          ...domain,
          packages: [],
        }));
        setDomains(domainsWithPackages);
      } catch (error) {
        setDomainsError('Failed to fetch domains');
        message.error('Failed to fetch domains');
      } finally {
        setDomainsLoading(false);
      }
    };

    fetchDomains();
  }, []);

  // Poll cache status
  useEffect(() => {
    fetchCacheStatus();
    const interval = setInterval(
      fetchCacheStatus,
      domainsLoading || cacheStatus.refreshing || manualCoreRefreshing ? 1500 : 30000
    );
    return () => clearInterval(interval);
  }, [domainsLoading, cacheStatus.refreshing, manualCoreRefreshing]);

  // Event handlers
  const handleFetchPackages = async (domainUid: string): Promise<Package[]> => {
    try {
      const response = await packagesApi.list(domainUid);
      const fetchedPackages: Package[] = (response.packages || []).map(pkg => ({
        ...pkg,
        sections: [],
      }));

      // Update the domain with its packages
      setDomains(prevDomains =>
        prevDomains.map(domain =>
          domain.uid === domainUid
            ? { ...domain, packages: fetchedPackages }
            : domain
        )
      );

      message.success(`Loaded ${fetchedPackages.length} packages`);
      return fetchedPackages;
    } catch (error: any) {
      // Handle 503 Service Unavailable (refresh in progress)
      if (error.response?.status === 503) {
        message.warning('Cache is being refreshed, please try again in a moment');
      } else {
        message.error('Failed to fetch packages');
      }
      return [];
    }
  };

  const handleFetchSections = async (domainUid: string, pkgUid: string) => {
    const hideLoading = message.loading('Loading sections for selected package...', 0);
    try {
      const response = await packagesApi.getSections(domainUid, pkgUid);
      const fetchedSections = response.sections || [];

      setSections(fetchedSections);

      // Update the package with its sections
      setDomains(prevDomains =>
        prevDomains.map(domain => {
          if (domain.uid === domainUid) {
            return {
              ...domain,
              packages: domain.packages.map(pkg =>
                pkg.uid === pkgUid
                  ? { ...pkg, sections: fetchedSections }
                  : pkg
              )
            };
          }
          return domain;
        })
      );

      hideLoading();
      message.success(`Loaded ${fetchedSections.length} sections`);
    } catch (error: any) {
      hideLoading();
      // Handle 503 Service Unavailable (refresh in progress)
      if (error.response?.status === 503) {
        message.warning('Cache is being refreshed, please try again in a moment');
      } else {
        message.error('Failed to fetch sections');
      }
    }
  };

  const handleSubmit = async () => {
    // Validate rules
    const errors = validateRules(rules);
    if (errors.length > 0) {
      message.error(`Validation failed: ${errors.map(e => e.message).join(', ')}`);
      return;
    }

    // Check for unused IPs
    const unused = hasUnusedIps(rules, sourcePool, destPool);
    const allUnusedIps = [
      ...unused.source.map(ip => ip.normalized),
      ...unused.dest.map(ip => ip.normalized),
    ];

    if (allUnusedIps.length > 0) {
      setUnusedIpsModal({ visible: true, unusedIps: allUnusedIps });
      return;
    }

    // Show confirmation modal
    setSubmitConfirmModal(true);
  };

  const submitRules = async () => {
    setSubmitting(true);
    try {
      // Transform rules to API format
      const apiRules = rules.map(rule => ({
        source_ips: rule.sourceIps.map(ip => ip.normalized),
        dest_ips: rule.destIps.map(ip => ip.normalized),
        services: rule.services.map(s => s.normalized),
        domain_uid: rule.domain?.uid || '',
        package_uid: rule.package?.uid || '',
        section_uid: rule.section?.uid || null,
        position: rule.position,
        action: rule.action,
        track: rule.track,
      }));

      await rules2Api.createBatch({ rules: apiRules });
      message.success('Rules created successfully');
      setUnusedIpsModal({ visible: false, unusedIps: [] });
      // Navigate back or refresh
      navigate('/');
    } catch (error) {
      message.error('Failed to create rules');
    } finally {
      setSubmitting(false);
    }
  };

  const handleModalConfirm = () => {
    setUnusedIpsModal({ ...unusedIpsModal, visible: false });
    setSubmitConfirmModal(true);
  };

  const handleModalCancel = () => {
    setUnusedIpsModal({ visible: false, unusedIps: [] });
  };

  const handleSubmitConfirm = () => {
    setSubmitConfirmModal(false);
    submitRules();
  };

  const handleSubmitCancel = () => {
    setSubmitConfirmModal(false);
  };

  const handleRefreshCache = async () => {
    const hideLoading = message.loading('Refreshing cache from Check Point...', 0);
    setManualCoreRefreshing(true);
    setCacheStatus(prev => ({
      ...prev,
      refreshing: true,
      core_refreshing: true,
      domains_progress: { processed: 0, total: 0 },
      packages_progress: { processed: 0, total: 0 },
    }));

    let refreshPollId: number | null = null;
    try {
      refreshPollId = window.setInterval(() => {
        void fetchCacheStatus();
      }, 700);

      await cacheApi.refresh();
      await fetchCacheStatus();
      hideLoading();
      message.success('Cache refresh completed');
    } catch (error) {
      hideLoading();
      message.error('Failed to refresh cache');
    } finally {
      if (refreshPollId !== null) {
        window.clearInterval(refreshPollId);
      }
      setManualCoreRefreshing(false);
    }
  };

  // Transform domains to RulesTable format
  const domainsForTable = domains.map(domain => ({
    name: domain.name,
    uid: domain.uid,
    packages: domain.packages.map(pkg => ({
      name: pkg.name,
      sections: pkg.sections,
    })),
  }));

  // Transform IP pools to string arrays for RulesTable
  const sourceIpsForTable = sourcePool.map(ip => ip.normalized);
  const destIpsForTable = destPool.map(ip => ip.normalized);
  const servicesForTable = servicesPool.map(svc => svc.normalized);

  // Calculate used IPs for each pool (source and dest separately)
  const usedSourceIps: string[] = [];
  const usedDestIps: string[] = [];
  rules.forEach(rule => {
    rule.sourceIps?.forEach(ip => usedSourceIps.push(ip.normalized.toLowerCase()));
    rule.destIps?.forEach(ip => usedDestIps.push(ip.normalized.toLowerCase()));
  });

  // Transform RuleRow to RulesTable.Rule format
  const rulesForTable: import('../components/RulesTable').Rule[] = rules.map(rule => ({
    key: rule.id,
    uid: rule.id,
    source_ips: rule.sourceIps.map(ip => ip.normalized),
    dest_ips: rule.destIps.map(ip => ip.normalized),
    services: rule.services.map(svc => svc.normalized),
    domain: rule.domain?.name,
    package: rule.package?.name,
    section: rule.section?.name,
    position: rule.position.type === 'custom' ? 'before' : rule.position.type,
    position_top: rule.position.type === 'custom' ? rule.position.custom_number?.toString() : undefined,
    action: rule.action,
    track: rule.track === 'log' ? 'Log' : 'None',
  }));

  const handleRulesTableUpdate = (updatedRule: import('../components/RulesTable').Rule) => {
    const ruleIndex = rules.findIndex(r => r.id === updatedRule.uid);
    if (ruleIndex !== -1) {
      const updatedRules = [...rules];
      updatedRules[ruleIndex] = {
        ...rules[ruleIndex],
        sourceIps: (updatedRule.source_ips || []).map(ip => ({
          original: ip,
          type: 'ipv4',
          normalized: ip,
        })),
        destIps: (updatedRule.dest_ips || []).map(ip => ({
          original: ip,
          type: 'ipv4',
          normalized: ip,
        })),
        services: (updatedRule.services || []).map(svc => ({
          original: svc,
          normalized: svc,
          type: 'named',
        })),
        domain: updatedRule.domain ? domains.find(d => d.name === updatedRule.domain) || null : null,
        package: updatedRule.package
          ? domains
              .find(d => d.name === updatedRule.domain)
              ?.packages.find(p => p.name === updatedRule.package) || null
          : null,
        section: updatedRule.section ? sections.find(s => s.name === updatedRule.section) || null : null,
        position: updatedRule.position === 'top' || updatedRule.position === 'bottom'
          ? { type: updatedRule.position }
          : {
              type: 'custom',
              custom_number: parseInt(updatedRule.position_top || updatedRule.position_bottom || '1'),
            },
        action: (updatedRule.action || 'accept') as 'accept' | 'drop',
        track: (updatedRule.track === 'Log' ? 'log' : 'none') as 'log' | 'none',
      };
      setRules(updatedRules);
    }
  };

  const handleRulesTableClone = (rule: import('../components/RulesTable').Rule) => {
    const originalRule = rules.find(r => r.id === rule.uid);
    if (originalRule) {
      const newRule: RuleRow = {
        id: `rule-${Date.now()}`,
        sourceIps: [...originalRule.sourceIps],
        destIps: [...originalRule.destIps],
        services: [...originalRule.services],
        domain: null,
        package: null,
        section: null,
        position: { type: 'bottom' },
        action: originalRule.action,
        track: originalRule.track,
      };
      setRules([...rules, newRule]);
      message.success('Rule cloned successfully');
    }
  };

  const handleRulesTableDelete = (rule: import('../components/RulesTable').Rule) => {
    const updatedRules = rules.filter(r => r.id !== rule.uid);
    setRules(updatedRules);
    message.success('Rule deleted successfully');
  };

  const handleAddRule = () => {
    const newRule: RuleRow = {
      id: `rule-${Date.now()}`,
      sourceIps: [],
      destIps: [],
      services: [],
      domain: null,
      package: null,
      section: null,
      position: { type: 'bottom' },
      action: 'accept',
      track: 'log',
    };
    setRules([...rules, newRule]);
  };

  const handleFetchPackagesForTable = (domainName: string) => {
    const domain = domains.find(d => d.name === domainName);
    if (domain) {
      handleFetchPackages(domain.uid);
    }
  };

  const handleFetchSectionsForTable = (domainName: string, packageName: string) => {
    const domain = domains.find(d => d.name === domainName);
    const pkg = domain?.packages.find(p => p.name === packageName);
    if (domain && pkg) {
      handleFetchSections(domain.uid, pkg.uid);
    }
  };

  const getProgressPercent = (processed: number, total: number) => {
    if (total <= 0) {
      return 0;
    }
    return Math.round((processed / total) * 100);
  };

  const getDomainProgressLabel = () => {
    const processed = cacheStatus.domains_progress.processed;
    const total = cacheStatus.domains_progress.total;
    const currentDomainName = cacheStatus.current_domain_name;

    if (currentDomainName && total > 0) {
      const displayIndex = Math.min(processed + 1, total);
      return `Domain ${displayIndex}/${total}: ${currentDomainName}`;
    }

    return `Domains: ${processed} / ${total}`;
  };

  if (domainsLoading && domains.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          padding: '32px',
        }}
      >
        <div style={{ width: '100%', maxWidth: 640 }}>
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <Spin indicator={<LoadingOutlined style={{ fontSize: 40 }} spin />} />
          </div>
          <h2 style={{ marginBottom: 8 }}>Caching domains and policy packages</h2>
          <p style={{ marginBottom: 24, color: '#666' }}>
            The first load prepares domains and packages now. Sections will continue warming in the background.
          </p>
          <div style={{ marginBottom: 20 }}>
            <div style={{ marginBottom: 8 }}>
              {getDomainProgressLabel()}
            </div>
            <Progress
              percent={getProgressPercent(
                cacheStatus.domains_progress.processed,
                cacheStatus.domains_progress.total
              )}
              status="active"
            />
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>
              Packages: {cacheStatus.packages_progress.processed} / {cacheStatus.packages_progress.total}
            </div>
            <Progress
              percent={getProgressPercent(
                cacheStatus.packages_progress.processed,
                cacheStatus.packages_progress.total
              )}
              status="active"
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.pageContainer}>
      {domainsError && (
        <Alert
          message="Error"
          description={domainsError}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Cache controls */}
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
        <Button
          onClick={handleRefreshCache}
          loading={cacheStatus.core_refreshing}
          disabled={cacheStatus.refreshing}
          icon={<ReloadOutlined />}
        >
          Refresh Cache
        </Button>
        {cacheStatus.domains_cached_at && (
          <span style={{ color: '#666' }}>
            Last cached: {new Date(cacheStatus.domains_cached_at).toLocaleString()}
          </span>
        )}
        {cacheStatus.is_empty && !cacheStatus.refreshing && (
          <Alert
            message="No cached data"
            description="Click Refresh to load from Check Point"
            type="warning"
            showIcon
          />
        )}
      </div>

      {(cacheStatus.core_refreshing || manualCoreRefreshing) && (
        <div
          style={{
            marginBottom: 16,
            padding: 16,
            border: '1px solid #f0f0f0',
            borderRadius: 12,
            background: '#fff',
          }}
        >
          <div style={{ marginBottom: 8, fontWeight: 600 }}>
            Refreshing domains and policy packages
          </div>
          {cacheStatus.domains_progress.total === 0 && cacheStatus.packages_progress.total === 0 && (
            <div
              style={{
                display: 'inline-block',
                marginBottom: 12,
                padding: '4px 10px',
                borderRadius: 999,
                fontSize: 12,
                color: '#1d4ed8',
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
              }}
            >
              Waiting for backend to start refresh...
            </div>
          )}
          <div style={{ marginBottom: 16, color: '#666' }}>
            {getDomainProgressLabel()}
          </div>
          <Progress
            percent={getProgressPercent(
              cacheStatus.domains_progress.processed,
              cacheStatus.domains_progress.total
            )}
            status="active"
            style={{ marginBottom: 16 }}
          />
          <div style={{ marginBottom: 16, color: '#666' }}>
            Packages: {cacheStatus.packages_progress.processed} / {cacheStatus.packages_progress.total}
          </div>
          <Progress
            percent={getProgressPercent(
              cacheStatus.packages_progress.processed,
              cacheStatus.packages_progress.total
            )}
            status="active"
          />
        </div>
      )}

      {cacheStatus.sections_refreshing && (
        <Alert
          message="Sections are warming in the background"
          description={
            `Processed ${cacheStatus.sections_progress.processed} of ${cacheStatus.sections_progress.total} packages. ` +
            'If you open a package whose sections are still missing, that package is refreshed immediately.'
          }
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <IpInputPanel
        sourcePool={sourcePool}
        destPool={destPool}
        servicesPool={servicesPool}
        usedSourceIps={usedSourceIps}
        usedDestIps={usedDestIps}
        onSourceChange={setSourcePool}
        onDestChange={setDestPool}
        onServicesChange={setServicesPool}
      />

      <button
        className={styles.addButton}
        onClick={handleAddRule}
      >
        <PlusOutlined /> Add Rule
      </button>

      <RulesTable
        rules={rulesForTable}
        domains={domainsForTable}
        availableServices={servicesForTable}
        availableSourceIps={sourceIpsForTable}
        availableDestIps={destIpsForTable}
        updateRule={handleRulesTableUpdate}
        handleClone={handleRulesTableClone}
        onDelete={handleRulesTableDelete}
        onFetchPackages={handleFetchPackagesForTable}
        onFetchSections={handleFetchSectionsForTable}
      />

      <div className={styles.submitSection}>
        <button
          className={styles.submitButton}
          onClick={handleSubmit}
          disabled={submitting || rules.length === 0}
        >
          {submitting ? 'Submitting...' : 'Submit Rules'}
        </button>
      </div>

      <Modal
        title="Unused IPs Detected"
        open={unusedIpsModal.visible}
        onOk={handleModalConfirm}
        onCancel={handleModalCancel}
        okText="Submit Anyway"
        cancelText="Go Back"
      >
        <p>The following IPs are not used in any rules:</p>
        <ul>
          {unusedIpsModal.unusedIps.map(ip => (
            <li key={ip}>{ip}</li>
          ))}
        </ul>
        <p>Do you want to submit anyway?</p>
      </Modal>

      <Modal
        title="Confirm Submission"
        open={submitConfirmModal}
        onOk={handleSubmitConfirm}
        onCancel={handleSubmitCancel}
        okText="Submit"
        cancelText="Cancel"
      >
        <p>Are you sure you want to submit {rules.length} rule(s)?</p>
      </Modal>
    </div>
  );
};

export default Domains;
