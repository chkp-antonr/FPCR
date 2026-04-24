import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Domains from './pages/Domains';
import Domains2 from './pages/Domains2';
import RitmEdit from './pages/RitmEdit';
import RitmApprove from './pages/RitmApprove';

function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#d32f2f',
          colorBgBase: '#f5f5f5',
          colorBgContainer: '#ffffff',
          borderRadius: 6,
        },
      }}
    >
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="domains" element={<Domains />} />
              <Route path="domains-2" element={<Domains2 />} />
              <Route path="ritm/edit/:ritmNumber" element={<RitmEdit />} />
              <Route path="ritm/approve/:ritmNumber" element={<RitmApprove />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
