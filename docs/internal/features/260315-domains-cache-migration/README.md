# Domains Page Cache Migration

**Date:** 2025-03-15
**Status:** Completed

## Goal

Migrate the Domains page to use the same UX as Domains2.tsx (RulesTable-based interface) while replacing mock data with real data from the Check Point API via SQLite caching.

## Overview

The Domains page was updated to use the RulesTable component from Domains2.tsx, but with a key difference: instead of using mock data, it now fetches real data from the Check Point API and caches it in SQLite. This provides a better user experience with actual firewall policy data while maintaining good performance through caching.

## Implementation Details

### Architecture

**Database-First Caching Pattern:**

- UI reads from SQLite cache (fast)
- Cache refresh is triggered manually or automatically when empty
- Check Point API is only called during refresh
- Global shared cache across all users (no per-user cache isolation)

**Cache Lifecycle:**

1. User opens Domains page → UI checks cache
2. If cache empty → Auto-refresh or show "Refresh to load" message
3. User clicks "Refresh Cache" button → Fetches from API and populates cache
4. Subsequent page loads read from cache (fast)
5. TTL/Refresh currently manual (future: auto-refresh based on age)

### Components

#### Backend Models (`src/fa/models.py`)

Added SQLModel cache tables:

```python
class CachedDomain(SQLModel, table=True):
    """Cached Check Point domain."""
    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    name: str
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CachedPackage(SQLModel, table=True):
    """Cached policy package for a domain."""
    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    domain_uid: str = Field(foreign_key="cached_domain.uid")
    name: str
    access_layer: str
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CachedSection(SQLModel, table=True):
    """Cached access section for a package."""
    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str
    package_uid: str
    domain_uid: str
    name: str
    rulebase_range: str  # JSON: [min, max]
    rule_count: int
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

#### Cache Service (`src/fa/cache_service.py`)

Singleton service for managing cache operations:

- `get_status()` - Returns cache timestamps and empty/refreshing flags
- `refresh_all()` - Fetches all domains, packages, sections from API
- `get_cached_domains()` - Returns all cached domains
- `get_cached_packages(domain_uid)` - Returns packages for a domain
- `get_cached_sections(domain_uid, pkg_uid)` - Returns sections for a package

**Key Design Decision:** To prevent race conditions where UI sees empty cache during refresh:

1. Fetch all data from API first
2. Clear old cache
3. Insert fresh data
4. Old data remains available until refresh completes

#### API Routes

**Cache Endpoints (`src/fa/routes/domains.py`):**

- `GET /api/v1/cache/status` - Cache status (timestamps, empty flag, refreshing flag)
- `POST /api/v1/cache/refresh` - Trigger cache refresh (waits for completion)

**Package/Section Endpoints (`src/fa/routes/packages.py`):**

- `GET /api/v1/domains/{domain_uid}/packages` - Returns cached packages, refreshes if empty
- `GET /api/v1/domains/{domain_uid}/packages/{pkg_uid}/sections` - Returns cached sections, refreshes if empty

**503 Handling:** If cache is empty and refresh is in progress, returns 503 Service Unavailable with message "Cache is being refreshed. Please try again in a moment."

#### Frontend Changes

**`webui/src/pages/Domains.tsx`:**

- Removed PredictionsPanel (not needed for cache-based implementation)
- Added cache state polling (every 30s)
- Added "Refresh Cache" button with loading message
- Added 503 error handling with user-friendly message

**`webui/src/components/RulesTable.tsx`:**

- Added "Reload" buttons (↻) next to Package and Section dropdowns
- Added "Click to load" links when packages/sections are empty
- Better empty state messages

### Data Flow

```
User opens Domains page
    ↓
Poll cache status
    ↓
If cache empty → Show warning + "Refresh to load" button
    ↓
User clicks "Refresh Cache"
    ↓
POST /api/v1/cache/refresh
    ↓
CacheService.refresh_all()
    ↓
Fetch domains from Check Point API
    ↓
For each domain:
    - Fetch packages
    - For each package:
        - Fetch access layers
        - Fetch sections with rule ranges
    ↓
Store all in SQLite
    ↓
UI polls status → Sees cache populated
    ↓
User can now select domain → packages → sections
```

## Files Modified

### Backend

- `src/fa/models.py` - Added cache table models
- `src/fa/cache_service.py` - New file (270 lines)
- `src/fa/app.py` - Added database initialization with auto-recreate
- `src/fa/db.py` - Database engine setup
- `src/fa/routes/domains.py` - Added cache endpoints
- `src/fa/routes/packages.py` - Modified to use cache, added 503 handling
- `src/fa/__init__.py` - Fixed absolute to relative imports
- `src/fa/mock_source.py` - Fixed absolute to relative imports, removed dict.keys()
- `src/fa/tests/test_mock_source.py` - Fixed absolute to relative import
- `src/cpsearch.py` - Fixed `class SearchType(str, Enum)` to `class SearchType(StrEnum)`

### Frontend

- `webui/src/pages/Domains.tsx` - Complete UX migration
- `webui/src/components/RulesTable.tsx` - Added reload buttons
- `webui/src/api/endpoints.ts` - No changes (already had cacheApi)
- `webui/src/types/index.ts` - Already had CacheStatusResponse

### Tooling

- `check.ps1` - Fixed PowerShell syntax (`&&` → `;`)
- Added `.ruff.toml` configuration

## Technical Decisions

### 1. Global Cache vs Per-User Cache

**Decision:** Global shared cache across all users

**Rationale:**

- Simpler implementation (no user isolation needed)
- Check Point data is shared across all users anyway
- Reduces API calls (one refresh benefits all users)
- Future: Can add TTL-based auto-refresh

### 2. Manual Refresh vs Auto-Refresh

**Decision:** Manual refresh with "Refresh Cache" button

**Rationale:**

- User has control over when to refresh
- Avoids unnecessary API load
- Clear indication of cache age via timestamps
- Future: Add auto-refresh based on cache age

### 3. Cache Clearing Strategy

**Decision:** Fetch new data first, then clear and replace cache

**Rationale:**

- Prevents race condition where UI sees empty cache during refresh
- Old data remains available until refresh completes
- Better user experience (no 503 errors during normal operation)

### 4. Lock-Based Refresh Prevention

**Decision:** Use `asyncio.Lock` to prevent concurrent refreshes

**Rationale:**

- Prevents multiple simultaneous refreshes
- Second caller gets 503 if refresh in progress
- Simple and effective

## Testing Notes

**Manual Testing Required:** Requires connection to Check Point management server with `cpaiops` library.

**Test Checklist:**

- [ ] Cache refresh completes successfully
- [ ] Domains load correctly after refresh
- [ ] Packages load for each domain
- [ ] Sections load for each package with rule ranges
- [ ] "Reload" buttons work correctly
- [ ] 503 error appears when trying to fetch during refresh
- [ ] Cache status polling works (30s interval)
- [ ] Multiple users see same cached data

**Known Limitations:**

- Mypy/Pyright have type errors with SQLAlchemy 2.0 (known type stub limitations)
- Some files still missing return type annotations (pre-existing)

## Future Improvements

1. **Auto-Refresh:** Add TTL-based auto-refresh (e.g., refresh every 15 minutes)
2. **Incremental Refresh:** Only refresh changed domains/packages
3. **WebSocket Updates:** Push cache updates to connected clients
4. **Cache Invalidation:** Invalidate cache when rules are created/modified
5. **Per-Domain Caching:** Allow selective refresh per domain
6. **Progress Indication:** Show refresh progress (e.g., "3/5 domains loaded")

## Related Files

**Raw session logs:** `docs/_AI_/20260315-domains-cache-migration/`
**Design discussion:** See session transcripts for detailed discussion of UX decisions

## References

- [`cpsearch.py`](../../cpsearch.py) - Check Point object search implementation
- [`Domains2.tsx`](../../webui/src/pages/Domains2.tsx) - Reference UX implementation
- [`cpaiops`](../../cpaiops) - Internal Check Point API library
