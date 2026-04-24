# FPCR WebUI - Design Document

**Date:** 2026-02-19

**Status:** Approved

**Author:** AI Assistant

**Reference:** W:\MMP\ (FastAPI + React application)

---

## Overview

Add a FastAPI backend with React TypeScript frontend to the existing FPCR CLI tool. The WebUI provides a browser interface for Check Point operations, starting with domain listing functionality.

### Key Differences from Reference (MMP)

| Aspect | MMP (Reference) | FPCR WebUI |
|--------|-----------------|------------|
| Authentication | LDAP | RADIUS (mocked initially with .env) |
| CP Credentials | Single service account | Per-user credentials (same as RADIUS) |
| Architecture | Plugin-based | Monolithic for MVP |
| Project | Standalone | Integrated into existing FPCR |

---

## Architecture

### Approach: Monolithic FastAPI + Session-Based Auth

**Selected for:** Simplicity, fastest path to working MVP, leverages existing cpaiops code.

### Project Structure

```
fpcr/
├── src/
│   ├── fpcr.py              # Existing CLI (unchanged)
│   ├── cpsearch.py          # Existing module (unchanged)
│   ├── cpcrud/              # Existing module (unchanged)
│   ├── utils.py             # Existing module (unchanged)
│   └── fa/                  # NEW: FastAPI application
│       ├── __init__.py
│       ├── app.py           # FastAPI application factory
│       ├── config.py        # Settings via pydantic-settings
│       ├── models.py        # Pydantic models
│       ├── auth.py          # Authentication routes & logic
│       ├── session.py       # Session management (SQLite)
│       └── routes/
│           ├── __init__.py
│           ├── auth.py      # /api/v1/auth/* endpoints
│           ├── domains.py   # /api/v1/domains endpoint
│           └── health.py    # /api/v1/health endpoint
├── webui/                   # NEW: React frontend
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts    # Axios instance with interceptors
│   │   │   └── endpoints.ts # Typed API functions
│   │   ├── components/
│   │   │   ├── Layout.tsx   # Main layout shell
│   │   │   └── ProtectedRoute.tsx # Auth guard
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx # Global auth state
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   └── Domains.tsx
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── public/
│   │   └── favicon.ico
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── docs/
│   └── internal/features/260219-webui/
│       ├── DESIGN.md         # This file
│       └── IMPLEMENTATION_SUMMARY.md
├── pyproject.toml           # Extended with FastAPI deps
├── .env                     # Extended with WEBUI_* vars
└── .env.secrets             # RADIUS mock credentials
```

---

## Authentication Flow

### Login Flow

1. User enters username/password (single set of credentials)
2. Frontend POSTs to `/api/v1/auth/login`
3. Backend validates via RADIUS (mocked with .env for MVP)
4. On success: creates session, stores encrypted credentials in SQLite
5. Response sets `session_id` cookie (httpOnly)
6. Frontend redirects to Dashboard

### Session Management

**Storage:** SQLite (`sessions.db`)

**Schema:**

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    password_encrypted TEXT NOT NULL,
    created_at TIMESTAMP,
    last_accessed TIMESTAMP
);
```

**Encryption:** Passwords encrypted at rest using `cryptography.fernet`

**Expiry:** Sessions expire after configurable hours (default: 8)

### Per-User CP Client

Each authenticated request creates a fresh `CPAIOPSClient` using the user's stored credentials:

```python
client = CPAIOPSClient(
    username=session.username,
    password=session.password,
    mgmt_ip=settings.api_mgmt
)
```

---

## API Routes

**Base URL:** `/api/v1`

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/auth/login` | Login, create session | No |
| POST | `/auth/logout` | Destroy session | Yes |
| GET | `/auth/me` | Get current user info | Yes |
| GET | `/health` | Health check | No |
| GET | `/domains` | List all domains | Yes |

**Documentation URLs:**

- `/api/v1/docs` - Swagger UI
- `/api/v1/redoc` - ReDoc
- `/api/v1/openapi.json` - OpenAPI schema

---

## React Frontend

### Tech Stack

- React 19.2.0 + TypeScript
- Vite (build tool & dev server)
- Ant Design 6.1.3 (UI components)
- React Router 7.0.0 (routing)
- Axios 1.7.0 (HTTP client)

### Page Structure

| Route | Component | Description |
|-------|-----------|-------------|
| `/login` | Login.tsx | Login form |
| `/` | Dashboard.tsx | Welcome page |
| `/domains` | Domains.tsx | Domains list/table |

### Layout

- Header: Logo, user info, logout button
- Sidebar: Navigation menu (Dashboard, Domains)
- Main content area: Page content

---

## Configuration

### Environment Variables

```bash
# Existing FPCR variables
API_MGMT=192.168.1.1
LOG_LEVEL=INFO

# RADIUS (future)
RADIUS_SERVER=radius.example.com
RADIUS_SECRET=shared_secret
RADIUS_TIMEOUT=5

# WebUI
WEBUI_HOST=0.0.0.0
WEBUI_PORT=8000
WEBUI_SECRET_KEY=<generate-random-string>
WEBUI_SESSION_AGE_HOURS=8
WEBUI_CORS_ORIGINS=http://localhost:5173

# Frontend (Vite)
VITE_API_BASE_URL=http://localhost:8000
```

### Secrets (.env.secrets - gitignored)

```bash
# RADIUS mock (temporary)
API_USERNAME=admin
API_PASSWORD=SecretPassword123
```

---

## Deployment

### Development

**Option A - Full Dev Mode:**

```bash
# Terminal 1 - Backend
uv run uvicorn src.fa.app:app --reload --reload-exclude ".venv" --port 8000

# Terminal 2 - Frontend
cd webui && npm run dev
```

Access: `http://localhost:5173`

**Option B - Backend Serving React:**

```bash
cd webui && npm run build && cd ..
uv run uvicorn src.fa.app:app --reload --reload-exclude ".venv" --port 8000
```

Access: `http://localhost:8000`

### Production

1. Build React: `cd webui && npm run build`
2. FastAPI serves static files via `StaticFiles`
3. Run: `uv run uvicorn src.fa.app:app --host 0.0.0.0 --port 8000`

### Static File Handling

- `/assets/*` - Static assets (CSS, JS, images)
- `/favicon.ico` - Special handler (returns favicon or index.html)
- `/*` - Catch-all serves `index.html` (SPA routing)
- `/api/*` - API routes (excluded from catch-all)

---

## Dependencies to Add

### Backend (pyproject.toml)

```toml
dependencies = [
    # Existing...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "python-multipart>=0.0.9",
    "cryptography>=43.0.0",
]
```

### Frontend (package.json)

```json
{
  "dependencies": {
    "react": "^19.2.0",
    "react-router-dom": "^7.0.0",
    "antd": "^6.1.3",
    "axios": "^1.7.0",
    "@ant-design/icons": "^5.5.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "typescript": "^5.6.0",
    "@types/react": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0"
  }
}
```

---

## Error Handling

### Backend Error Responses

| Status | Body | UX Handling |
|--------|------|-------------|
| 401 | `{"error": "Invalid credentials"}` | Login form error message |
| 401 | `{"error": "Authentication required"}` | Redirect to login |
| 503 | `{"error": "Authentication service unavailable"}` | Error message, retry |
| 500 | `{"error": "Internal server error"}` | Generic error message |

### Frontend Error Handling

- Axios interceptor redirects to login on 401
- Ant Design `message` component for user feedback
- Error boundaries for React crashes

---

## Testing Checklist

### Manual Testing

- [ ] Login with valid credentials
- [ ] Login with invalid credentials
- [ ] Session persists across page refresh
- [ ] Logout clears session
- [ ] Domains page loads after login
- [ ] Session expires after inactivity
- [ ] Vite dev mode proxies API correctly
- [ ] Production build serves correctly via FastAPI
- [ ] Favicon loads correctly
- [ ] API docs accessible at `/api/v1/docs`

### Automated Tests (Future)

- Backend: pytest for auth, session, domains endpoints
- Frontend: Vitest + React Testing Library for components

---

## Future Enhancements (Out of Scope for MVP)

- Real RADIUS client (replace mock)
- Role-based access control (RBAC)
- Additional pages (search, CRUD operations)
- Session activity monitoring
- Audit logging
- Multi-domain management server support
- WebSocket for real-time updates
