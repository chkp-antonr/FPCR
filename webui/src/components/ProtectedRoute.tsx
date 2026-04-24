import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import styles from '../styles/protectedRoute.module.css';

export default function ProtectedRoute({ children }: { children: React.JSX.Element }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
