import { Layout as AntLayout, Menu, Button } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LogoutOutlined, HomeOutlined, UnorderedListOutlined, AppstoreOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import styles from '../styles/layout.module.css';

const { Header, Content, Sider } = AntLayout;

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: 'Dashboard' },
    { key: '/domains', icon: <UnorderedListOutlined />, label: 'Domains' },
    { key: '/domains-2', icon: <AppstoreOutlined />, label: 'Domains_2' },
  ];

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <AntLayout className={styles.layout}>
      <Header className={styles.header}>
        <div className={styles.logo}>
          FPCR<span className={styles.logoAccent}>.</span>
        </div>
        <div className={styles.userSection}>
          <span className={styles.username}>{user?.username}</span>
          <Button
            type="text"
            icon={<LogoutOutlined />}
            onClick={handleLogout}
            className={styles.logoutButton}
          >
            Logout
          </Button>
        </div>
      </Header>
      <AntLayout>
        <Sider width={200} className={styles.sider}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
        <Content className={styles.content}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
