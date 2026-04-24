import { useEffect, useState, type ReactNode } from 'react';
import { Card, Typography, Button, List, Modal, Input, message, Empty, Progress, Space, Alert } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { ritmApi, cacheApi } from '../api/endpoints';
import { RITM_STATUS, type RITMItem, type CacheStatusResponse } from '../types';
import { useAuth } from '../contexts/AuthContext';
import styles from '../styles/pages/dashboard.module.css';

const { Title, Paragraph } = Typography;

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [myRitms, setMyRitms] = useState<RITMItem[]>([]);
  const [ritmsForApproval, setRitmsForApproval] = useState<RITMItem[]>([]);
  const [approvedRitms, setApprovedRitms] = useState<RITMItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [manualCoreRefreshing, setManualCoreRefreshing] = useState(false);
  const [newRitmModalVisible, setNewRitmModalVisible] = useState(false);
  const [newRitmNumber, setNewRitmNumber] = useState('');
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
      return null;
    }
  };

  const fetchRitms = async () => {
    if (!user?.username) return;

    setLoading(true);
    try {
      const response = await ritmApi.list();
      const allRitms = [...(response.ritms || [])].sort(
        (left, right) => new Date(right.date_created).getTime() - new Date(left.date_created).getTime(),
      );

      const currentUsername = user.username;

      setMyRitms(allRitms.filter(r =>
        r.username_created === currentUsername &&
        (r.status === RITM_STATUS.WORK_IN_PROGRESS || r.feedback)
      ));

      setRitmsForApproval(allRitms.filter(r =>
        r.status === RITM_STATUS.READY_FOR_APPROVAL &&
        r.username_created !== currentUsername
      ));

      setApprovedRitms(allRitms.filter(r =>
        r.status === RITM_STATUS.APPROVED
      ));
    } catch (error) {
      message.error('Failed to fetch RITMs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRitms();
    const interval = setInterval(fetchRitms, 30000); // Poll every 30s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    void fetchCacheStatus();
    const interval = setInterval(
      () => {
        void fetchCacheStatus();
      },
      cacheStatus.refreshing || manualCoreRefreshing ? 1500 : 30000
    );

    return () => clearInterval(interval);
  }, [cacheStatus.refreshing, manualCoreRefreshing]);

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

  const handleCreateRitm = async () => {
    if (!newRitmNumber) {
      message.error('Please enter a RITM number');
      return;
    }
    try {
      await ritmApi.create({ ritm_number: newRitmNumber });
      message.success(`RITM ${newRitmNumber} created`);
      setNewRitmModalVisible(false);
      setNewRitmNumber('');
      fetchRitms();
      navigate(`/ritm/edit/${newRitmNumber}`);
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Failed to create RITM');
    }
  };

  const formatDate = (date: string) => new Date(date).toLocaleDateString('en-GB');

  const getRitmDestination = (ritm: RITMItem) => {
    const currentUsername = user?.username || '';
    const isCreator = ritm.username_created === currentUsername;

    if (ritm.status === RITM_STATUS.READY_FOR_APPROVAL) {
      return isCreator ? `/ritm/edit/${ritm.ritm_number}` : `/ritm/approve/${ritm.ritm_number}`;
    }

    if (ritm.status === RITM_STATUS.APPROVED) {
      return isCreator ? `/ritm/edit/${ritm.ritm_number}` : `/ritm/approve/${ritm.ritm_number}`;
    }

    return `/ritm/edit/${ritm.ritm_number}`;
  };

  type DashboardColumn = {
    key: string;
    label: string;
    className?: string;
    render: (ritm: RITMItem) => ReactNode;
  };

  const renderRitmList = (
    ritms: RITMItem[],
    title: string,
    emptyDescription: string,
    columns: DashboardColumn[],
  ) => {
    const columnTemplate = columns.map(() => 'minmax(0, 1fr)').join(' ');

    return (
      <Card className={styles.ritmCard}>
        <h3 className={styles.cardTitle}>{title}</h3>
        <div className={styles.cardHeader} style={{ gridTemplateColumns: columnTemplate }}>
          {columns.map(column => (
            <span key={column.key}>{column.label}</span>
          ))}
        </div>
        <List
          dataSource={ritms}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyDescription} />,
          }}
          renderItem={(ritm) => (
            <List.Item className={styles.listItem}>
              <button
                type="button"
                className={styles.ritmRowButton}
                style={{ gridTemplateColumns: columnTemplate }}
                onClick={() => navigate(getRitmDestination(ritm))}
              >
                {columns.map(column => (
                  <span key={column.key} className={column.className}>
                    {column.render(ritm)}
                  </span>
                ))}
              </button>
            </List.Item>
          )}
        />
      </Card>
    );
  };

  const myRitmColumns: DashboardColumn[] = [
    {
      key: 'ritm',
      label: 'RITM',
      className: styles.primaryCell,
      render: (ritm) => ritm.ritm_number,
    },
    {
      key: 'date',
      label: 'Date',
      render: (ritm) => formatDate(ritm.date_created),
    },
  ];

  const sharedApprovalColumns: DashboardColumn[] = [
    {
      key: 'ritm',
      label: 'RITM',
      className: styles.primaryCell,
      render: (ritm) => ritm.ritm_number,
    },
    {
      key: 'date',
      label: 'Date',
      render: (ritm) => formatDate(ritm.date_created),
    },
    {
      key: 'user',
      label: 'User',
      render: (ritm) => ritm.username_created,
    },
  ];

  return (
    <div className={styles.pageContainer}>
      <Card className={styles.welcomeCard} style={{ marginBottom: 16 }}>
        <div className={styles.headerRow}>
          <div>
            <Title level={2} className={styles.title}>Welcome to FPCR</Title>
            <Paragraph className={styles.paragraph}>
              Firewall Policy Change Request tool for Check Point management.
            </Paragraph>
          </div>
          <Space wrap>
            <Button
              onClick={handleRefreshCache}
              loading={cacheStatus.core_refreshing || manualCoreRefreshing}
              disabled={cacheStatus.refreshing}
              icon={<ReloadOutlined />}
            >
              Cache Refresh
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setNewRitmModalVisible(true)}
              className={styles.viewButton}
            >
              New RITM
            </Button>
          </Space>
        </div>

        {(cacheStatus.core_refreshing || manualCoreRefreshing) && (
          <div className={styles.progressPanel}>
            <div className={styles.progressLabel}>{getDomainProgressLabel()}</div>
            <Progress
              percent={getProgressPercent(
                cacheStatus.domains_progress.processed,
                cacheStatus.domains_progress.total
              )}
              status="active"
              style={{ marginBottom: 10 }}
            />
            <div className={styles.progressLabel}>
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

        {cacheStatus.is_empty && !cacheStatus.refreshing && (
          <Alert
            type="warning"
            showIcon
            message="Cache is empty"
            description="Click Cache Refresh to load domains and packages from Check Point."
            style={{ marginTop: 12 }}
          />
        )}
      </Card>

      {!user ? (
        <Card>
          <Empty description="Please log in to view RITMs" />
        </Card>
      ) : loading ? (
        <div>Loading...</div>
      ) : (
        <div className={styles.cardsGrid}>
          {renderRitmList(myRitms, 'My RITMs', 'No RITMs assigned to you yet.', myRitmColumns)}
          {renderRitmList(ritmsForApproval, 'RITMs for Approval', 'No RITMs are waiting for approval.', sharedApprovalColumns)}
          {renderRitmList(approvedRitms, 'Approved RITMs', 'No approved RITMs yet.', sharedApprovalColumns)}
        </div>
      )}

      <Modal
        title="Create New RITM"
        open={newRitmModalVisible}
        onOk={handleCreateRitm}
        onCancel={() => {
          setNewRitmModalVisible(false);
          setNewRitmNumber('');
        }}
      >
        <Input
          placeholder="RITM1234567"
          value={newRitmNumber}
          onChange={(e) => setNewRitmNumber(e.target.value)}
          onPressEnter={handleCreateRitm}
        />
        <div style={{ marginTop: 8, color: '#888' }}>
          Format: RITM followed by numbers (e.g., RITM2452257)
        </div>
      </Modal>
    </div>
  );
}
