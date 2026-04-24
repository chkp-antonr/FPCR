import React, { useState, useEffect } from 'react';
import { Alert, Spin, message, Modal } from 'antd';
import { LoadingOutlined, PlusOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { domainsApi, packagesApi, topologyApi, rules2Api } from '../api/endpoints';
import { validateRules, hasUnusedIps } from '../utils/ruleValidator';
import { generatePredictions } from '../utils/predictionEngine';
import type { RuleRow, IpEntry, TopologyEntry, ServiceEntry, Prediction } from '../types';
import IpInputPanel from '../components/IpInputPanel';
import PredictionsPanel from '../components/PredictionsPanel';
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

const Domains2: React.FC = () => {
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

  // Topology state
  const [topology, setTopology] = useState<TopologyEntry[]>([]);
  const [topologyLoading, setTopologyLoading] = useState(false);
  const [topologyError, setTopologyError] = useState<string | null>(null);

  // Predictions state
  const [predictions, setPredictions] = useState<Prediction[]>([]);

  // Rules state
  const [rules, setRules] = useState<RuleRow[]>([]);

  // Loading states
  const [submitting, setSubmitting] = useState(false);

  // Modal state
  const [unusedIpsModal, setUnusedIpsModal] = useState<{
    visible: boolean;
    unusedIps: string[];
  }>({ visible: false, unusedIps: [] });

  const [submitConfirmModal, setSubmitConfirmModal] = useState(false);

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

  // Fetch topology when IPs change
  useEffect(() => {
    if (sourcePool.length === 0 && destPool.length === 0) {
      setTopology([]);
      setTopologyError(null);
      return;
    }

    const fetchTopology = async () => {
      setTopologyLoading(true);
      setTopologyError(null);
      try {
        const response = await topologyApi.getTopology();
        setTopology(response.topology || []);
      } catch (error) {
        setTopologyError('Failed to fetch topology');
        message.error('Failed to fetch topology');
      } finally {
        setTopologyLoading(false);
      }
    };

    const timer = setTimeout(fetchTopology, 500);
    return () => clearTimeout(timer);
  }, [sourcePool, destPool]);

  // Generate predictions from topology and pools
  useEffect(() => {
    if (topology.length === 0) {
      setPredictions([]);
      return;
    }

    const newPredictions = generatePredictions(sourcePool, destPool, topology);
    setPredictions(newPredictions);
  }, [topology, sourcePool, destPool]);

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
    } catch (error) {
      message.error('Failed to fetch packages');
      return [];
    }
  };

  const handleFetchSections = async (domainUid: string, pkgUid: string) => {
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

      message.success(`Loaded ${fetchedSections.length} sections`);
    } catch (error) {
      message.error('Failed to fetch sections');
    }
  };

  const handleClearPredictions = () => {
    setPredictions([]);
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

  // Handle drag drop from predictions to rule table
  const handleTableDrop = async (e: React.DragEvent, rule: import('../components/RulesTable').Rule) => {
    try {
      // Read prediction data from dataTransfer
      const predictionData = e.dataTransfer.getData('prediction');
      if (!predictionData) {
        message.warning('No prediction data found');
        return;
      }

      // Safely parse JSON with error handling
      let prediction: import('../types').Prediction;
      try {
        prediction = JSON.parse(predictionData) as import('../types').Prediction;
      } catch (parseError) {
        message.error('Invalid prediction data format');
        return;
      }

      // Validate prediction structure with null/undefined checks
      if (!prediction || typeof prediction !== 'object') {
        message.error('Invalid prediction structure');
        return;
      }

      // Validate required nested properties with optional chaining
      if (!prediction.ip?.original) {
        message.error('Prediction missing required IP information');
        return;
      }

      const updatedRule = { ...rule };
      const ipToAdd = prediction.ip.original;
      const targetField = prediction.source === 'source' ? 'source_ips' : 'dest_ips';

      // Smart-fill: set domain and package from first candidate (only if fields are empty)
      let fetchedPackagesForDomain: Package[] | null = null;
      let domainWithPackages: Domain | null = null;

      if (prediction.candidates?.length > 0) {
        const firstCandidate = prediction.candidates[0];

        const isNewDomain = updatedRule.domain !== firstCandidate.domain.name;

        if (firstCandidate?.domain?.name && !updatedRule.domain) {
          updatedRule.domain = firstCandidate.domain.name;

          // Load packages for this domain BEFORE updating rule
          const targetDomain = domains.find(d => d.name === firstCandidate.domain.name);
          if (targetDomain && isNewDomain && targetDomain.packages.length === 0) {
            fetchedPackagesForDomain = await handleFetchPackages(targetDomain.uid);
            // Create a local domain object with the fetched packages
            domainWithPackages = { ...targetDomain, packages: fetchedPackagesForDomain };
            // Also fetch sections for the predicted package
            if (firstCandidate?.package?.uid) {
              await handleFetchSections(targetDomain.uid, firstCandidate.package.uid);
            }
          } else if (targetDomain) {
            domainWithPackages = targetDomain;
          }
        }

        if (firstCandidate?.package?.name && !updatedRule.package) {
          updatedRule.package = firstCandidate.package.name;
        }
      }

      // Initialize array if needed
      if (!updatedRule[targetField]) {
        (updatedRule as any)[targetField] = [];
      }

      // Prevent duplicate IPs
      const currentArray = (updatedRule as any)[targetField] as string[];
      if (currentArray.includes(ipToAdd)) {
        message.warning(`IP ${ipToAdd} already exists in ${prediction.source === 'source' ? 'Source' : 'Destination'} IPs`);
        // Still update the rule with domain/package from prediction
        const ruleIndex = rules.findIndex(r => r.id === rule.uid);
        if (ruleIndex !== -1) {
          const updatedRules = [...rules];
          updatedRules[ruleIndex] = {
            ...rules[ruleIndex],
            domain: updatedRule.domain ? (domainWithPackages || domains.find(d => d.name === updatedRule.domain) || null) : null,
            package: updatedRule.package
              ? domainWithPackages?.packages.find(p => p.name === updatedRule.package)
                || domains.find(d => d.name === updatedRule.domain)?.packages.find(p => p.name === updatedRule.package)
                || null
              : null,
          };
          setRules(updatedRules);
        }
        return;
      }

      // Add IP to the appropriate array
      currentArray.push(ipToAdd);

      // Transform back to RuleRow and update
      const ruleIndex = rules.findIndex(r => r.id === rule.uid);
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
          // Also update domain and package from prediction - use domainWithPackages if available
          domain: updatedRule.domain ? (domainWithPackages || domains.find(d => d.name === updatedRule.domain) || null) : null,
          package: updatedRule.package
            ? domainWithPackages?.packages.find(p => p.name === updatedRule.package)
              || domains.find(d => d.name === updatedRule.domain)?.packages.find(p => p.name === updatedRule.package)
              || null
            : null,
        };
        setRules(updatedRules);
        message.success(`Prediction added to ${prediction.source === 'source' ? 'Source' : 'Destination'} IPs`);
      }
    } catch (error) {
      message.error('Failed to process drag-drop operation');
    }
  };

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

  // Handle prediction drag start - stub for future implementation
  const handlePredictionDragStart = (_prediction: Prediction) => {
    // Drag start handling is managed by the PredictionsPanel component
    // This stub is kept for interface compatibility
  };

  if (domainsLoading && domains.length === 0) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin indicator={<LoadingOutlined style={{ fontSize: 48 }} spin />} />
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

      {topologyLoading && (
        <div style={{ textAlign: 'center', margin: '24px 0' }}>
          <Spin tip="Loading topology..." />
        </div>
      )}

      {topologyError && (
        <Alert
          message="Topology Error"
          description={topologyError}
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}

      <PredictionsPanel
        predictions={predictions}
        onDragStart={handlePredictionDragStart}
        onClear={handleClearPredictions}
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
        onDrop={handleTableDrop}
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

export default Domains2;
