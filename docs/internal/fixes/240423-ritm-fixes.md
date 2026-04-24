# Small Fixes - RITM Evidence Tracking (2026-04-23)

## Hot Reload Fix
**File**: [src/fa/app.py](src/fa/app.py)
- Removed redundant `SQLModel.metadata.clear()` from lifespan (line 76-77)
- Models already handle hot reload correctly via `_known_tables` check

## Session UID Display  
**Files**: [src/fa/templates/session_changes.html](src/fa/templates/session_changes.html), [src/fa/services/session_changes_pdf.py](src/fa/services/session_changes_pdf.py)
- Added Session UID display in evidence HTML and PDF
- Removed SID display (security)

## Packages Progress Reset
**File**: [src/fa/cache_service.py](src/fa/cache_service.py)
- Added `self._packages_processed = 0` when starting new domain (line 292)

## Evidence JSON Removal
**File**: [src/fa/templates/session_changes.html](src/fa/templates/session_changes.html)
- Removed raw JSON section at bottom of evidence (was duplication)

## Unused CSS Cleanup
**File**: [src/fa/templates/session_changes.html](src/fa/templates/session_changes.html)
- Removed `.json-section` and `.json-section pre` styles (no longer needed)
