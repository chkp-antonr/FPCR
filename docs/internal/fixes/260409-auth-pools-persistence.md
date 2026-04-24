# Session Fixes - 2026-04-09

## AuthContext Migration

### Issue

Pages were using `localStorage.getItem('username')` which was never set, causing "You can only view your own RITMs" errors.

### Fix

- Updated Dashboard.tsx, RitmEdit.tsx, and RitmApprove.tsx to use `useAuth()` context
- Removed all `localStorage.getItem('username')` references

## Domain/Package/Section Loading

### Issue

Domain dropdown was populated but packages/sections failed to load in RITM edit page.

### Fix

- Added `domains` state to RitmEdit component
- Implemented `onFetchPackages` callback to load packages on demand
- Implemented `onFetchSections` callback to load sections on demand
- Added proper error handling and debug logging
- Extended `DomainInfo` type to include `uid` field

## Input Pool Persistence

### Issue

Input pools (Source IPs, Dest IPs, Services) were lost when returning to edit a RITM.

### Database

Added columns to RITM table:

- `source_ips TEXT` (JSON array)
- `dest_ips TEXT` (JSON array)
- `services TEXT` (JSON array)

### API

- Added `POST /api/v1/ritm/{ritm_number}/pools` endpoint

### Frontend

- Auto-save pools when changed (1-second debounce)
- Load pools when RITM loads
- Save pools via `ritmApi.savePools()`

## Timezone Fix

### Issue

`TypeError: can't subtract offset-naive and offset-aware datetimes` in lock endpoint

### Fix

- Convert database naive datetimes to UTC-aware before comparison
- Added `tzinfo=UTC` to database values before age calculation

## Type Updates

### DomainInfo Type

- Added `uid` field to `DomainInfo` interface in types/index.ts
- Updated all usages in Domains.tsx, Domains2.tsx, and RulesTable.tsx

### RITMItem Type

- Added `source_ips`, `dest_ips`, `services` fields (string arrays)
- Updated API response mapping in ritm.py

## Imports

### BaseModel Import

- Added missing `BaseModel` import to ritm.py for `RITMPoolsRequest`

### PackageInfo Export

- Exported `SectionInfo`, `PackageInfo`, `DomainInfo` from types/index.ts
- Removed duplicate definitions from RulesTable.tsx
