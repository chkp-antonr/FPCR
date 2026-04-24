# Domains.tsx Real Data with Caching Design

**Date:** 2026-03-15

**Status:** Approved

**Author:** Design Session

## Overview

Migrate `Domains.tsx` to use the same UX as `Domains2.tsx` (RulesTable-based), but remove the predictions panel and integrate real Check Point data with SQLite caching.

## Key Requirements

1. Replace `Domains.tsx` UX with `Domains2.tsx` UX (RulesTable component)
2. Remove predictions panel from `Domains.tsx`
3. Use real Check Point data via `cpaiops` library (no mock data)
4. Cache domains, packages, and sections to SQLite (`DATABASE_URL`)
5. Add "Refresh cache" button in the UI
6. Keep Submit button as-is (no actual rule implementation)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI Component | RulesTable (like Domains2.tsx) | Consistent admin interface |
| Cache Scope | Global (shared) | Simpler, all users see same data |
| Cache Invalidation | Manual refresh now, TTL later | Simple initial implementation |
| Cached Data | Domains, Packages, Sections | Core data needed for rules |
| Topology | Not cached | Used only for predictions (being removed) |
| Architecture | Database-First | UI reads directly from SQLite |
| Cache Miss | Refresh then return from cache | Cache as single source of truth |
| Schema Changes | Auto-reinitialize on error | No migrations needed |

## Architecture

```
┌─────────────┐      ┌──────────────────┐     ┌─────────────┐
│  Domains.tsx│────▶│  API Endpoints   │────▶│SQLite Cache │
│   (React)   │◀────│  (FastAPI)       │◀────│  (SQLModel) │
└─────────────┘      └──────────────────┘     └─────────────┘
                            │
                            ▼ (cache miss)
                     ┌──────────────┐
                     │  cpaiops     │
                     │  Check Point │
                     │     API      │
                     └──────────────┘
```

## Database Schema

### New SQLModel Tables

```python
class CachedDomain(SQLModel, table=True):
    __tablename__ = "cached_domains"
    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    name: str
    cached_at: datetime

class CachedPackage(SQLModel, table=True):
    __tablename__ = "cached_packages"
    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    domain_uid: str = Field(foreign_key="cached_domains.uid")
    name: str
    access_layer: str
    cached_at: datetime

class CachedSection(SQLModel, table=True):
    __tablename__ = "cached_sections"
    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    package_uid: str = Field(foreign_key="cached_packages.uid")
    domain_uid: str = Field(index=True)
    name: str
    rulebase_range: str  # JSON string "[min, max]"
    rule_count: int
    cached_at: datetime
```

## Backend Components

### Cache Service (`src/fa/cache_service.py`)

```python
class CacheService:
    async def get_status() -> dict  # Returns timestamps and empty flag
    async def refresh_all(username, password, mgmt_ip)  # Full refresh
    async def get_cached_domains() -> list[CachedDomain]
    async def get_cached_packages(domain_uid) -> list[CachedPackage]
    async def get_cached_sections(domain_uid, pkg_uid) -> list[CachedSection]
```

### New API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/cache/status` | GET | Return cache status with timestamps |
| `/api/v1/cache/refresh` | POST | Trigger background refresh from Check Point |

### Modified Routes Behavior

- `GET /api/v1/domains` - Return cached, refresh on empty
- `GET /api/v1/domains/{uid}/packages` - Return cached, refresh on empty
- `GET /api/v1/domains/{uid}/packages/{pkg_uid}/sections` - Return cached, refresh on empty

## Frontend Changes

### Domains.tsx Modifications

1. **Remove from Domains2.tsx:**
   - `PredictionsPanel` component and imports
   - `generatePredictions` utility
   - `topology` state and effects
   - Topology API calls
   - Drag-drop handlers for predictions

2. **Add to Domains.tsx:**
   - Cache status polling (every 30s)
   - "Refresh cache" button with timestamp display
   - Loading state for cache refresh
   - Error handling for refresh failures

### UI Elements

```
┌──────────────────────────────────────────┐
│  IP Input Panel                          │
├──────────────────────────────────────────┤
│  [Refresh Cache] Last: 2 min ago         │
├──────────────────────────────────────────┤
│  [Add Rule]                              │
├──────────────────────────────────────────┤
│  Rules Table                             │
│  ┌──────┬──────┬───────┬────┬────┬────┐  │
│  │Source│Dest  │Service│Dom │Pkg │... │  │
│  └──────┴──────┴───────┴────┴────┴────┘  │
├──────────────────────────────────────────┤
│  [Submit Rules]                          │
└──────────────────────────────────────────┘
```

## Error Handling

1. **Database initialization:** Catch errors, drop and recreate tables
2. **Cache refresh failures:** Log errors, preserve old cache, return error status
3. **Concurrent refreshes:** Use `asyncio.Lock` to prevent duplicate refreshes
4. **Empty cache:** Show user-friendly message with "Refresh" call-to-action

## Implementation Phases

1. **Backend - Database & Models:** Add SQLModel tables, init logic
2. **Backend - Cache Service:** Implement CRUD and refresh
3. **Backend - API Updates:** New cache routes, update existing routes
4. **Frontend - Domains.tsx:** Copy Domains2, remove predictions, add cache controls
5. **Testing:** Full integration test of cache flow

## Future Considerations

- Add TTL-based cache expiration
- Add per-package targeted refresh
- Consider adding topology caching if needed later
- Add cache metrics (hit rate, last refresh duration)
