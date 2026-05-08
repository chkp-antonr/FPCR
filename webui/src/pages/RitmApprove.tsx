import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { message, Modal, Button, Spin, Card, Typography, Alert, Space, Input, Row, Col, Statistic, Tag, Collapse } from 'antd';
import { ArrowLeftOutlined, CheckOutlined, CloseOutlined, LockOutlined } from '@ant-design/icons';
import { ritmApi } from '../api/endpoints';
import { RITM_STATUS, type EvidenceHistoryResponse, type RITMItem, type PolicyItem } from '../types';
import { useAuth } from '../contexts/AuthContext';
import RulesTable from '../components/RulesTable';
import styles from '../styles/pages/ritm-approve.module.css';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface LockInfo {
  locked: boolean;
  lockedBy: string | null;
  lockedAt: string | null;
  canEdit: boolean;
  expiresAt: string | null;
}

export default function RitmApprove() {
  const { ritmNumber } = useParams<{ ritmNumber: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [ritm, setRitm] = useState<RITMItem | null>(null);
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const [lockInfo, setLockInfo] = useState<LockInfo>({
    locked: false,
    lockedBy: null,
    lockedAt: null,
    canEdit: false,
    expiresAt: null,
  });

  const [approveModalVisible, setApproveModalVisible] = useState(false);
  const [returnModalVisible, setReturnModalVisible] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [evidenceHistory, setEvidenceHistory] = useState<EvidenceHistoryResponse | null>(null);
  const [sessionHtml, setSessionHtml] = useState<string | null>(null);
  const [htmlLoading, setHtmlLoading] = useState(false);
  const [showSessionHtml, setShowSessionHtml] = useState(false);

  // Poll for lock status every 30 seconds
  useEffect(() => {
    const checkLockStatus = async () => {
      if (!ritmNumber) return;

      try {
        const response = await ritmApi.get(ritmNumber);
        const r = response.ritm;

        const currentUsername = user?.username || '';
        const isLocked = !!r.approver_locked_by;
        const isLockedByMe = r.approver_locked_by === currentUsername;

        let expiresAt: string | null = null;
        if (r.approver_locked_at) {
          const lockedTime = new Date(r.approver_locked_at);
          expiresAt = new Date(lockedTime.getTime() + 30 * 60 * 1000).toISOString();
        }

        setLockInfo({
          locked: isLocked,
          lockedBy: r.approver_locked_by,
          lockedAt: r.approver_locked_at,
          canEdit: isLockedByMe,
          expiresAt,
        });
      } catch (error) {
        console.error('Failed to check lock status:', error);
      }
    };

    checkLockStatus();
    const interval = setInterval(checkLockStatus, 30000);
    return () => clearInterval(interval);
  }, [ritmNumber]);

  // Load RITM and policies
  useEffect(() => {
    const loadRitm = async () => {
      try {
        setLoading(true);
        const response = await ritmApi.get(ritmNumber || '');
        setRitm(response.ritm);
        setPolicies(response.policies || []);
      } catch (error: any) {
        message.error(error.response?.data?.detail || 'Failed to load RITM');
        navigate('/');
      } finally {
        setLoading(false);
      }
    };

    loadRitm();
  }, [ritmNumber, navigate]);

  // Acquire lock on mount
  useEffect(() => {
    const acquireLock = async () => {
      if (!ritmNumber || ritm?.status !== RITM_STATUS.READY_FOR_APPROVAL) return;

      try {
        await ritmApi.acquireLock(ritmNumber);
        message.success('Lock acquired for approval');
      } catch (error: any) {
        if (error.response?.status === 403) {
          message.warning('RITM is locked by another approver');
        } else {
          console.error('Failed to acquire lock:', error);
        }
      }
    };

    if (ritm && ritm.status === RITM_STATUS.READY_FOR_APPROVAL && !lockInfo.locked) {
      acquireLock();
    }
  }, [ritm, ritmNumber, lockInfo.locked]);

  useEffect(() => {
    const loadEvidenceHistory = async () => {
      if (!ritmNumber) return;
      try {
        const history = await ritmApi.getEvidenceHistory(ritmNumber);
        setEvidenceHistory(history);
      } catch (err) {
        console.error('getEvidenceHistory failed:', err);
        setEvidenceHistory(null);
      }
    };

    loadEvidenceHistory();
  }, [ritm, ritmNumber]);

  const handleApprove = async () => {
    if (!ritmNumber) return;

    try {
      setActionLoading(true);
      await ritmApi.update(ritmNumber, { status: RITM_STATUS.APPROVED });
      const publishResponse = await ritmApi.publish(ritmNumber);
      if (publishResponse.errors && publishResponse.errors.length > 0) {
        message.warning(`Published with errors: ${publishResponse.errors.join(', ')}`);
      } else {
        message.success('RITM approved and published to Check Point');
      }
      setApproveModalVisible(false);
      navigate('/');
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Failed to approve/publish RITM');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReturn = async () => {
    if (!ritmNumber) return;

    if (!feedback.trim()) {
      message.warning('Please provide feedback for the return');
      return;
    }

    try {
      setActionLoading(true);
      await ritmApi.update(ritmNumber, {
        status: RITM_STATUS.WORK_IN_PROGRESS,
        feedback: feedback.trim(),
      });
      message.success('RITM returned to creator with feedback');
      setReturnModalVisible(false);
      setFeedback('');
      navigate('/');
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Failed to return RITM');
    } finally {
      setActionLoading(false);
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
      setHtmlLoading(true);
      const html = await ritmApi.getSessionEvidenceHtml(ritmNumber, 1);
      setSessionHtml(html);
      setShowSessionHtml(true);
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Failed to load Evidence HTML');
    } finally {
      setHtmlLoading(false);
    }
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

  const currentUsername = user?.username || '';
  const isCreator = ritm.username_created === currentUsername;

  // Creator cannot approve their own RITM (but can view completed ones)
  if (isCreator && ritm.status === RITM_STATUS.READY_FOR_APPROVAL) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          message="You cannot approve your own RITM"
          description="Please ask another approver to review this request."
          type="warning"
          showIcon
          action={
            <Button onClick={() => navigate('/')}>Back to Dashboard</Button>
          }
        />
      </div>
    );
  }

  // Transform policies to RulesTable format
  const rulesForTable: any[] = policies.map(policy => ({
    key: `policy-${policy.id || policy.ritm_number}`,
    uid: `policy-${policy.id || policy.ritm_number}`,
    source_ips: policy.source_ips,
    dest_ips: policy.dest_ips,
    services: policy.services,
    domain: policy.domain_name,
    package: policy.package_name,
    section: policy.section_name,
    position: policy.position_type === 'custom' ? 'before' : policy.position_type,
    position_top: policy.position_number?.toString(),
    position_bottom: policy.position_number?.toString(),
    action: policy.action,
    track: policy.track === 'log' ? 'Log' : 'None',
    comments: policy.comments,
    rule_name: policy.rule_name,
  }));

  return (
    <div className={styles.pageContainer}>
      <div style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          Back to Dashboard
        </Button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Title level={3}>RITM: {ritmNumber}</Title>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic title="Created by" value={ritm.username_created} />
          </Col>
          <Col span={6}>
            <Statistic
              title="Date Created"
              value={new Date(ritm.date_created).toLocaleDateString()}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="Status"
              value={
                ritm.status === RITM_STATUS.WORK_IN_PROGRESS ? 'Work in Progress' :
                ritm.status === RITM_STATUS.READY_FOR_APPROVAL ? 'Ready for Approval' :
                ritm.status === RITM_STATUS.APPROVED ? 'Approved' :
                ritm.status === RITM_STATUS.COMPLETED ? 'Completed' : 'Unknown'
              }
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="Rules"
              value={policies.length}
            />
          </Col>
        </Row>

        {ritm.feedback && (
          <Alert
            message={`Feedback: "${ritm.feedback}"`}
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
          />
        )}

        {lockInfo.locked && (
          <Alert
            message={
              <Space>
                <LockOutlined />
                {lockInfo.lockedBy === currentUsername
                  ? 'You have locked this RITM for approval'
                  : `Locked by ${lockInfo.lockedBy}`}
                {lockInfo.expiresAt && (
                  <Text type="secondary">
                    (expires {new Date(lockInfo.expiresAt).toLocaleTimeString()})
                  </Text>
                )}
              </Space>
            }
            type={lockInfo.lockedBy === currentUsername ? 'success' : 'warning'}
            showIcon
            style={{ marginTop: 16 }}
          />
        )}
      </Card>

      <Card title="Rules" style={{ marginBottom: 16 }}>
        <RulesTable
          rules={rulesForTable}
          domains={[]}
          availableServices={[]}
          availableSourceIps={[]}
          availableDestIps={[]}
          updateRule={() => {}}
          handleClone={() => {}}
          onDelete={() => {}}
          disabled={true}
        />
      </Card>

      <Card title="Evidence" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space>
            <Button
              type="primary"
              onClick={handleDownloadSessionPdf}
            >
              Download Evidence PDF
            </Button>
            <Button
              onClick={handleToggleSessionHtml}
              loading={htmlLoading}
            >
              {showSessionHtml ? 'Hide Evidence HTML' : 'Show Evidence HTML'}
            </Button>
          </Space>

          {(!evidenceHistory || evidenceHistory.domains.length === 0) && (
            <Text type="secondary">No evidence sessions found for this RITM.</Text>
          )}

          {evidenceHistory && evidenceHistory.domains.length > 0 && (
            <Collapse
              size="small"
              items={evidenceHistory.domains.map((domain) => ({
                key: domain.domain_uid,
                label: `${domain.domain_name} (${domain.packages.length} package${domain.packages.length === 1 ? '' : 's'})`,
                children: (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {domain.packages.map((pkg) => (
                      <Card
                        key={pkg.package_uid}
                        size="small"
                        title={pkg.package_name}
                        bodyStyle={{ paddingTop: 12, paddingBottom: 12 }}
                      >
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                          {pkg.sessions.map((session) => {
                            const typeColor =
                              session.session_type === 'approval'
                                ? 'blue'
                                : session.session_type === 'correction'
                                  ? 'orange'
                                  : 'green';
                            return (
                              <div key={session.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                                <Space size={8} wrap>
                                  <Tag color={typeColor}>{session.session_type.toUpperCase()}</Tag>
                                  <Text>Attempt {session.attempt}</Text>
                                  <Text type="secondary">
                                    {new Date(session.created_at).toLocaleString()}
                                  </Text>
                                </Space>
                                <Text type="secondary" style={{ fontSize: '0.85em' }}>
                                  {session.session_uid ? `Session ${session.session_uid}` : 'No session UID'}
                                </Text>
                              </div>
                            );
                          })}
                        </Space>
                      </Card>
                    ))}
                  </Space>
                ),
              }))}
            />
          )}

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
      </Card>

      {lockInfo.canEdit && ritm.status === RITM_STATUS.READY_FOR_APPROVAL && (
        <Card>
          <Space>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              onClick={() => setApproveModalVisible(true)}
              loading={actionLoading}
            >
              Approve
            </Button>
            <Button
              danger
              icon={<CloseOutlined />}
              onClick={() => setReturnModalVisible(true)}
              loading={actionLoading}
            >
              Reject with Feedback
            </Button>
          </Space>
        </Card>
      )}

      <Modal
        title="Approve RITM"
        open={approveModalVisible}
        onOk={handleApprove}
        onCancel={() => setApproveModalVisible(false)}
        okText="Approve"
        cancelText="Cancel"
        confirmLoading={actionLoading}
      >
        <p>Are you sure you want to approve this RITM?</p>
        <p>This will enable the rules, run a final policy verification, and publish to Check Point.</p>
      </Modal>

      <Modal
        title="Return RITM with Feedback"
        open={returnModalVisible}
        onOk={handleReturn}
        onCancel={() => {
          setReturnModalVisible(false);
          setFeedback('');
        }}
        okText="Return"
        cancelText="Cancel"
        confirmLoading={actionLoading}
      >
        <p>Please provide feedback for the creator:</p>
        <TextArea
          rows={4}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="Enter feedback here..."
          maxLength={500}
          showCount
        />
      </Modal>
    </div>
  );
}
