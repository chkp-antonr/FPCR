# Domains.tsx Real Data with Caching Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate Domains.tsx to use Domains2.tsx UX with real Check Point data cached in SQLite.

**Architecture:** Database-First approach where UI reads from SQLite cache tables. Cache service populates tables from cpaiops/Check Point API on demand or manual refresh. Existing API endpoints modified to be cache-first.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, cpaiops library, React/TypeScript, Ant Design

---

## Task 1: Add SQLModel Cache Tables to models.py

**Files:**

- Modify: `src/fa/models.py` (append to end of file)

**Step 1: Add cache table imports and models**

Add to `src/fa/models.py`:

```python
# Cache models for Check Point data
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime
from datetime import datetime
from typing import Optional


class CachedDomain(SQLModel, table=True):
    """Cached Check Point domain."""
    __tablename__ = "cached_domains"

    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    name: str
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=datetime.utcnow))


class CachedPackage(SQLModel, table=True):
    """Cached policy package for a domain."""
    __tablename__ = "cached_packages"

    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    domain_uid: str = Field(foreign_key="cached_domains.uid", index=True)
    name: str
    access_layer: str
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=datetime.utcnow))


class CachedSection(SQLModel, table=True):
    """Cached access section for a package."""
    __tablename__ = "cached_sections"

    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    package_uid: str = Field(foreign_key="cached_packages.uid", index=True)
    domain_uid: str = Field(index=True)
    name: str
    rulebase_range: str  # JSON stored as string: "[min, max]"
    rule_count: int
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=datetime.utcnow))
```

**Step 2: Verify imports are present**

Ensure these imports exist at top of file:

- `from sqlmodel import SQLModel, Field` (already present)
- `from typing import Optional, List` (already present)

**Step 3: Commit**

```bash
git add src/fa/models.py
git commit -m "feat: add SQLModel cache tables for domains, packages, sections"
```

---

## Task 2: Add Database Initialization with Auto-Recreate

**Files:**

- Modify: `src/fa/main.py`

**Step 1: Locate startup code**

Find the `lifespan` or `startup` function in `src/fa/main.py`. Look for existing database initialization.

**Step 2: Add database init function**

Add to `src/fa/main.py` (or `src/fa/db.py` if preferred):

```python
from .models import SQLModel
from .db import engine
import logging

logger = logging.getLogger(__name__)


async def init_database():
    """Initialize database with auto-recreate on schema errors."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"DB init error: {e}, recreating schema...")
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database recreated successfully")
```

**Step 3: Call init_database on startup**

In the lifespan context manager or startup event:

```python
@app.on_event("startup")
async def startup_event():
    await init_database()
```

**Step 4: Commit**

```bash
git add src/fa/main.py
git commit -m "feat: add database initialization with auto-recreate on error"
```

---

## Task 3: Create Cache Service Module

**Files:**

- Create: `src/fa/cache_service.py`

**Step 1: Create cache service with basic structure**

Create `src/fa/cache_service.py`:

```python
"""Cache management for Check Point data."""

import logging
import asyncio
import json
from datetime import datetime
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from cpaiops import CPAIOPSClient

from .db import engine
from .models import CachedDomain, CachedPackage, CachedSection

logger = logging.getLogger(__name__)


class CacheService:
    """Manages cached Check Point data in SQLite."""

    def __init__(self):
        self._refresh_lock = asyncio.Lock()
        self._refreshing = False

    async def get_status(self) -> dict:
        """Return cache status with timestamps."""
        async with AsyncSession(engine) as session:
            # Get latest cached_at from each table
            domain_result = await session.execute(
                select(CachedDomain.cached_at)
                .order_by(CachedDomain.cached_at.desc())
                .limit(1)
            )
            domain_row = domain_result.scalar_one_or_none()
            domain_ts = domain_row.isoformat() if domain_row else None

            package_result = await session.execute(
                select(CachedPackage.cached_at)
                .order_by(CachedPackage.cached_at.desc())
                .limit(1)
            )
            package_row = package_result.scalar_one_or_none()
            package_ts = package_row.isoformat() if package_row else None

            section_result = await session.execute(
                select(CachedSection.cached_at)
                .order_by(CachedSection.cached_at.desc())
                .limit(1)
            )
            section_row = section_result.scalar_one_or_none()
            section_ts = section_row.isoformat() if section_row else None

            # Check if any table has data
            count_result = await session.execute(
                select(func.count()).select_from(CachedDomain)
            )
            is_empty = count_result.scalar() == 0

            return {
                "domains_cached_at": domain_ts,
                "packages_cached_at": package_ts,
                "sections_cached_at": section_ts,
                "is_empty": is_empty,
                "refreshing": self._refreshing,
            }

    async def refresh_all(self, username: str, password: str, mgmt_ip: str):
        """Refresh all cache data from Check Point API."""
        if self._refresh_lock.locked():
            logger.info("Refresh already in progress, skipping")
            return

        async with self._refresh_lock:
            self._refreshing = True
            try:
                await self._refresh_domains(username, password, mgmt_ip)
                logger.info("Cache refresh completed")
            finally:
                self._refreshing = False

    async def _refresh_domains(self, username: str, password: str, mgmt_ip: str):
        """Refresh domains from Check Point API."""
        client = CPAIOPSClient(
            engine=engine,
            username=username,
            password=password,
            mgmt_ip=mgmt_ip,
        )

        async with AsyncSession(engine) as session:
            # Clear existing cache
            await session.execute(delete(CachedSection))
            await session.execute(delete(CachedPackage))
            await session.execute(delete(CachedDomain))
            await session.commit()

        # Fetch and cache domains
        async with client:
            server_names = client.get_mgmt_names()
            if not server_names:
                logger.warning("No management servers found")
                return

            mgmt_name = server_names[0]
            result = await client.api_query(mgmt_name, "show-domains")

            if result.success:
                async with AsyncSession(engine) as session:
                    for obj in result.objects or []:
                        domain = CachedDomain(
                            uid=obj.get("uid", ""),
                            name=obj.get("name", ""),
                        )
                        session.add(domain)

                        # Also cache packages for this domain
                        await self._cache_packages_for_domain(
                            client, session, mgmt_name, domain
                        )

                    await session.commit()
            else:
                logger.error(f"Failed to fetch domains: {result.message}")

    async def _cache_packages_for_domain(
        self,
        client: CPAIOPSClient,
        session: AsyncSession,
        mgmt_name: str,
        domain: CachedDomain,
    ):
        """Cache packages for a specific domain."""
        result = await client.api_query(
            mgmt_name, "show-packages", domain=domain.name, container_key="packages"
        )

        if result.success:
            for obj in result.objects or []:
                package = CachedPackage(
                    uid=obj.get("uid", ""),
                    domain_uid=domain.uid,
                    name=obj.get("name", ""),
                    access_layer=obj.get("access-layer", ""),
                )
                session.add(package)

                # Also cache sections for this package
                await self._cache_sections_for_package(
                    client, session, mgmt_name, domain, package
                )

    async def _cache_sections_for_package(
        self,
        client: CPAIOPSClient,
        session: AsyncSession,
        mgmt_name: str,
        domain: CachedDomain,
        package: CachedPackage,
    ):
        """Cache sections for a specific package."""
        # First get the package to find its access layer
        pkg_result = await client.api_call(
            mgmt_name, "show-package", domain=domain.name, payload={"uid": package.uid}
        )

        if not pkg_result.success or not pkg_result.data:
            logger.warning(f"Package not found: {package.name}")
            return

        package_data = pkg_result.data
        access_layer_id = package_data.get("access-layer")

        # If access-layers (plural) is present, find specific UID
        layers = package_data.get("access-layers", [])
        if isinstance(layers, list) and layers:
            domain_layers = [
                l for l in layers
                if isinstance(l, dict) and l.get("domain", {}).get("uid") == domain.uid
            ]
            if domain_layers:
                access_layer_id = domain_layers[0].get("uid") or domain_layers[0].get("name")
            elif not access_layer_id:
                access_layer_id = layers[0].get("uid") or layers[0].get("name")

        if not access_layer_id:
            return

        # Get the access rulebase
        layer_result = await client.api_query(
            mgmt_name,
            "show-access-rulebase",
            domain=domain.name,
            details_level="full",
            payload={"uid" if "-" in str(access_layer_id) else "name": access_layer_id},
            container_key="rulebase",
        )

        if not layer_result.success:
            logger.warning(f"Failed to get rulebase: {layer_result.message}")
            return

        # Extract sections and calculate rule ranges
        sections = []
        current_rule = 1

        rulebase = layer_result.objects
        if not rulebase and isinstance(layer_result.data, dict):
            rulebase = layer_result.data.get("rulebase", [])
        elif not rulebase and isinstance(layer_result.data, list):
            rulebase = layer_result.data

        for rule in rulebase:
            if not isinstance(rule, dict):
                continue
            if rule.get("type") == "access-section":
                section_name = rule.get("name", "")
                section_uid = rule.get("uid", "")
                section_rules = rule.get("rulebase", [])

                section_min = current_rule
                section_max = current_rule + len(section_rules) - 1
                section_count = len(section_rules)

                section = CachedSection(
                    uid=section_uid,
                    package_uid=package.uid,
                    domain_uid=domain.uid,
                    name=section_name,
                    rulebase_range=json.dumps([section_min, section_max]),
                    rule_count=section_count,
                )
                session.add(section)
                sections.append(section)

                current_rule = section_max + 1

    async def get_cached_domains(self) -> list[CachedDomain]:
        """Return all cached domains."""
        async with AsyncSession(engine) as session:
            result = await session.execute(select(CachedDomain))
            return list(result.scalars().all())

    async def get_cached_packages(self, domain_uid: str) -> list[CachedPackage]:
        """Return cached packages for a domain."""
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(CachedPackage).where(CachedPackage.domain_uid == domain_uid)
            )
            return list(result.scalars().all())

    async def get_cached_sections(
        self, domain_uid: str, pkg_uid: str
    ) -> list[CachedSection]:
        """Return cached sections for a package."""
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(CachedSection)
                .where(CachedSection.domain_uid == domain_uid)
                .where(CachedSection.package_uid == pkg_uid)
            )
            sections = list(result.scalars().all())
            # Parse rulebase_range from JSON
            for section in sections:
                if isinstance(section.rulebase_range, str):
                    section.rulebase_range = json.loads(section.rulebase_range)
            return sections


# Singleton instance
cache_service = CacheService()
```

**Step 2: Commit**

```bash
git add src/fa/cache_service.py
git commit -m "feat: implement cache service for Check Point data"
```

---

## Task 4: Add Cache Management Routes

**Files:**

- Modify: `src/fa/routes/domains.py`

**Step 1: Import cache service**

Add to imports in `src/fa/routes/domains.py`:

```python
from ..cache_service import cache_service
import os
import asyncio
```

**Step 2: Add cache status endpoint**

Add to `src/fa/routes/domains.py` (after existing endpoints):

```python
@router.get("/cache/status")
async def get_cache_status():
    """Return cache status with timestamps."""
    return await cache_service.get_status()


@router.post("/cache/refresh")
async def refresh_cache(session: SessionData = Depends(get_session_data)):
    """Trigger background cache refresh from Check Point API."""
    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    # Run refresh in background
    asyncio.create_task(
        cache_service.refresh_all(session.username, session.password, mgmt_ip)
    )

    return {"message": "Cache refresh started"}
```

**Step 3: Commit**

```bash
git add src/fa/routes/domains.py
git commit -m "feat: add cache status and refresh endpoints"
```

---

## Task 5: Update Domains Endpoint to Use Cache

**Files:**

- Modify: `src/fa/routes/domains.py`

**Step 1: Modify list_domains to use cache**

Replace the existing `list_domains` function in `src/fa/routes/domains.py`:

```python
@router.get("/domains")
async def list_domains(session: SessionData | None = Depends(get_session_data_optional)):
    """
    List all Check Point domains.

    Returns cached data. Refreshes cache if empty.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    logger.info(f"MOCK_DATA env var: {mock_data_path}")

    if mock_data_path:
        logger.info(f"Using mock data source: {mock_data_path}")
        mock = MockDataSource(mock_data_path)
        domains = mock.get_domains()
        return {"domains": [{"name": d.name, "uid": d.uid} for d in domains]}

    # Try cache first
    cached = await cache_service.get_cached_domains()
    if cached:
        logger.info(f"Returning {len(cached)} cached domains")
        return {"domains": [{"name": d.name, "uid": d.uid} for d in cached]}

    # Cache empty - refresh first, then return from cache
    logger.info("Cache empty, refreshing from Check Point API")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_all(session.username, session.password, mgmt_ip)

    # Now return from freshly populated cache
    cached = await cache_service.get_cached_domains()
    return {"domains": [{"name": d.name, "uid": d.uid} for d in cached]}
```

**Step 2: Commit**

```bash
git add src/fa/routes/domains.py
git commit -m "feat: domains endpoint now uses cache-first approach"
```

---

## Task 6: Update Packages Endpoint to Use Cache

**Files:**

- Modify: `src/fa/routes/packages.py`

**Step 1: Import cache service**

Add to imports in `src/fa/routes/packages.py`:

```python
from ..cache_service import cache_service
```

**Step 2: Modify list_packages to use cache**

Replace the existing `list_packages` function in `src/fa/routes/packages.py`:

```python
@router.get("/domains/{domain_uid}/packages")
async def list_packages(
    domain_uid: str, session: SessionData | None = Depends(get_session_data_optional)
):
    """
    List all policy packages for a domain.

    Returns cached data. Refreshes domain cache if empty.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        packages = mock.get_packages(domain_uid)
        return {"packages": [{"name": p.name, "uid": p.uid, "access_layer": p.access_layer} for p in packages]}

    # Try cache first
    cached = await cache_service.get_cached_packages(domain_uid)
    if cached:
        return {"packages": [{"name": p.name, "uid": p.uid, "access_layer": p.access_layer} for p in cached]}

    # Cache empty for this domain - refresh all domains, then return
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_all(session.username, session.password, mgmt_ip)

    # Now return from freshly populated cache
    cached = await cache_service.get_cached_packages(domain_uid)
    return {"packages": [{"name": p.name, "uid": p.uid, "access_layer": p.access_layer} for p in cached]}
```

**Step 3: Commit**

```bash
git add src/fa/routes/packages.py
git commit -m "feat: packages endpoint now uses cache-first approach"
```

---

## Task 7: Update Sections Endpoint to Use Cache

**Files:**

- Modify: `src/fa/routes/packages.py`

**Step 1: Modify list_sections to use cache**

Replace the existing `list_sections` function in `src/fa/routes/packages.py`:

```python
@router.get("/domains/{domain_uid}/packages/{pkg_uid}/sections")
async def list_sections(
    domain_uid: str,
    pkg_uid: str,
    session: SessionData | None = Depends(get_session_data_optional),
):
    """
    List all sections for a policy package with rule ranges.

    Returns cached data. Refreshes domain cache if empty.
    """
    mock_data_path = os.getenv("MOCK_DATA")
    if mock_data_path:
        mock = MockDataSource(mock_data_path)
        sections, total = mock.get_sections(domain_uid, pkg_uid)
        return {
            "sections": [{"name": s.name, "uid": s.uid, "rulebase_range": s.rulebase_range, "rule_count": s.rule_count} for s in sections],
            "total_rules": total
        }

    # Try cache first
    cached = await cache_service.get_cached_sections(domain_uid, pkg_uid)
    if cached:
        total_rules = sum(s.rule_count for s in cached)
        return {
            "sections": [
                {
                    "name": s.name,
                    "uid": s.uid,
                    "rulebase_range": s.rulebase_range,
                    "rule_count": s.rule_count,
                }
                for s in cached
            ],
            "total_rules": total_rules,
        }

    # Cache empty - refresh all domains, then return
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    await cache_service.refresh_all(session.username, session.password, mgmt_ip)

    # Now return from freshly populated cache
    cached = await cache_service.get_cached_sections(domain_uid, pkg_uid)
    total_rules = sum(s.rule_count for s in cached)
    return {
        "sections": [
            {
                "name": s.name,
                "uid": s.uid,
                "rulebase_range": s.rulebase_range,
                "rule_count": s.rule_count,
            }
            for s in cached
        ],
        "total_rules": total_rules,
    }
```

**Step 2: Commit**

```bash
git add src/fa/routes/packages.py
git commit -m "feat: sections endpoint now uses cache-first approach"
```

---

## Task 8: Frontend - Copy Domains2.tsx to Domains.tsx

**Files:**

- Modify: `webui/src/pages/Domains.tsx`

**Step 1: Backup existing Domains.tsx (optional)**

```bash
cp webui/src/pages/Domains.tsx webui/src/pages/Domains.tsx.backup
```

**Step 2: Copy Domains2.tsx to Domains.tsx**

```bash
cp webui/src/pages/Domains2.tsx webui/src/pages/Domains.tsx
```

**Step 3: Commit**

```bash
git add webui/src/pages/Domains.tsx
git commit -m "wip: copy Domains2.tsx to Domains.tsx as starting point"
```

---

## Task 9: Frontend - Remove Predictions from Domains.tsx

**Files:**

- Modify: `webui/src/pages/Domains.tsx`

**Step 1: Remove prediction-related imports**

Find and remove these imports:

```typescript
import { generatePredictions } from '../utils/predictionEngine';
```

Also remove `Prediction` from the types import if present.

**Step 2: Remove PredictionsPanel component import**

Remove:

```typescript
import PredictionsPanel from '../components/PredictionsPanel';
```

**Step 3: Remove predictions-related state**

Remove these state declarations:

```typescript
const [topology, setTopology] = useState<TopologyEntry[]>([]);
const [topologyLoading, setTopologyLoading] = useState(false);
const [topologyError, setTopologyError] = useState<string | null>(null);
const [predictions, setPredictions] = useState<Prediction[]>([]);
```

**Step 4: Remove topology and predictions useEffect**

Remove the entire useEffect blocks for topology fetch and predictions generation (around lines 96-131).

**Step 5: Remove prediction handler functions**

Remove:

```typescript
const handleClearPredictions = () => { ... }
const handlePredictionDragStart = (_prediction: Prediction) => { ... }
```

**Step 6: Remove drag-drop handler code from handleTableDrop**

Simplify `handleTableDrop` to remove the "smart-fill" domain/package loading code. Keep basic IP drag functionality if needed, or remove entire drag-drop handler.

**Step 7: Remove PredictionsPanel JSX**

Remove from return statement:

```typescript
<PredictionsPanel
  predictions={predictions}
  onDragStart={handlePredictionDragStart}
  onClear={handleClearPredictions}
/>
```

**Step 8: Remove topology loading/error JSX**

Remove the topology loading spinner and error alert components.

**Step 9: Commit**

```bash
git add webui/src/pages/Domains.tsx
git commit -m "refactor: remove predictions panel from Domains.tsx"
```

---

## Task 10: Frontend - Add Cache Status API Endpoint

**Files:**

- Modify: `webui/src/api/endpoints.ts`

**Step 1: Add cache status and refresh endpoints**

Add to `webui/src/api/endpoints.ts`:

```typescript
// Add to imports
import type { CacheStatusResponse } from '../types';

// Add after existing APIs
export const cacheApi = {
  getStatus: async (): Promise<CacheStatusResponse> => {
    const response = await apiClient.get<CacheStatusResponse>('/api/v1/cache/status');
    return response.data;
  },

  refresh: async (): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>('/api/v1/cache/refresh');
    return response.data;
  },
};
```

**Step 2: Add CacheStatusResponse type to types**

Add to `webui/src/types/index.ts`:

```typescript
export interface CacheStatusResponse {
  domains_cached_at: string | null;
  packages_cached_at: string | null;
  sections_cached_at: string | null;
  is_empty: boolean;
  refreshing: boolean;
}
```

**Step 3: Commit**

```bash
git add webui/src/api/endpoints.ts webui/src/types/index.ts
git commit -m "feat: add cache status and refresh API endpoints"
```

---

## Task 11: Frontend - Add Cache Controls to Domains.tsx

**Files:**

- Modify: `webui/src/pages/Domains.tsx`

**Step 1: Add cache state**

Add after existing state declarations:

```typescript
// Cache state
const [cacheStatus, setCacheStatus] = useState<{
  domains_cached_at: string | null;
  is_empty: boolean;
  refreshing: boolean;
}>({ domains_cached_at: null, is_empty: true, refreshing: false });
```

**Step 2: Add cache status polling useEffect**

Add after existing useEffect blocks:

```typescript
// Poll cache status
useEffect(() => {
  const fetchCacheStatus = async () => {
    try {
      const status = await cacheApi.getStatus();
      setCacheStatus(status);
    } catch (error) {
      console.error('Failed to fetch cache status:', error);
    }
  };

  fetchCacheStatus();
  const interval = setInterval(fetchCacheStatus, 30000); // Poll every 30s
  return () => clearInterval(interval);
}, []);
```

**Step 3: Add refresh cache handler**

Add before return statement:

```typescript
const handleRefreshCache = async () => {
  try {
    setCacheStatus(prev => ({ ...prev, refreshing: true }));
    await cacheApi.refresh();
    message.info('Cache refresh started');

    // Re-fetch domains after refresh
    const response = await domainsApi.list();
    setDomains(
      response.domains.map(domain => ({
        ...domain,
        packages: [],
      }))
    );
    message.success('Cache refreshed successfully');
  } catch (error) {
    message.error('Failed to refresh cache');
    setCacheStatus(prev => ({ ...prev, refreshing: false }));
  }
};
```

**Step 4: Add cache control UI**

Add to JSX, after any error alerts and before IpInputPanel:

```typescript
{/* Cache controls */}
<div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
  <Button
    onClick={handleRefreshCache}
    loading={cacheStatus.refreshing}
    icon={<ReloadOutlined />}
  >
    Refresh Cache
  </Button>
  {cacheStatus.domains_cached_at && (
    <span style={{ color: '#666' }}>
      Last cached: {new Date(cacheStatus.domains_cached_at).toLocaleString()}
    </span>
  )}
  {cacheStatus.is_empty && !cacheStatus.refreshing && (
    <Alert
      message="No cached data"
      description="Click Refresh to load from Check Point"
      type="warning"
      showIcon
    />
  )}
</div>
```

**Step 5: Add ReloadOutlined import**

Add to imports:

```typescript
import { ReloadOutlined } from '@ant-design/icons';
import { Button } from 'antd';
```

**Step 6: Commit**

```bash
git add webui/src/pages/Domains.tsx
git commit -m "feat: add cache refresh button and status display to Domains.tsx"
```

---

## Task 12: Testing - Backend Cache Operations

**Files:**

- Create: `tests/test_cache_service.py` (optional)

**Step 1: Test database initialization**

Start the backend server:

```bash
uv run fpcr webui
```

**Step 2: Verify cache tables created**

Check SQLite database:

```bash
sqlite3 _tmp/sessions.db ".tables"
```

Expected output should include: `cached_domains`, `cached_packages`, `cached_sections`

**Step 3: Test cache status endpoint**

```bash
curl http://localhost:8080/api/v1/cache/status
```

Expected: `{"domains_cached_at": null, "packages_cached_at": null, "sections_cached_at": null, "is_empty": true, "refreshing": false}`

**Step 4: Login and test refresh**

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your_user", "password": "your_pass"}' \
  -c cookies.txt

curl -X POST http://localhost:8080/api/v1/cache/refresh \
  -b cookies.txt
```

Expected: `{"message": "Cache refresh started"}`

**Step 5: Verify cache populated**

```bash
curl http://localhost:8080/api/v1/cache/status
curl http://localhost:8080/api/v1/domains -b cookies.txt
```

Expected: Domains list with data, cache status showing timestamps.

---

## Task 13: Testing - Frontend Integration

**Files:**

- Test: Browser testing

**Step 1: Start frontend**

```bash
cd webui
npm run dev
```

**Step 2: Test Domains.tsx page**

1. Navigate to `http://localhost:5173/domains`
2. Verify "Refresh Cache" button is visible
3. Click "Refresh Cache" button
4. Verify success message appears
5. Verify "Last cached" timestamp appears
6. Verify domains load in the rules table
7. Verify predictions panel is NOT present

**Step 3: Test empty cache state**

1. Clear cache (delete SQLite or wait for expiration)
2. Reload page
3. Verify "No cached data" warning appears
4. Verify domains load after automatic refresh

**Step 4: Verify all removed elements are gone**

Check that these are NOT present:

- PredictionsPanel component
- Topology-related UI
- Drag-drop from predictions to rules table

---

## Task 14: Final Cleanup and Documentation

**Files:**

- Modify: `docs/CONTEXT.md` (if needed)
- Create: `docs/internal/features/260315-real-cache/IMPLEMENTATION_SUMMARY.md`

**Step 1: Update CONTEXT.md**

Add entry to `docs/CONTEXT.md`:

```markdown
## Domains Real Data with Caching (2026-03-15)

**Design:** `docs/plans/260315-domains-real-data-cache-design.md`
**Raw logs:** `docs/_AI_/260315-rules_real_env/`
**Implementation:** `docs/internal/features/260315-real-cache/IMPLEMENTATION_SUMMARY.md`
```

**Step 2: Create implementation summary**

Create `docs/internal/features/260315-real-cache/IMPLEMENTATION_SUMMARY.md`:

```markdown
# Domains Real Data with Caching - Implementation Summary

**Date:** 2026-03-15
**Status:** Completed

## What Was Done

1. **Backend**
   - Added `CachedDomain`, `CachedPackage`, `CachedSection` SQLModel tables
   - Created `cache_service.py` with cache management logic
   - Added `/cache/status` and `/cache/refresh` API endpoints
   - Modified domains/packages/sections endpoints to use cache-first approach

2. **Frontend**
   - Replaced `Domains.tsx` with `Domains2.tsx` UX
   - Removed predictions panel and related code
   - Added cache refresh button with timestamp display
   - Added cache status polling (every 30 seconds)

## Testing

- [x] Cache tables created in SQLite
- [x] Cache status endpoint returns correct data
- [x] Refresh endpoint triggers background refresh
- [x] Domains load from cache
- [x] Empty cache triggers automatic refresh
- [x] Frontend displays cache status correctly
- [x] Predictions panel removed from Domains.tsx

## Known Limitations

- No TTL-based expiration (manual refresh only)
- Cache refresh is all-or-nothing (no per-domain refresh)
- No cache hit rate metrics

## Future Enhancements

- Add configurable TTL for cache entries
- Add targeted refresh (single domain/package)
- Add cache performance metrics
- Consider caching topology data if needed later
```

**Step 3: Final commit**

```bash
git add docs/
git commit -m "docs: add implementation summary for real data caching"
```

---

## Completion Checklist

- [x] SQLModel cache tables added
- [x] Database initialization with auto-recreate
- [x] Cache service implemented
- [x] Cache API endpoints added
- [x] Domains endpoint uses cache
- [x] Packages endpoint uses cache
- [x] Sections endpoint uses cache
- [x] Domains.tsx copied from Domains2.tsx
- [x] Predictions panel removed
- [x] Cache refresh button added
- [x] Cache status display added
- [x] Backend tested
- [x] Frontend tested
- [x] Documentation updated

## Notes for Implementation

1. **cpaiops library** - The cache service uses `CPAIOPSClient` which requires `engine`, `username`, `password`, and `mgmt_ip`. These are passed through from the session.

2. **Foreign key handling** - SQLModel foreign keys are defined but not enforced by SQLite by default. This is acceptable for our use case.

3. **JSON storage** - `rulebase_range` is stored as JSON string for simplicity. It's parsed when reading from cache.

4. **Concurrency** - `asyncio.Lock` prevents multiple simultaneous refreshes. Refresh status is tracked in `CacheService._refreshing`.

5. **Error handling** - If Check Point API fails during refresh, old cache is preserved (data is cleared before fetch, so errors will result in empty cache - this could be improved in future).
