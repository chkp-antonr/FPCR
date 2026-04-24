# WebUI Styling System Design

**Date**: 2026-02-20
**Status**: Approved
**Author**: AI Assistant

## Overview

This document defines the styling architecture for the FPCR (Firewall Policy Change Request) WebUI. The goal is to replace inline styles with a maintainable, CSS-based system that provides a clean enterprise aesthetic with security-themed colors.

## Requirements

1. **No inline styles** - All styling must use CSS, not `style={{ }}` props
2. **Platform-wide consistency** - Easy to change styles across the entire application
3. **Clean Enterprise aesthetic** - Professional, minimal, data-focused design
4. **Security-themed colors** - Firewall management appropriate palette (reds, teals, dark grays)
5. **Horizontal layout** - Domains page selectors in a horizontal bar arrangement

## Design Decisions

### Approach: CSS Modules with CSS Variables

After evaluating three approaches, CSS Modules with CSS custom properties was chosen because:

- Single source of truth for colors/spacing via `:root` variables
- Platform-wide changes via CSS variable updates
- Scoped styles prevent conflicts between components
- Excellent TypeScript support
- Industry-standard React pattern

## Architecture

### File Structure

```
webui/src/
├── styles/
│   ├── globals.css              # CSS variables, global styles, resets
│   ├── layout.module.css        # Layout component styles
│   └── pages/
│       ├── domains.module.css   # Domains page styles
│       ├── dashboard.module.css # Dashboard page styles
│       └── login.module.css     # Login page styles
├── main.tsx                     # Imports globals.css
└── modules.d.ts                 # TypeScript declarations for CSS modules
```

### Naming Conventions

- CSS Modules use BEM-like naming: `.block`, `.block__element`, `.block--modifier`
- Class names are semantic and descriptive (not cryptic)
- Consistent prefix patterns for component grouping

### Import Pattern

```tsx
import styles from '../styles/pages/domains.module.css';

// Usage
<div className={styles.pageContainer}>...</div>
```

## Color System

### CSS Variables (`:root`)

```css
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
```

### Color Rationale

- **Primary Red (#d32f2f)**: Security-focused accent color, attention-grabbing for actions
- **Secondary Teal (#00897b)**: Represents secure/authorized states
- **Enterprise Grays**: Professional backdrop that doesn't compete with data
- **Semantic Colors**: Follow Ant Design conventions for consistency

## Component Styles

### Domains Page (`domains.module.css`)

The domains page uses a horizontal selector bar layout:

```css
.pageContainer {
  padding: var(--space-lg);
}

.packageCard {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border-light);
}

.selectorBar {
  display: flex;
  gap: var(--space-md);
  align-items: flex-end;
  padding: var(--space-lg);
  flex-wrap: wrap;
}

.selectorGroup {
  flex: 1 1 250px;
  min-width: 200px;
}

.positionGroup {
  flex: 2 1 400px;
  padding: var(--space-md);
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

.positionLabel {
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.submitButton {
  margin-left: auto;
  background: var(--color-primary);
}
```

### Layout Component (`layout.module.css`)

```css
.layout {
  min-height: 100vh;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  padding: 0 var(--space-lg);
  box-shadow: var(--shadow-md);
}

.logo {
  color: white;
  font-size: 20px;
  font-weight: 700;
}

.logoAccent {
  color: var(--color-primary);
}
```

### Global Styles (`globals.css`)

Contains:

- CSS variable definitions
- Global resets and base styles
- Ant Design component overrides for focus states
- Smooth transitions
- Card hover effects

## Ant Design Integration

The theme config in `App.tsx` references CSS variables:

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

This ensures Ant Design components use the same color system as custom styles.

## Migration Strategy

To migrate from inline styles to CSS modules:

1. Create CSS files and modules.d.ts declaration
2. Import styles in each component
3. Replace `style={{ }}` with `className={styles.*}`
4. Test each component visually

## Future Considerations

- Dark mode support via CSS media queries and variable overrides
- Responsive breakpoints in CSS variables
- Animation library consideration (Framer Motion vs CSS transitions)
- Component library for reusable UI patterns

## References

- Current domains page: [webui/src/pages/Domains.tsx](../../webui/src/pages/Domains.tsx)
- Layout component: [webui/src/components/Layout.tsx](../../webui/src/components/Layout.tsx)
