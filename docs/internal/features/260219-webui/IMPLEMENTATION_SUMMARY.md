# FPCR WebUI - Implementation Summary

**Date:** 2026-02-19
**Status:** Complete

## What Was Built

FastAPI backend with React TypeScript frontend for the FPCR tool.

### Backend (`src/fa/`)

- `app.py` - FastAPI application factory with static file serving
- `config.py` - Pydantic settings management with WEBUI_ prefix
- `session.py` - SQLite-based session manager with password encryption
- `radius.py` - RADIUS credential validation (mocked for MVP)
- `models.py` - Pydantic request/response models
- `routes/` - API endpoints (auth, domains, health)

### Frontend (`webui/`)

- React 19 + TypeScript + Vite
- Ant Design UI components
- React Router for navigation
- Axios for API calls with interceptors
- Context-based authentication

### Features

1. **Authentication**
   - Login via RADIUS (mocked with .env for MVP)
   - Session-based auth with SQLite storage
   - Passwords encrypted at rest
   - httpOnly cookies for session ID

2. **Domains Page**
   - Lists all Check Point domains
   - Uses per-user credentials for API calls
   - Sortable table with pagination

3. **Development**
   - Hot reload via Vite dev server (port 5173)
   - API proxy to FastAPI (port 8000)

4. **Production**
   - Single FastAPI server serves both API and static files
   - API docs at `/api/v1/docs`

## How to Run

### Development (Two terminals)

Terminal 1:
```bash
uv run uvicorn src.fa.app:app --reload --reload-exclude ".venv" --port 8000
```

Terminal 2:
```bash
cd webui && npm run dev
```

Visit: http://localhost:5173

### Production (Single terminal)

```bash
cd webui && npm run build && cd ..
uv run uvicorn src.fa.app:app --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000

## Environment Variables Required

```bash
# .env
API_MGMT=192.168.1.1
WEBUI_SECRET_KEY=<proper-fernet-key>
WEBUI_SESSION_AGE_HOURS=8
WEBUI_CORS_ORIGINS=http://localhost:5173,http://localhost:8000

# .env.secrets
API_USERNAME=admin
API_PASSWORD=SecretPassword123
```

## Implementation Notes

### Fernet Key Generation
The WEBUI_SECRET_KEY must be a proper Fernet key (32 bytes, base64-url-safe encoded).
Generate with:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### pydantic_settings Configuration
- Uses `WEBUI_` env prefix
- `.env` file is loaded via `python-dotenv`
- `extra="ignore"` to skip unrelated env vars
- `cors_origins` is stored as string, accessed via `cors_origins_list` property

## Future Enhancements

- Real RADIUS client implementation
- Additional pages (search, CRUD)
- Role-based access control
- Audit logging
- WebSocket for real-time updates
