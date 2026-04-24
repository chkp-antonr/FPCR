import { Form, Input, Button, Card, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import styles from '../styles/pages/login.module.css';

interface LoginForm {
  username: string;
  password: string;
}

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: LoginForm) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success('Logged in successfully');
      navigate('/');
    } catch {
      message.error('Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.loginContainer}>
      <Card
        className={styles.loginCard}
        classNames={{ header: styles.cardHeader }}
        title={
          <div className={styles.cardTitle}>
            <span className={styles.titleMain}>FPCR</span>
            <span className={styles.titleAccent}>.</span>
          </div>
        }
      >
        <Form
          onFinish={onFinish}
          layout="vertical"
          autoComplete="off"
          className={styles.formContainer}
        >
          <Form.Item
            name="username"
            label={<span className={styles.inputLabel}>Username</span>}
            rules={[{ required: true, message: 'Please enter username' }]}
          >
            <Input placeholder="Enter your username" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            label={<span className={styles.inputLabel}>Password</span>}
            rules={[{ required: true, message: 'Please enter password' }]}
          >
            <Input.Password placeholder="Enter your password" size="large" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={loading}
              className={styles.loginButton}
            >
              Log In
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
