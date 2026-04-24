# WebUI Styling System Implementation Plan

> **For Claude:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace inline styles in the FPCR WebUI with a maintainable CSS-based system using CSS Modules and CSS variables for a clean, security-themed enterprise aesthetic.

**Architecture:** CSS Modules for component-scoped styles combined with CSS custom properties for global theming. Ant Design theme config references CSS variables for consistency.

**Tech Stack:** React, Vite, TypeScript, CSS Modules, Ant Design

---

## File Structure

```text
webui/src/
├── styles/
│   ├── globals.css              # NEW - CSS variables, global styles
│   ├── layout.module.css        # NEW - Layout component styles
│   └── pages/
│       ├── domains.module.css   # NEW - Domains page styles
│       ├── dashboard.module.css # NEW - Dashboard page styles
│       └── login.module.css     # NEW - Login page styles
├── modules.d.ts                 # NEW - CSS Modules TypeScript declarations
├── main.tsx                     # MODIFY - Import globals.css
├── App.tsx                      # MODIFY - Update theme config
├── components/
│   └── Layout.tsx               # MODIFY - Use CSS modules
├── pages/
│   ├── Domains.tsx              # MODIFY - Use CSS modules
│   ├── Dashboard.tsx            # MODIFY - Use CSS modules
│   └── Login.tsx                # MODIFY - Use CSS modules
```

---

## Chunk 1: Foundation - CSS Variables and TypeScript Declarations

### Task 1: Create CSS Modules TypeScript Declaration

**Files:**

- Create: `webui/src/modules.d.ts`

- [ ] **Step 1: Create the TypeScript declaration file**

```typescript
declare module '*.module.css' {
  const classes: { [key: string]: string };
  export default classes;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd webui && npm run type-check` (if available) or `npx tsc --noEmit`
Expected: No errors, CSS modules are now recognized

- [ ] **Step 3: Commit**

```bash
git add webui/src/modules.d.ts
git commit -m "feat(types): add CSS modules TypeScript declaration"
```

### Task 2: Create Global Styles with CSS Variables

**Files:**

- Create: `webui/src/styles/globals.css`

- [ ] **Step 1: Create globals.css with CSS variables**

```css
@import 'antd/dist/reset.css';

:root {
  /* Primary - Security Red (accent, actions) */
  --color-primary: #d32f2f;
  --color-primary-hover: #b71c1c;
  --color-primary-light: #ffcdd2;

  /* Secondary - Teal (success/secure states) */
  --color-secondary: #00897b;
  --color-secondary-hover: #00695c;

  /* Neutral - Enterprise Grays */
  --color-bg-base: #f5f5f5;
  --color-bg-container: #ffffff;
  --color-bg-elevated: #ffffff;
  --color-border: #d9d9d9;
  --color-border-light: #f0f0f0;

  /* Text */
  --color-text-primary: #262626;
  --color-text-secondary: #595959;
  --color-text-tertiary: #8c8c8c;

  /* Semantic */
  --color-success: #52c41a;
  --color-warning: #faad14;
  --color-error: #ff4d4f;
  --color-info: #1890ff;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.03);
  --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.08);

  /* Spacing scale */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-xxl: 48px;

  /* Border radius */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
}

/* Global base styles */
* {
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: var(--color-bg-base);
  color: var(--color-text-primary);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* Card enhancement */
.ant-card {
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s;
}

.ant-card:hover {
  box-shadow: var(--shadow-md);
}

/* Input focus states */
.ant-input:focus,
.ant-select:focus .ant-select-selector,
.ant-auto-complete:focus .ant-select-selector {
  border-color: var(--color-secondary) !important;
  box-shadow: 0 0 0 2px rgba(0, 137, 123, 0.1) !important;
}

/* Button primary override */
.ant-btn-primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.ant-btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}

/* Smooth transitions (but not for everything) */
.ant-card,
.ant-btn,
.ant-input,
.ant-select-selector {
  transition: background-color 0.15s, border-color 0.15s, box-shadow 0.15s;
}
```

- [ ] **Step 2: Import globals.css in main.tsx**

**Files:**

- Modify: `webui/src/main.tsx`

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/globals.css';  // ADD THIS LINE

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 3: Verify dev server runs without errors**

Run: `cd webui && npm run dev`
Expected: Dev server starts, no CSS import errors

- [ ] **Step 4: Commit**

```bash
git add webui/src/styles/globals.css webui/src/main.tsx
git commit -m "feat(styles): add global styles with CSS variables"
```

### Task 3: Update App.tsx Theme Config

**Files:**

- Modify: `webui/src/App.tsx`

- [ ] **Step 1: Update ConfigProvider theme to use CSS variables**

```tsx
<ConfigProvider
  theme={{
    algorithm: theme.defaultAlgorithm,
    token: {
      colorPrimary: 'var(--color-primary)',
      colorBgBase: 'var(--color-bg-base)',
      colorBgContainer: 'var(--color-bg-container)',
      borderRadius: 6,
    },
  }}
>
```

- [ ] **Step 2: Verify dev server runs**

Run: `cd webui && npm run dev`
Expected: Theme uses CSS variables (inspect element to verify)

- [ ] **Step 3: Commit**

```bash
git add webui/src/App.tsx
git commit -m "feat(theme): update Ant Design theme to use CSS variables"
```

---

## Chunk 2: Layout Component Styling

### Task 4: Create Layout CSS Module

**Files:**

- Create: `webui/src/styles/layout.module.css`

- [ ] **Step 1: Create layout.module.css**

```css
/* Main layout */
.layout {
  min-height: 100vh;
}

/* Header with security-themed gradient */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  padding: 0 var(--space-lg);
  box-shadow: var(--shadow-md);
  height: 64px;
}

.logo {
  color: white;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1px;
  display: flex;
  align-items: center;
}

.logoAccent {
  color: var(--color-primary);
}

.userSection {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.username {
  color: rgba(255, 255, 255, 0.85);
  font-size: 14px;
}

.logoutButton {
  color: rgba(255, 255, 255, 0.7);
}

.logoutButton:hover {
  color: white;
}

/* Sidebar */
.sider {
  background: var(--color-bg-container) !important;
  border-right: 1px solid var(--color-border-light);
}

.sider .ant-menu {
  border-right: none;
}

.menuItem {
  padding: var(--space-md) var(--space-lg);
  font-size: 14px;
}

/* Content area */
.content {
  padding: 0 var(--space-lg) var(--space-lg) var(--space-lg);
  background: var(--color-bg-base);
  min-height: calc(100vh - 64px);
}
```

- [ ] **Step 2: Update Layout.tsx to use CSS modules**

**Files:**

- Modify: `webui/src/components/Layout.tsx`

```tsx
import { Layout as AntLayout, Menu, Button } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LogoutOutlined, HomeOutlined, UnorderedListOutlined } from '@ant-design/icons';
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
```

- [ ] **Step 3: Verify layout renders correctly**

Run: `cd webui && npm run dev`
Expected: Login, navigate to dashboard, see styled header and sidebar

- [ ] **Step 4: Commit**

```bash
git add webui/src/styles/layout.module.css webui/src/components/Layout.tsx
git commit -m "feat(styles): add layout CSS module and update Layout component"
```

---

## Chunk 3: Domains Page Styling

### Task 5: Create Domains Page CSS Module

**Files:**

- Create: `webui/src/styles/pages/domains.module.css`

- [ ] **Step 1: Create domains.module.css**

```css
/* Page container */
.pageContainer {
  padding: var(--space-lg);
}

/* Main card with refined shadows */
.packageCard {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border-light);
}

.cardHeader {
  border-bottom: 1px solid var(--color-border-light);
  padding: var(--space-md) var(--space-lg);
}

.cardTitle {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

/* Horizontal selector bar */
.selectorBar {
  display: flex;
  gap: var(--space-md);
  align-items: flex-end;
  padding: var(--space-lg);
  flex-wrap: wrap;
}

/* Individual selector groups */
.selectorGroup {
  flex: 1 1 250px;
  min-width: 200px;
}

.selectorLabel {
  display: block;
  margin-bottom: var(--space-sm);
  font-weight: 500;
  font-size: 14px;
  color: var(--color-text-primary);
}

/* AutoComplete full width */
.autoComplete {
  width: 100%;
}

/* Spin container wrapper */
.spinWrapper {
  width: 100%;
}

/* Position selector with visual distinction */
.positionGroup {
  flex: 2 1 400px;
  padding: var(--space-md);
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

.positionLabel {
  display: block;
  margin-bottom: var(--space-sm);
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.positionControls {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

/* Radio group styling */
.radioGroup {
  display: flex;
  gap: var(--space-sm);
}

/* Custom number input */
.customInput {
  width: 90px;
}

/* Submit button */
.submitButton {
  margin-left: auto;
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.submitButton:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}
```

- [ ] **Step 2: Update Domains.tsx to use CSS modules**

**Files:**

- Modify: `webui/src/pages/Domains.tsx`

Key changes:

1. Add import: `import styles from '../styles/pages/domains.module.css';`
2. Replace `style={{ padding: 24 }}` with `className={styles.pageContainer}`
3. Replace all other inline styles with CSS module classes
4. Add className to Card: `classNames={{ header: styles.cardHeader }}`

```tsx
import { useEffect, useState } from 'react';
import { Card, AutoComplete, Button, message, Spin, Radio, InputNumber, Flex } from 'antd';
import type { SelectProps } from 'antd/es/select';
import { domainsApi, packagesApi } from '../api/endpoints';
import type {
  DomainItem,
  PackageItem,
  SectionItem,
  PositionChoice
} from '../types';
import styles from '../styles/pages/domains.module.css';

// ... (keep all state and logic the same) ...

return (
  <div className={styles.pageContainer}>
    <Card
      title={<span className={styles.cardTitle}>Package Selection</span>}
      className={styles.packageCard}
      classNames={{ header: styles.cardHeader }}
    >
      <Spin spinning={initialLoading}>
        <Flex gap="middle" align="flex-end" className={styles.selectorBar} wrap="wrap">
          <div className={styles.selectorGroup}>
            <label className={styles.selectorLabel}>Domain:</label>
            <AutoComplete
              className={styles.autoComplete}
              options={domainOptions}
              value={domainSearch}
              onChange={setDomainSearch}
              onSelect={(value) => {
                const domain = domains.find(d => d.uid === value);
                if (domain) {
                  setSelectedDomain(domain);
                  setDomainSearch(domain.name);

                  setSelectedPackage(null);
                  setPackageSearch('');
                  setSections([]);
                  setSectionOptions([]);
                  setSelectedSection(null);
                  setSectionSearch('');
                  setTotalRules(0);
                  setPositionType(null);
                  setCustomNumber(null);
                  fetchPackages(domain.uid);
                }
              }}
              placeholder="Search domain..."
              filterOption={(inputValue, option) =>
                !!option?.label?.toString().toLowerCase().includes(inputValue.toLowerCase())
              }
            />
          </div>

          <div className={styles.selectorGroup}>
            <label className={styles.selectorLabel}>Package:</label>
            <div className={styles.spinWrapper}>
              <Spin spinning={packagesLoading}>
                <AutoComplete
                  className={styles.autoComplete}
                  options={packageOptions}
                  value={packageSearch}
                  onChange={setPackageSearch}
                  disabled={!selectedDomain}
                  onSelect={(value) => {
                    const pkg = packages.find(p => p.uid === value);
                    if (pkg && selectedDomain) {
                      setSelectedPackage(pkg);
                      setPackageSearch(pkg.name);

                      setSelectedSection(null);
                      setSectionSearch('');
                      setTotalRules(0);
                      setPositionType(null);
                      setCustomNumber(null);
                      fetchSections(selectedDomain.uid, pkg.uid);
                    }
                  }}
                  placeholder="Search package..."
                  filterOption={(inputValue, option) =>
                    !!option?.label?.toString().toLowerCase().includes(inputValue.toLowerCase())
                  }
                />
              </Spin>
            </div>
          </div>

          <div className={styles.selectorGroup}>
            <label className={styles.selectorLabel}>Access Section:</label>
            <div className={styles.spinWrapper}>
              <Spin spinning={sectionsLoading}>
                <AutoComplete
                  className={styles.autoComplete}
                  options={sectionOptions}
                  value={sectionSearch}
                  onChange={(val) => {
                    setSectionSearch(val);
                    if (!val) {
                      setSelectedSection(null);
                    }
                  }}
                  disabled={!selectedPackage}
                  onSelect={(value) => {
                    const section = sections.find(s => s.uid === value);
                    if (section) {
                      setSelectedSection(section);
                      setSectionSearch(`${section.rulebase_range[0]}-${section.rulebase_range[1]} ${section.name}`);
                    }
                  }}
                  placeholder={selectedPackage ? "Select section (optional)..." : ""}
                  filterOption={(inputValue, option) =>
                    !!option?.label?.toString().toLowerCase().includes(inputValue.toLowerCase())
                  }
                  allowClear
                />
              </Spin>
            </div>
          </div>

          <div className={styles.positionGroup}>
            <label className={styles.positionLabel}>Rule Position:</label>
            <Flex align="center" gap="middle" className={styles.positionControls}>
              <Radio.Group
                className={styles.radioGroup}
                value={positionType}
                onChange={(e) => {
                  setPositionType(e.target.value);
                  if (e.target.value !== 'custom') setCustomNumber(null);
                }}
                disabled={!selectedPackage || sectionsLoading}
              >
                <Radio value="top">Top</Radio>
                <Radio value="bottom">Bottom</Radio>
                <Radio value="custom">Custom #</Radio>
              </Radio.Group>

              {positionType === 'custom' && (
                <InputNumber
                  min={selectedSection ? selectedSection.rulebase_range[0] : 1}
                  max={selectedSection ? selectedSection.rulebase_range[1] + 1 : totalRules + 1}
                  value={customNumber}
                  onChange={(value) => setCustomNumber(value)}
                  className={styles.customInput}
                  size="small"
                  placeholder="Rule #"
                />
              )}

              <Button
                type="primary"
                disabled={
                  !positionType ||
                  (positionType === 'custom' &&
                    (customNumber === null ||
                      (selectedSection
                        ? (customNumber < selectedSection.rulebase_range[0] || customNumber > selectedSection.rulebase_range[1] + 1)
                        : (customNumber < 1 || customNumber > totalRules + 1)
                      )
                    )
                  )
                }
                onClick={() => {
                  if (!positionType) return;
                  const payload: PositionChoice = {
                    type: positionType,
                    custom_number: positionType === 'custom' ? customNumber ?? 0 : undefined,
                  };
                  console.log('Final Selection:', {
                    domain: selectedDomain?.name,
                    package: selectedPackage?.name,
                    section: selectedSection?.name || 'GLOBAL (Top/Bottom of Policy)',
                    position: payload,
                  });
                  message.success(`Targeting ${positionType} of ${selectedSection ? 'section ' + selectedSection.name : 'policy'}`);
                }}
                className={styles.submitButton}
              >
                Confirm
              </Button>
            </Flex>
          </div>
        </Flex>

      </Spin>
    </Card>
  </div>
);
```

- [ ] **Step 3: Verify domains page renders correctly**

Run: `cd webui && npm run dev`
Expected: Domains page displays with styled selectors, position group has gradient background

- [ ] **Step 4: Commit**

```bash
git add webui/src/styles/pages/domains.module.css webui/src/pages/Domains.tsx
git commit -m "feat(styles): add domains page CSS module and update component"
```

---

## Chunk 4: Remaining Pages

### Task 6: Create Dashboard Page CSS Module

**Files:**

- Create: `webui/src/styles/pages/dashboard.module.css`
- Modify: `webui/src/pages/Dashboard.tsx`

- [ ] **Step 1: Create dashboard.module.css**

```css
.pageContainer {
  padding: var(--space-lg);
}

.welcomeCard {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border-light);
}

.title {
  margin-bottom: var(--space-md);
}

.paragraph {
  margin-bottom: var(--space-md);
  color: var(--color-text-secondary);
}

.viewButton {
  margin-top: var(--space-md);
}
```

- [ ] **Step 2: Update Dashboard.tsx**

```tsx
import { Card, Typography, Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import styles from '../styles/pages/dashboard.module.css';

const { Title, Paragraph } = Typography;

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className={styles.pageContainer}>
      <Card className={styles.welcomeCard}>
        <Title level={2} className={styles.title}>Welcome to FPCR</Title>
        <Paragraph className={styles.paragraph}>
          Firewall Policy Change Request tool for Check Point management.
        </Paragraph>
        <Paragraph className={styles.paragraph}>
          Select an option from the sidebar to get started.
        </Paragraph>
        <Button type="primary" onClick={() => navigate('/domains')} className={styles.viewButton}>
          View Domains
        </Button>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Verify dashboard renders correctly**

Run: `cd webui && npm run dev`
Expected: Dashboard displays with styled card

- [ ] **Step 4: Commit**

```bash
git add webui/src/styles/pages/dashboard.module.css webui/src/pages/Dashboard.tsx
git commit -m "feat(styles): add dashboard page CSS module"
```

### Task 7: Create Login Page CSS Module

**Files:**

- Create: `webui/src/styles/pages/login.module.css`
- Modify: `webui/src/pages/Login.tsx`

- [ ] **Step 1: Create login.module.css**

```css
.loginContainer {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  padding: var(--space-lg);
}

.loginCard {
  width: 100%;
  max-width: 400px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--color-border-light);
}

.loginHeader {
  text-align: center;
  margin-bottom: var(--space-lg);
}

.loginTitle {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.loginSubtitle {
  color: var(--color-text-secondary);
  margin-top: var(--space-sm);
}

.loginForm {
  margin-top: var(--space-lg);
}

.submitButton {
  width: 100%;
  height: 40px;
  background: var(--color-primary);
  border-color: var(--color-primary);
  font-weight: 600;
}

.submitButton:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}
```

- [ ] **Step 2: Update Login.tsx**

```tsx
import { useState } from 'react';
import { Card, Form, Input, Button, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import styles from '../styles/pages/login.module.css';

export default function Login() {
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success('Login successful');
      navigate('/');
    } catch (error) {
      message.error('Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.loginContainer}>
      <Card className={styles.loginCard}>
        <div className={styles.loginHeader}>
          <h1 className={styles.loginTitle}>FPCR</h1>
          <p className={styles.loginSubtitle}>Firewall Policy Change Request</p>
        </div>
        <Form
          name="login"
          onFinish={onFinish}
          autoComplete="off"
          className={styles.loginForm}
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: 'Please input your username' }]}
          >
            <Input size="large" placeholder="Username" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: 'Please input your password' }]}
          >
            <Input.Password size="large" placeholder="Password" />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              className={styles.submitButton}
            >
              Login
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Verify login page renders correctly**

Run: `cd webui && npm run dev`
Expected: Login page displays with dark gradient background and centered card

- [ ] **Step 4: Commit**

```bash
git add webui/src/styles/pages/login.module.css webui/src/pages/Login.tsx
git commit -m "feat(styles): add login page CSS module"
```

---

## Chunk 5: Verification and Cleanup

### Task 8: Final Verification

- [ ] **Step 1: Run type check**

Run: `cd webui && npx tsc --noEmit`
Expected: No TypeScript errors

- [ ] **Step 2: Run build**

Run: `cd webui && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Visual regression check**

Run: `cd webui && npm run dev`
Manual check: Navigate through all pages (Login → Dashboard → Domains) and verify:

- Header has dark gradient background
- Primary buttons are red (#d32f2f)
- Input focus is teal
- Cards have subtle shadows
- Position selector has gradient background
- No inline styles remain (inspect DOM)

- [ ] **Step 4: Final commit**

```bash
git add webui/src/
git commit -m "chore: final verification - WebUI styling system complete"
```

### Task 9: Update Documentation

- [ ] **Step 1: Update CONTEXT.md**

**Files:**

- Modify: `docs/CONTEXT.md`

Add entry:

```markdown
## WebUI Styling System
- **Design**: [docs/internal/features/260220-webui-styling/DESIGN.md](internal/features/260220-webui-styling/DESIGN.md)
- **Plan**: [docs/plans/260220-webui-styling.md](plans/260220-webui-styling.md)
- CSS Modules with security-themed color palette (red/teal/gray)
- CSS variables for global theming
```

- [ ] **Step 2: Commit documentation**

```bash
git add docs/CONTEXT.md
git commit -m "docs: add WebUI styling system to context"
```

---

## Summary

This implementation plan:

1. **Replaces all inline styles** with CSS modules
2. **Introduces CSS variables** for consistent theming
3. **Creates security-themed color palette** (red primary, teal secondary)
4. **Provides clean enterprise aesthetic** with subtle shadows and gradients
5. **Maintains Ant Design integration** via theme config

**Files Created:** 9
**Files Modified:** 6
**Total Tasks:** 25 sub-tasks across 9 main tasks
