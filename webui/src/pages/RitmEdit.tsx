import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { message, Modal, Button, Spin, Card, Typography, Alert, Space, Steps, Collapse } from 'antd';
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { ritmApi, domainsApi, packagesApi } from '../api/endpoints';
import { RITM_STATUS, type RuleRow, type IpEntry, type ServiceEntry, type DomainInfo, type TryVerifyResponse } from '../types';
import { useAuth } from '../contexts/AuthContext';
import IpInputPanel from '../components/IpInputPanel';
import RulesTable from '../components/RulesTable';
import styles from '../styles/pages/ritm-edit.module.css';

const { Title, Text } = Typography;

export default function RitmEdit() {
  const { ritmNumber } = useParams<{ ritmNumber: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  // RITM state
  const [ritm, setRitm] = useState<{
    ritm_number: string;
    username_created: string;
    date_created: string;
    status: number;
    feedback?: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Pool state
  const [sourcePool, setSourcePool] = useState<IpEntry[]>([]);
  const [destPool, setDestPool] = useState<IpEntry[]>([]);
  const [servicesPool, setServicesPool] = useState<ServiceEntry[]>([]);

  // Rules state
  const [rules, setRules] = useState<RuleRow[]>([]);

  // Domains state
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [domainsLoaded, setDomainsLoaded] = useState(false);
  const [loadingPackageRules, setLoadingPackageRules] = useState<string[]>([]);
  const [loadingSectionRules, setLoadingSectionRules] = useState<string[]>([]);

  // Store loaded policies temporarily
  const [loadedPolicies, setLoadedPolicies] = useState<any[] | null>(null);

  // Modals
  const [submitModalVisible, setSubmitModalVisible] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Workflow state (plan → try & verify)
  type WorkflowStep = 'idle' | 'planned' | 'verified';
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>('idle');
  const [planning, setPlanning] = useState(false);
  const [verificationErrors, setVerificationErrors] = useState<string[]>([]);
  const [evidenceHtml, setEvidenceHtml] = useState<string | null>(null);
  const [evidenceYaml, setEvidenceYaml] = useState<string | null>(null);
  const [evidenceChanges, setEvidenceChanges] = useState<any>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const [tryVerifying, setTryVerifying] = useState(false);
  const [tryVerifyResult, setTryVerifyResult] = useState<TryVerifyResponse | null>(null);
  const [canRecreateEvidence, setCanRecreateEvidence] = useState(false);
  const [workflowLog, setWorkflowLog] = useState<Array<{ ts: string; text: string }>>([]);
  const [sessionHtml, setSessionHtml] = useState<string | null>(null);
  const [showSessionHtml, setShowSessionHtml] = useState(false);
  const [sessionHtmlLoading, setSessionHtmlLoading] = useState(false);

  // Load domains on mount
  useEffect(() => {
    const loadDomains = async () => {
      try {
        const response = await domainsApi.list();
        // Convert DomainItem[] to DomainInfo[]
        const domainInfo: DomainInfo[] = response.domains.map(d => ({
          name: d.name,
          uid: d.uid,
          packages: [],  // Packages will be loaded on demand via onFetchPackages
        }));
        setDomains(domainInfo);
        setDomainsLoaded(true);
      } catch (error) {
        console.error('Failed to load domains:', error);
      }
    };

    loadDomains();
  }, []);

  // Load RITM and policies on mount
  useEffect(() => {
    const loadRitm = async () => {
      try {
        setLoading(true);
        const response = await ritmApi.get(ritmNumber || '');
        setRitm({
          ...response.ritm,
          feedback: response.ritm.feedback || undefined,
        });

        // Load input pools
        if (response.ritm.source_ips) {
          setSourcePool(response.ritm.source_ips.map(ip => ({
            original: ip,
            type: 'ipv4' as const,
            normalized: ip,
          })));
        }
        if (response.ritm.dest_ips) {
          setDestPool(response.ritm.dest_ips.map(ip => ({
            original: ip,
            type: 'ipv4' as const,
            normalized: ip,
          })));
        }
        if (response.ritm.services) {
          setServicesPool(response.ritm.services.map(svc => ({
            original: svc,
            normalized: svc,
            type: 'named' as const,
          })));
        }

        // Restore workflow step if evidence sessions exist in DB (page reload / 2nd cycle recovery)
        try {
          const history = await ritmApi.getEvidenceHistory(ritmNumber || '');
          if (history.domains && history.domains.length > 0) {
            setWorkflowStep('verified');
            setCanRecreateEvidence(true);
            addWorkflowLog('Workflow restored: Try & Verify was already completed.');
          }
        } catch {
          // no evidence yet — leave workflowStep as 'idle'
        }

        // Auto-acquire editor lock when opening a WIP RITM (creation or after feedback)
        if (response.ritm.status === RITM_STATUS.WORK_IN_PROGRESS &&
            response.ritm.editor_locked_by !== user?.username) {
          try {
            await ritmApi.acquireEditorLock(ritmNumber || '');
          } catch (lockErr: any) {
            const detail = lockErr.response?.data?.detail;
            if (detail && detail !== 'RITM not found') {
              message.warning(`Could not acquire editor lock: ${detail}`);
            }
          }
        }

        // Store policies for later processing after domains are loaded
        if (response.policies && response.policies.length > 0) {
          setLoadedPolicies(response.policies);
        } else {
          setLoading(false);
        }

      } catch (error: any) {
        message.error(error.response?.data?.detail || 'Failed to load RITM');
        navigate('/');
        setLoading(false);
      }
    };

    loadRitm();
  }, [ritmNumber]);

  // After both domains and policies are loaded, process rules and load their packages/sections
  useEffect(() => {
    const processPolicies = async () => {
      if (!domainsLoaded || !loadedPolicies || loadedPolicies.length === 0) {
        if (domainsLoaded && (!loadedPolicies || loadedPolicies.length === 0)) {
          setLoading(false);
        }
        return;
      }

      // Build rule rows
      const ruleRows: RuleRow[] = loadedPolicies.map((policy, idx) => ({
        id: `policy-${policy.id || idx}`,
        sourceIps: policy.source_ips.map((ip: string) => ({
          original: ip,
          type: 'ipv4' as const,
          normalized: ip,
        })),
        destIps: policy.dest_ips.map((ip: string) => ({
          original: ip,
          type: 'ipv4' as const,
          normalized: ip,
        })),
        services: policy.services.map((svc: string) => ({
          original: svc,
          normalized: svc,
          type: 'named' as const,
        })),
        domain: { name: policy.domain_name, uid: policy.domain_uid },
        package: { name: policy.package_name, uid: policy.package_uid, access_layer: '' },
        section: policy.section_uid && policy.section_name ? {
          name: policy.section_name,
          uid: policy.section_uid,
          rulebase_range: [0, 0],
          rule_count: 0,
        } : null,
        position: {
          type: policy.position_type === 'custom' ? 'custom' : policy.position_type,
          custom_number: policy.position_number,
        },
        action: policy.action as 'accept' | 'drop',
        track: policy.track as 'log' | 'none',
        comments: policy.comments,
        rule_name: policy.rule_name,
      }));

      // Collect unique domains that need packages loaded
      const domainsNeedingPackages = new Map<string, string>(); // domainName -> domainUid
      const domainsNeedingSections = new Map<string, { packageName: string; packageUid: string }[]>(); // domainName -> packages

      for (const policy of loadedPolicies) {
        if (policy.domain_name && policy.domain_uid) {
          domainsNeedingPackages.set(policy.domain_name, policy.domain_uid);

          if (policy.package_name && policy.package_uid) {
            if (!domainsNeedingSections.has(policy.domain_name)) {
              domainsNeedingSections.set(policy.domain_name, []);
            }
            domainsNeedingSections.get(policy.domain_name)!.push({
              packageName: policy.package_name,
              packageUid: policy.package_uid,
            });
          }
        }
      }

      // Load packages for each unique domain
      const domainUpdates = new Map<string, DomainInfo>();
      for (const [domainName, domainUid] of domainsNeedingPackages) {
        try {
          const packagesResponse = await packagesApi.list(domainUid);
          const packagesWithSections = packagesResponse.packages.map(p => ({
            name: p.name,
            uid: p.uid,
            access_layer: p.access_layer,
            sections: [] as any[],
          }));

          // Load sections for packages that need them
          const packagesNeedingSections = domainsNeedingSections.get(domainName) || [];
          for (const pkgNeedingSections of packagesNeedingSections) {
            const pkgIndex = packagesWithSections.findIndex(p => p.uid === pkgNeedingSections.packageUid);
            if (pkgIndex !== -1) {
              try {
                const sectionsResponse = await packagesApi.getSections(domainUid, pkgNeedingSections.packageUid);
                packagesWithSections[pkgIndex].sections = sectionsResponse.sections;
              } catch (error) {
                console.error(`Failed to load sections for ${pkgNeedingSections.packageName}:`, error);
              }
            }
          }

          domainUpdates.set(domainName, {
            name: domainName,
            uid: domainUid,
            packages: packagesWithSections,
          });
        } catch (error) {
          console.error(`Failed to load packages for domain ${domainName}:`, error);
        }
      }

      // Update domains with loaded packages
      if (domainUpdates.size > 0) {
        setDomains(prev => prev.map(d => {
          const updated = domainUpdates.get(d.name);
          return updated ? updated : d;
        }));
      }

      setRules(ruleRows);
      setLoadedPolicies(null); // Clear the temporary state
      setLoading(false);
    };

    processPolicies();
  }, [domainsLoaded, loadedPolicies]);

  // Auto-save policies when rules change (debounced)
  useEffect(() => {
    if (rules.length > 0 && ritm && ritm.status === RITM_STATUS.WORK_IN_PROGRESS) {
      const timer = setTimeout(() => {
        savePolicies();
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [rules, ritm, ritm?.status]);

  // Auto-save pools when they change (debounced)
  useEffect(() => {
    if (ritm && ritm.status === RITM_STATUS.WORK_IN_PROGRESS) {
      const hasPools = sourcePool.length > 0 || destPool.length > 0 || servicesPool.length > 0;
      if (hasPools) {
        const timer = setTimeout(() => {
          savePools();
        }, 1000);
        return () => clearTimeout(timer);
      }
    }
  }, [sourcePool, destPool, servicesPool, ritm, ritm?.status]);

  const savePolicies = async () => {
    try {
      const policyItems = rules.map(rule => ({
        ritm_number: ritmNumber || '',
        comments: rule.comments || `${ritmNumber} #${new Date().toISOString().split('T')[0]}#`,
        rule_name: rule.rule_name || ritmNumber || '',
        domain_uid: rule.domain?.uid || '',
        domain_name: rule.domain?.name || '',
        package_uid: rule.package?.uid || '',
        package_name: rule.package?.name || '',
        section_uid: rule.section?.uid || null,
        section_name: rule.section?.name || null,
        position_type: rule.position.type,
        position_number: rule.position.custom_number,
        action: rule.action,
        track: rule.track,
        source_ips: rule.sourceIps.map(ip => ip.normalized),
        dest_ips: rule.destIps.map(ip => ip.normalized),
        services: rule.services.map(s => s.normalized),
      }));

      await ritmApi.savePolicy(ritmNumber || '', policyItems);
    } catch (error) {
      console.error('Failed to save policies:', error);
    }
  };

  const savePools = async () => {
    try {
      await ritmApi.savePools(ritmNumber || '', {
        source_ips: sourcePool.map(ip => ip.normalized),
        dest_ips: destPool.map(ip => ip.normalized),
        services: servicesPool.map(s => s.normalized),
      });
    } catch (error) {
      console.error('Failed to save pools:', error);
    }
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
      comments: `${ritmNumber} #${new Date().toISOString().split('T')[0]}#`,
      rule_name: ritmNumber || '',
    };
    setRules([...rules, newRule]);
  };

  const handleSubmitForApproval = async () => {
    if (rules.length === 0) {
      message.warning('Please add at least one rule before submitting');
      return;
    }

    try {
      setSaving(true);
      setSubmitError(null);
      const hide = message.loading('Disabling rules and publishing...', 0);
      try {
        await ritmApi.submitForApproval(ritmNumber || '');
      } finally {
        hide();
      }
      message.success('RITM submitted for approval — rules disabled and published');
      setSubmitModalVisible(false);
      navigate('/');
    } catch (error: any) {
      setSubmitError(error.response?.data?.detail || 'Failed to submit for approval');
    } finally {
      setSaving(false);
    }
  };

  const handleOverrideAndSubmit = async () => {
    try {
      setSaving(true);
      setSubmitError(null);
      await ritmApi.acquireEditorLock(ritmNumber || '');
      const hide = message.loading('Disabling rules and publishing...', 0);
      try {
        await ritmApi.submitForApproval(ritmNumber || '');
      } finally {
        hide();
      }
      message.success('RITM submitted for approval');
      setSubmitModalVisible(false);
      navigate('/');
    } catch (error: any) {
      setSubmitError(error.response?.data?.detail || 'Failed to override and submit');
    } finally {
      setSaving(false);
    }
  };

  const extractErrorMsg = (error: any, fallback: string): string => {
    if (error.response?.data) {
      if (typeof error.response.data === 'string') return error.response.data;
      if (error.response.data.detail) {
        const d = error.response.data.detail;
        if (typeof d === 'string') return d;
        if (Array.isArray(d)) {
          return d.map((e: any) => {
            if (typeof e === 'string') return e;
            if (e.msg) return `${e.loc?.join('.') || 'field'}: ${e.msg}`;
            return JSON.stringify(e);
          }).join('\n');
        }
      }
    }
    return error.message || fallback;
  };

  const addWorkflowLog = (text: string) => {
    const ts = new Date().toLocaleTimeString();
    setWorkflowLog(prev => [{ ts, text }, ...prev].slice(0, 30));
    console.info(`[workflow ${ts}] ${text}`);
  };

  const handleGeneratePlan = async () => {
    setPlanning(true);
    setVerificationErrors([]);
    setEvidenceHtml(null);
    setShowEvidence(false);
    setTryVerifyResult(null);
    addWorkflowLog('Generating YAML plan...');
    const hide = message.loading('Generating YAML plan...', 0);
    try {
      const response = await ritmApi.generatePlanYaml(ritmNumber || '');
      setEvidenceYaml(response.yaml);
      setEvidenceChanges(response.changes);
      setShowEvidence(true);
      setWorkflowStep('planned');
      addWorkflowLog('YAML plan generated and ready for review.');
      message.success({ content: 'YAML plan ready — review then try & verify.', key: 'wf', duration: 4 });
    } catch (error: any) {
      const msg = extractErrorMsg(error, 'Plan generation failed');
      setVerificationErrors([msg]);
      addWorkflowLog(`Plan generation failed: ${msg}`);
      message.error({ content: 'Plan generation failed.', key: 'wf', duration: 5 });
    } finally {
      hide();
      setPlanning(false);
    }
  };

  const handleTryVerify = async () => {
    setTryVerifying(true);
    setVerificationErrors([]);
    setEvidenceHtml(null);
    setShowEvidence(false);
    setTryVerifyResult(null);
    addWorkflowLog('Try & Verify started...');
    const hide = message.loading('Try & Verify in progress...', 0);
    try {
      const response = await ritmApi.tryVerifyRitm(ritmNumber || '');
      setTryVerifyResult(response);
      setWorkflowStep('verified');

      // Log per-package results
      response.results.forEach(r => {
        const statusMsg = {
          success: `✓ ${r.domain} / ${r.package}: SUCCESS (${r.rules_created} rules, ${r.objects_created} objects)`,
          skipped: `⊘ ${r.domain} / ${r.package}: SKIPPED (pre-verify failed)`,
          create_failed: `✗ ${r.domain} / ${r.package}: CREATE FAILED`,
          verify_failed: `✗ ${r.domain} / ${r.package}: VERIFY FAILED (rules rolled back)`,
        }[r.status] || `${r.domain} / ${r.package}: ${r.status}`;

        addWorkflowLog(statusMsg);

        if (r.errors.length > 0) {
          r.errors.forEach(err => addWorkflowLog(`  Error: ${err}`));
        }
      });

      if (response.published) {
        addWorkflowLog('Changes published successfully');
      }

      if (response.evidence_html) {
        setSessionHtml(response.evidence_html);
        setCanRecreateEvidence(true);
      }

      if (response.results.some(r => r.status === 'success')) {
        message.success({
          content: `Try & Verify complete. ${response.results.filter(r => r.status === 'success').length} package(s) succeeded.`,
          key: 'wf',
          duration: 5,
        });
      } else {
        message.warning({
          content: 'Try & Verify failed. All packages were skipped or had errors.',
          key: 'wf',
          duration: 5,
        });
      }
    } catch (error: any) {
      const msg = extractErrorMsg(error, 'Try & Verify failed');
      setVerificationErrors(prev => [...prev, msg]);
      addWorkflowLog(`Try & Verify failed: ${msg}`);
      message.error({ content: 'Try & Verify failed.', key: 'wf', duration: 5 });
    } finally {
      hide();
      setTryVerifying(false);
    }
  };

  const handleDownloadSessionPdf = async () => {
    if (!ritmNumber) return;

    try {
      const token = localStorage.getItem('token') || '';
      const response = await fetch(`/api/v1/ritm/${ritmNumber}/session-pdf?evidence=1`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || 'Failed to download PDF');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${ritmNumber}_evidence1.pdf`;
      a.click();
      URL.revokeObjectURL(url);

      message.success('Evidence PDF downloaded successfully');
    } catch (error: any) {
      message.error(error.message || 'Failed to download PDF');
    }
  };

  const handleToggleSessionHtml = async () => {
    if (!ritmNumber) return;

    if (showSessionHtml) {
      setShowSessionHtml(false);
      return;
    }

    if (sessionHtml) {
      setShowSessionHtml(true);
      return;
    }

    try {
      setSessionHtmlLoading(true);
      const html = await ritmApi.getSessionEvidenceHtml(ritmNumber, 1);
      setSessionHtml(html);
      setShowSessionHtml(true);
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Failed to load Evidence HTML');
    } finally {
      setSessionHtmlLoading(false);
    }
  };

  const handleResetWorkflow = () => {
    setWorkflowStep('idle');
    setEvidenceYaml(null);
    setEvidenceChanges(null);
    setShowEvidence(false);
    setTryVerifyResult(null);
    setVerificationErrors([]);
    setSessionHtml(null);
    setShowSessionHtml(false);
    addWorkflowLog('Workflow reset.');
  };

  const handleRecreateEvidence = async () => {
    if (!ritmNumber) return;

    addWorkflowLog('Re-creating evidence from current session state...');
    const hide = message.loading('Re-creating evidence...', 0);
    try {
      const response = await ritmApi.recreateEvidence(ritmNumber);
      setSessionHtml(response.html);
      setShowSessionHtml(true);

      // Also update tryVerifyResult so evidence shows in SessionChangesDisplay
      if (tryVerifyResult) {
        setTryVerifyResult({
          ...tryVerifyResult,
          session_changes: response.changes || {},
        });
      } else {
        // Create a minimal tryVerifyResult if it doesn't exist
        setTryVerifyResult({
          results: [],
          evidence_pdf: null,
          evidence_html: response.html,
          published: false,
          session_changes: response.changes || {},
        });
      }

      addWorkflowLog('Evidence re-created successfully');
      message.success('Evidence re-created from current Check Point state');
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Failed to re-create evidence');
    } finally {
      hide();
    }
  };

  const handleRulesTableUpdate = (updatedRule: any) => {
    const ruleIndex = rules.findIndex(r => r.id === updatedRule.uid);
    if (ruleIndex !== -1) {
      const existingRule = rules[ruleIndex];
      const updatedRules = [...rules];
      updatedRules[ruleIndex] = {
        ...existingRule,
        sourceIps: (updatedRule.source_ips || []).map((ip: string) => ({
          original: ip,
          type: 'ipv4' as const,
          normalized: ip,
        })),
        destIps: (updatedRule.dest_ips || []).map((ip: string) => ({
          original: ip,
          type: 'ipv4' as const,
          normalized: ip,
        })),
        services: (updatedRule.services || []).map((s: string) => ({
          original: s,
          normalized: s,
          type: 'named' as const,
        })),
        // Resolve domain/package/section from name strings back to typed objects
        domain: (() => {
          if (updatedRule.domain === undefined) return existingRule.domain;
          if (!updatedRule.domain) return null;
          const d = domains.find(d => d.name === updatedRule.domain);
          return d ? { name: d.name, uid: d.uid } : existingRule.domain;
        })(),
        package: (() => {
          if (updatedRule.package === undefined) return existingRule.package;
          if (!updatedRule.package) return null;
          const domainName = updatedRule.domain ?? existingRule.domain?.name;
          const d = domains.find(d => d.name === domainName);
          const p = d?.packages.find(p => p.name === updatedRule.package);
          if (!p?.uid) return existingRule.package;
          return { name: p.name, uid: p.uid, access_layer: p.access_layer ?? '' };
        })(),
        section: (() => {
          if (updatedRule.section === undefined) return existingRule.section;
          if (!updatedRule.section) return null;
          const domainName = updatedRule.domain ?? existingRule.domain?.name;
          const pkgName = updatedRule.package ?? existingRule.package?.name;
          const d = domains.find(d => d.name === domainName);
          const p = d?.packages.find(p => p.name === pkgName);
          const s = p?.sections?.find((s: any) => s.name === updatedRule.section);
          return s ? { name: s.name, uid: s.uid, rulebase_range: s.rulebase_range, rule_count: s.rule_count } : existingRule.section;
        })(),
        position: updatedRule.position === 'top' || updatedRule.position === 'bottom'
          ? { type: updatedRule.position as 'top' | 'bottom' }
          : {
              type: 'custom',
              custom_number: updatedRule.position_top || updatedRule.position_bottom ? Number(updatedRule.position_top || updatedRule.position_bottom) : undefined,
            },
        action: (updatedRule.action || 'accept') as 'accept' | 'drop',
        track: (updatedRule.track === 'Log' ? 'log' : 'none') as 'log' | 'none',
        comments: updatedRule.comments,
        rule_name: updatedRule.rule_name,
      };
      setRules(updatedRules);
    }
  };

  const handleRulesTableClone = (rule: any) => {
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
        comments: `${ritmNumber} #${new Date().toISOString().split('T')[0]}#`,
        rule_name: ritmNumber || '',
      };
      setRules([...rules, newRule]);
      message.success('Rule cloned successfully');
    }
  };

  const handleRulesTableDelete = (rule: any) => {
    const updatedRules = rules.filter(r => r.id !== rule.uid);
    setRules(updatedRules);
    message.success('Rule deleted successfully');
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" tip="Loading RITM..." />
      </div>
    );
  }

  if (!ritm) {
    return (
      <div style={{ padding: 24 }}>
        <Alert message="RITM not found" type="error" showIcon />
      </div>
    );
  }

  // Only creator can edit (or if returned with feedback)
  const currentUsername = user?.username || '';
  if (ritm.username_created !== currentUsername && !ritm.feedback) {
    return (
      <div style={{ padding: 24 }}>
        <Alert message="You can only view your own RITMs" type="warning" showIcon />
      </div>
    );
  }

  // Transform IP pools to string arrays for RulesTable
  const sourceIpsForTable = sourcePool.map(ip => ip.normalized);
  const destIpsForTable = destPool.map(ip => ip.normalized);
  const servicesForTable = servicesPool.map(svc => svc.normalized);

  const usedSourceIps: string[] = [];
  const usedDestIps: string[] = [];
  rules.forEach(rule => {
    rule.sourceIps?.forEach(ip => usedSourceIps.push(ip.normalized.toLowerCase()));
    rule.destIps?.forEach(ip => usedDestIps.push(ip.normalized.toLowerCase()));
  });

  // Transform RuleRow to RulesTable.Rule format
  const rulesForTable: any[] = rules.map(rule => ({
    key: rule.id,
    uid: rule.id,
    source_ips: rule.sourceIps.map(ip => ip.normalized),
    dest_ips: rule.destIps.map(ip => ip.normalized),
    services: rule.services.map(svc => svc.normalized),
    domain: rule.domain?.name,
    package: rule.package?.name,
    section: rule.section?.name,
    position: rule.position.type === 'custom' ? 'before' : rule.position.type,
    position_top: rule.position.custom_number?.toString(),
    position_bottom: rule.position.custom_number?.toString(),
    action: rule.action,
    track: rule.track === 'log' ? 'Log' : 'None',
    comments: rule.comments,
    rule_name: rule.rule_name,
  }));

  const canEdit = ritm.status === RITM_STATUS.WORK_IN_PROGRESS;

  return (
    <div className={styles.pageContainer}>
      <div style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          Back to Dashboard
        </Button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Title level={3}>RITM: {ritmNumber}</Title>
        <Space direction="vertical" size="small">
          <Text type="secondary">Created by: {ritm.username_created}</Text>
          <Text type="secondary">Date: {new Date(ritm.date_created).toLocaleString()}</Text>
          <Text type="secondary">Status: {
            ritm.status === RITM_STATUS.WORK_IN_PROGRESS ? 'Work in Progress' :
            ritm.status === RITM_STATUS.READY_FOR_APPROVAL ? 'Ready for Approval' :
            ritm.status === RITM_STATUS.APPROVED ? 'Approved' :
            ritm.status === RITM_STATUS.COMPLETED ? 'Completed' : 'Unknown'
          }</Text>
          {ritm.feedback && (
            <Text type="warning">Feedback: {ritm.feedback}</Text>
          )}
        </Space>
      </Card>

      {!canEdit && (
        <Alert
          message="This RITM is being reviewed or has been approved. View only mode."
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {ritm.feedback && (
        <Alert
          message={`This RITM was returned with feedback: "${ritm.feedback}"`}
          type="warning"
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

      {canEdit && (
        <button
          className={styles.addButton}
          onClick={handleAddRule}
          disabled={saving}
        >
          <PlusOutlined /> Add Rule
        </button>
      )}

      <RulesTable
        rules={rulesForTable}
        domains={domains}
        loadingPackageRules={loadingPackageRules}
        loadingSectionRules={loadingSectionRules}
        availableServices={servicesForTable}
        availableSourceIps={sourceIpsForTable}
        availableDestIps={destIpsForTable}
        updateRule={handleRulesTableUpdate}
        handleClone={handleRulesTableClone}
        onDelete={handleRulesTableDelete}
        onFetchPackages={async (domainName: string, rule?: any) => {
          if (rule?.uid) {
            setLoadingPackageRules(prev => (prev.includes(rule.uid) ? prev : [...prev, rule.uid]));
          }

          // Find domain UID by name
          const domain = domains.find(d => d.name === domainName);
          if (domain) {
            try {
              const response = await packagesApi.list(domain.uid);
              console.log(`Loaded ${response.packages.length} packages for domain ${domainName}`);
              // Update the domain with its packages
              setDomains(prev => prev.map(d =>
                d.name === domainName
                  ? { ...d, packages: response.packages.map(p => ({
                      name: p.name,
                      uid: p.uid,
                      access_layer: p.access_layer,
                      sections: [],  // Sections will be loaded on demand
                    })) }
                  : d
              ));
            } catch (error) {
              console.error('Failed to load packages:', error);
              message.error(`Failed to load packages: ${error instanceof Error ? error.message : 'Unknown error'}`);
            } finally {
              if (rule?.uid) {
                setLoadingPackageRules(prev => prev.filter(id => id !== rule.uid));
              }
            }
          } else if (rule?.uid) {
            setLoadingPackageRules(prev => prev.filter(id => id !== rule.uid));
          }
        }}
        onFetchSections={async (domainName: string, packageName: string, rule?: any) => {
          if (rule?.uid) {
            setLoadingSectionRules(prev => (prev.includes(rule.uid) ? prev : [...prev, rule.uid]));
          }

          // Find domain UID by name
          const domain = domains.find(d => d.name === domainName);
          if (domain) {
            // Find package UID by name within the domain
            const packageInfo = domain.packages.find(p => p.name === packageName);
            if (packageInfo?.uid) {
              try {
                const response = await packagesApi.getSections(domain.uid, packageInfo.uid);
                console.log(`Loaded ${response.sections.length} sections for package ${packageName}`);
                // Update the package with its sections
                setDomains(prev => prev.map(d => {
                  if (d.name === domainName) {
                    return {
                      ...d,
                      packages: d.packages.map(p =>
                        p.name === packageName
                          ? { ...p, sections: response.sections }
                          : p
                      ),
                    };
                  }
                  return d;
                }));
              } catch (error) {
                console.error('Failed to load sections:', error);
                message.error(`Failed to load sections: ${error instanceof Error ? error.message : 'Unknown error'}`);
              } finally {
                if (rule?.uid) {
                  setLoadingSectionRules(prev => prev.filter(id => id !== rule.uid));
                }
              }
            } else if (rule?.uid) {
              setLoadingSectionRules(prev => prev.filter(id => id !== rule.uid));
            }
          } else if (rule?.uid) {
            setLoadingSectionRules(prev => prev.filter(id => id !== rule.uid));
          }
        }}
        disabled={!canEdit || saving}
      />

      {/* Evidence Display */}
      {showEvidence && (evidenceHtml || evidenceYaml || evidenceChanges) && (
        <Card
          title="Planned Changes"
          style={{ marginBottom: 16 }}
          extra={
            <Space>
              {evidenceYaml && (
                <Button
                  size="small"
                  onClick={async () => {
                    await navigator.clipboard.writeText(evidenceYaml);
                    message.success('YAML copied to clipboard');
                  }}
                >
                  Copy YAML
                </Button>
              )}
              {evidenceYaml && (
                <Button
                  size="small"
                  onClick={() => {
                    const blob = new Blob([evidenceYaml!], { type: 'text/yaml' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${ritmNumber}_evidence.yaml`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download YAML
                </Button>
              )}
              {evidenceHtml && (
                <Button
                  size="small"
                  onClick={() => {
                    const blob = new Blob([evidenceHtml!], { type: 'text/html' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${ritmNumber}_evidence.html`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download HTML
                </Button>
              )}
              <Button
                size="small"
                onClick={() => setShowEvidence(false)}
              >
                Close
              </Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }}>

            {/* YAML Preview */}
            {evidenceYaml && (
              <div>
                <Text strong>Planned CPCRUD YAML:</Text>
                <pre style={{
                  background: '#f5f5f5',
                  padding: 8,
                  borderRadius: 4,
                  maxHeight: 300,
                  overflow: 'auto',
                  fontSize: '0.9em'
                }}>
                  {evidenceYaml}
                </pre>
              </div>
            )}

          </Space>
        </Card>
      )}

      {/* Errors Display */}
      {verificationErrors.length > 0 && (
        <Card
          title={<Text type="danger">Verification Errors</Text>}
          style={{ marginBottom: 16 }}
          extra={
            <Space>
              <Button
                size="small"
                onClick={() => {
                  const text = verificationErrors.join('\n');
                  navigator.clipboard.writeText(text);
                  message.success('Errors copied to clipboard');
                }}
              >
                Copy to Clipboard
              </Button>
              <Button
                size="small"
                onClick={() => {
                  const text = verificationErrors.join('\n');
                  const blob = new Blob([text], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `${ritmNumber}_errors.txt`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Download
              </Button>
              <Button
                size="small"
                danger
                onClick={() => setVerificationErrors([])}
              >
                Clear
              </Button>
            </Space>
          }
        >
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {verificationErrors.map((error, idx) => (
              <li key={idx}>
                <Text type="danger">{error}</Text>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {canEdit && (
        <div className={styles.actionsSection}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {/* Multi-step workflow card */}
            <Card size="small">
              <Steps
                current={
                  workflowStep === 'idle' ? 0
                  : workflowStep === 'planned' ? 1
                  : 2
                }
                size="small"
                style={{ marginBottom: 16 }}
                items={[
                  { title: 'Plan' },
                  { title: 'Try & Verify' },
                ]}
              />

              {workflowStep === 'idle' && (
                <Button
                  type="primary"
                  onClick={handleGeneratePlan}
                  disabled={planning || saving || rules.length === 0}
                  loading={planning}
                  block
                >
                  Generate YAML Plan
                </Button>
              )}

              {workflowStep === 'planned' && (
                <Space style={{ width: '100%' }} direction="vertical">
                  <Text type="secondary">
                    Review the planned changes above, then run Try & Verify.
                  </Text>
                  <Space>
                    <Button
                      type="primary"
                      onClick={handleTryVerify}
                      disabled={tryVerifying || saving}
                      loading={tryVerifying}
                    >
                      Try & Verify
                    </Button>
                    <Button onClick={handleResetWorkflow}>Re-plan</Button>
                  </Space>
                </Space>
              )}

              {workflowStep === 'verified' && (
                <Space style={{ width: '100%' }} direction="vertical">
                  {tryVerifyResult && (
                    <Alert
                      type={tryVerifyResult.results.some(r => r.status === 'success') ? 'success' : 'warning'}
                      message={
                        tryVerifyResult.results.some(r => r.status === 'success')
                          ? `Try & Verify complete - ${tryVerifyResult.results.filter(r => r.status === 'success').length} package(s) succeeded`
                          : 'Try & Verify completed with errors'
                      }
                      showIcon
                    />
                  )}

                  {/* Show per-package results */}
                  {tryVerifyResult && tryVerifyResult.results.map(r => (
                    <div key={r.package} style={{ fontSize: '0.9em' }}>
                      <Text type={
                        r.status === 'success' ? 'success' :
                        r.status === 'skipped' ? 'secondary' :
                        'danger'
                      }>
                        {r.domain} / {r.package}: {r.status.toUpperCase()}
                        {r.rules_created > 0 && ` (${r.rules_created} rules, ${r.objects_created} objects)`}
                      </Text>
                      {r.errors.length > 0 && (
                        <ul style={{ margin: '4px 0 0 20', padding: 0 }}>
                          {r.errors.map((err, i) => (
                            <li key={i}><Text type="danger">{err}</Text></li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}

                  {canRecreateEvidence && (
                    <Button size="small" onClick={handleRecreateEvidence}>
                      Re-create Evidence
                    </Button>
                  )}

                  <Button size="small" onClick={handleResetWorkflow}>Reset workflow</Button>
                </Space>
              )}
            </Card>

            <Card
              size="small"
              title="Workflow Activity"
              extra={
                <Button
                  size="small"
                  onClick={() => setWorkflowLog([])}
                  disabled={workflowLog.length === 0}
                >
                  Clear
                </Button>
              }
            >
              {workflowLog.length === 0 ? (
                <Text type="secondary">No activity yet.</Text>
              ) : (
                <ul style={{ margin: 0, paddingLeft: 18, maxHeight: 180, overflowY: 'auto' }}>
                  {workflowLog.map((entry, idx) => (
                    <li key={`${entry.ts}-${idx}`}>
                      <Text style={{ fontSize: '0.9em' }}>
                        [{entry.ts}] {entry.text}
                      </Text>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            {/* Session changes display for try-verify results */}
            {tryVerifyResult && tryVerifyResult.session_changes != null && (
              <Card
                size="small"
                title="Session Changes"
                style={{ marginBottom: 0 }}
              >
                <Collapse
                  size="small"
                  items={[{
                    key: 'changes',
                    label: 'Session Changes (show-changes)',
                    extra: (
                      <Space size="small" onClick={e => e.stopPropagation()}>
                        <Button
                          size="small"
                          onClick={() => {
                            navigator.clipboard.writeText(JSON.stringify(tryVerifyResult.session_changes, null, 2));
                            message.success('Copied to clipboard');
                          }}
                        >Copy</Button>
                        <Button
                          size="small"
                          onClick={() => {
                            const blob = new Blob([JSON.stringify(tryVerifyResult.session_changes, null, 2)], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `${ritmNumber}_changes.json`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }}
                        >Download JSON</Button>
                        <Button
                          size="small"
                          type="primary"
                          onClick={handleDownloadSessionPdf}
                        >Download PDF</Button>
                        <Button
                          size="small"
                          onClick={handleRecreateEvidence}
                        >Regenerate Evidence</Button>
                        <Button
                          size="small"
                          onClick={handleToggleSessionHtml}
                          loading={sessionHtmlLoading}
                        >
                          {showSessionHtml ? 'Hide Evidence HTML' : 'Show Evidence HTML'}
                        </Button>
                      </Space>
                    ),
                    children: (
                      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                        <SessionChangesDisplay sessionChanges={tryVerifyResult.session_changes} />
                        {showSessionHtml && sessionHtml && (
                          <iframe
                            title="Evidence HTML Preview"
                            srcDoc={sessionHtml}
                            sandbox="allow-same-origin"
                            style={{
                              width: '100%',
                              minHeight: 650,
                              border: '1px solid #d9d9d9',
                              borderRadius: 8,
                              backgroundColor: '#fff',
                            }}
                          />
                        )}
                      </Space>
                    ),
                  }]}
                />
              </Card>
            )}

            {/* Submit Section */}
            <div className={styles.submitSection}>
              <button
                className={styles.submitButton}
                onClick={() => setSubmitModalVisible(true)}
                disabled={saving || rules.length === 0 || workflowStep !== 'verified'}
              >
                {saving ? 'Saving...' : 'Submit for Approval'}
              </button>
              {workflowStep !== 'verified' && rules.length > 0 && (
                <Text type="warning" style={{ fontSize: '0.9em' }}>
                  Complete all workflow steps before submitting
                </Text>
              )}
            </div>
          </Space>
        </div>
      )}

      <Modal
        title="Submit for Approval"
        open={submitModalVisible}
        onOk={handleSubmitForApproval}
        onCancel={() => { setSubmitModalVisible(false); setSubmitError(null); }}
        okText="Submit"
        cancelText="Cancel"
        confirmLoading={saving}
      >
        <p>Are you sure you want to submit this RITM for approval?</p>
        <p>This will save all rules and allow other users to review and approve them.</p>
        {submitError && (
          <Alert
            type="error"
            message={submitError}
            style={{ marginTop: 12 }}
            action={
              <Button size="small" danger onClick={handleOverrideAndSubmit} loading={saving}>
                Override
              </Button>
            }
          />
        )}
      </Modal>
    </div>
  );
}

// Component to display session changes in visual format
function SessionChangesDisplay({ sessionChanges }: { sessionChanges: any }) {
  if (!sessionChanges) return null;

  const domainChanges = sessionChanges.domain_changes || {};
  const domains = Object.keys(domainChanges);

  if (domains.length === 0) {
    return <Text type="secondary">No changes recorded</Text>;
  }

  return (
    <div style={{ fontSize: '0.9em' }}>
      {domains.map((domainName) => {
        const domainData = domainChanges[domainName];
        const tasks = domainData.tasks || [];

        return (
          <div key={domainName} style={{ marginBottom: 16 }}>
            <Title level={5} style={{ margin: '8px 0', color: '#0066cc' }}>
              Domain: {domainName}
            </Title>

            {tasks.map((task: any, taskIdx: number) => {
              const taskDetails = task['task-details'] || [];

              return taskDetails.map((detail: any, detailIdx: number) => {
                const changes = detail.changes || [];

                return changes.map((change: any, changeIdx: number) => {
                  const operations = change.operations || {};
                  const addedObjects = operations['added-objects'] || [];
                  const modifiedObjects = operations['modified-objects'] || [];
                  const deletedObjects = operations['deleted-objects'] || [];

                  // Separate rules from objects
                  const rules = addedObjects.filter((obj: any) => obj.type === 'access-rule');
                  const objects = {
                    added: addedObjects.filter((obj: any) => obj.type !== 'access-rule'),
                    modified: modifiedObjects,
                    deleted: deletedObjects,
                  };

                  const looksLikeUid = (value: string): boolean => (
                    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
                  );

                  const getString = (value: any): string | null => (
                    typeof value === 'string' && value.trim() ? value.trim() : null
                  );

                  const resolvePackageName = (rule: any): string => {
                    const candidates = [
                      rule.package,
                      rule['package-name'],
                      rule['policy-package'],
                      rule['rulebase-name'],
                      rule.rulebase,
                    ];
                    for (const candidate of candidates) {
                      const value = getString(candidate);
                      if (value) return value;
                    }
                    return 'Standard';
                  };

                  const resolveSectionName = (rule: any): string => {
                    const layerObjName = getString(rule.layer?.name);
                    if (layerObjName) return layerObjName;

                    const candidates = [
                      rule['layer-name'],
                      rule.layer_name,
                      rule['section-name'],
                      rule.section_name,
                      rule['access-section-name'],
                      rule['access-section'],
                      rule.layer,
                    ];

                    for (const candidate of candidates) {
                      const value = getString(candidate);
                      if (!value) continue;
                      if (!looksLikeUid(value)) return value;
                    }

                    return 'Rules';
                  };

                  const rulesByPackage = new Map<string, any[]>();
                  rules.forEach((rule: any) => {
                    const pkg = resolvePackageName(rule);
                    if (!rulesByPackage.has(pkg)) rulesByPackage.set(pkg, []);
                    rulesByPackage.get(pkg)!.push(rule);
                  });

                  const renderRefList = (items: any[] | undefined): string => {
                    if (!Array.isArray(items) || items.length === 0) return '-';
                    const rendered = items.map((item: any) => {
                      if (typeof item === 'string') return item;
                      if (item && typeof item === 'object') return item.name || item.uid || '';
                      return '';
                    }).filter(Boolean);
                    return rendered.length > 0 ? rendered.join(', ') : '-';
                  };

                  return (
                    <div key={`${taskIdx}-${detailIdx}-${changeIdx}`} style={{ marginLeft: 16 }}>
                      {/* Rules Table */}
                      {rules.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                          {Array.from(rulesByPackage.entries()).map(([packageName, packageRules], packageIdx) => {
                            const rulesBySection = new Map<string, any[]>();
                            packageRules.forEach((rule: any) => {
                              const section = resolveSectionName(rule);
                              if (!rulesBySection.has(section)) rulesBySection.set(section, []);
                              rulesBySection.get(section)!.push(rule);
                            });

                            let zebraIndex = 0;

                            return (
                              <div key={`${packageName}-${packageIdx}`} style={{ marginBottom: 10 }}>
                                <div
                                  style={{
                                    background: '#e6f2ff',
                                    borderLeft: '4px solid #0066cc',
                                    padding: '5px 10px',
                                    marginBottom: 6,
                                  }}
                                >
                                  Package: {packageName}
                                </div>

                                <table
                                  style={{
                                    width: '100%',
                                    borderCollapse: 'collapse',
                                    fontSize: '0.85em',
                                  }}
                                >
                                  <thead>
                                    <tr style={{ background: '#2e3f58', borderBottom: '2px solid #1a2639' }}>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Rule No.</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Name</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Source</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Destination</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Service</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Action</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Track</th>
                                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#ffffff' }}>Comments</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {Array.from(rulesBySection.entries()).flatMap(([sectionName, sectionRules], sectionIdx) => {
                                      const sectionRows = [
                                        (
                                          <tr key={`section-${sectionIdx}`} style={{ background: '#ebe5a5', borderBottom: '2px solid #d4c896' }}>
                                            <td colSpan={8} style={{ padding: '8px 12px', textAlign: 'left', color: '#333333', fontWeight: 600 }}>
                                              Section: {sectionName}
                                            </td>
                                          </tr>
                                        )
                                      ];

                                      const ruleRows = sectionRules.map((rule: any, ruleIdx: number) => {
                                        const row = (
                                          <tr
                                            key={`rule-${sectionIdx}-${ruleIdx}`}
                                            style={{
                                              background: zebraIndex % 2 === 0 ? '#ffffff' : '#f0f8ff',
                                              borderBottom: '1px solid #d9d9d9',
                                            }}
                                          >
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {rule['rule-number'] || rule.rule_number || rule.position || ''}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {rule.name || '-'}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {renderRefList(rule.source)}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {renderRefList(rule.destination)}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {renderRefList(rule.service)}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {rule.action?.name || rule.action || '-'}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {rule.track?.type?.name || rule.track || 'Log'}
                                            </td>
                                            <td style={{ padding: '8px 12px', border: '1px solid #d9d9d9' }}>
                                              {rule.comments || ''}
                                            </td>
                                          </tr>
                                        );
                                        zebraIndex += 1;
                                        return row;
                                      });

                                      return [...sectionRows, ...ruleRows];
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Objects Summary */}
                      {(objects.added.length > 0 || objects.modified.length > 0 || objects.deleted.length > 0) && (
                        <div style={{ marginBottom: 12 }}>
                          <Text strong>Objects Summary</Text>
                          {['added', 'modified', 'deleted'].map((category) => {
                            const catObjects = objects[category as keyof typeof objects];
                            if (!catObjects || catObjects.length === 0) return null;

                            // Group by type
                            const byType: Record<string, any[]> = {};
                            catObjects.forEach((obj: any) => {
                              const type = obj.type || 'other';
                              if (!byType[type]) byType[type] = [];
                              byType[type].push(obj);
                            });

                            return (
                              <div key={category} style={{ marginLeft: 12, marginTop: 4 }}>
                                <Text>{category.charAt(0).toUpperCase() + category.slice(1)}:</Text>
                                {Object.entries(byType).map(([type, objs]) => (
                                  <div key={type} style={{ marginLeft: 12 }}>
                                    <Text style={{ fontSize: '0.9em' }}>
                                      {type}:{' '}
                                      {objs.map((obj: any) => {
                                        const ip = obj['ipv4-address'] || obj.subnet4 || '';
                                        const mask = obj['mask-length4'] || '';
                                        return `${obj.name}${ip ? ` (${ip}${mask ? '/' + mask : ''})` : ''}`;
                                      }).join(', ')}
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                });
              });
            })}
          </div>
        );
      })}

      {/* Raw JSON section */}
      <Collapse
        size="small"
        items={[{
          key: 'raw-json',
          label: 'Raw JSON',
          style: { marginTop: 16 },
          children: (
            <pre style={{ margin: 0, fontSize: '0.85em', maxHeight: 400, overflow: 'auto', background: 'transparent' }}>
              {JSON.stringify(sessionChanges, null, 2)}
            </pre>
          ),
        }]}
      />
    </div>
  );
}
