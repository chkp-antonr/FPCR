# RITM Try & Verify Evidence Tracking

**Date:** 2026-04-23

**Status:** Implemented

## Overview

Fixed critical issues with the RITM Try & Verify workflow, particularly around evidence generation and session tracking.

## Problem Statement

1. **Hot Reload Bug**: Application failed to start with `KeyError: 'ritm_created_objects'` after uvicorn hot reload
2. **Stale Session UID**: Evidence generation failed because cached session UID didn't match current API session
3. **Incorrect Response Parsing**: `show-changes` API returns nested structure that wasn't being parsed correctly
4. **UnicodeDecodeError**: PDF bytes couldn't be serialized in JSON response
5. **Lost Workflow State**: Page reload lost "verified" state, disabling approval button
6. **Session Accumulation**: Multiple Try & Verify runs accumulated 10+ stale sessions
7. **No Session Tracking**: Evidence lacked session UID traceability

## Solution

### 1. Database Hot Reload Fix

Removed redundant `SQLModel.metadata.clear()` from `app.py` lifespan. The models already handle hot reload correctly.

### 2. Session UID Tracking

- Call `show-session` API after creating objects/rules to get current session UID
- Store in `RITM.try_verify_session_uid` and `RITMSession` table
- Use this UID for `show-changes` API calls

### 3. Response Parsing

Parse nested structure: `tasks[0].task-details[0].changes[0].operations`

### 4. PDF Serialization

Base64 encode PDF bytes before returning in JSON response.

### 5. Workflow State Restoration

On page load, check if `session_changes_evidence1` exists to restore `workflowStep='verified'`

### 6. Session Cleanup

Delete old sessions before adding new ones to prevent accumulation

### 7. Evidence Display

Add Session UID to evidence HTML and PDF for traceability

## Files Changed

- `src/fa/app.py`: Removed duplicate metadata clear
- `src/fa/models.py`: Added `try_verify_session_uid` column, changed PDF response type
- `src/fa/services/package_workflow.py`: Session UID tracking, response parsing
- `src/fa/services/ritm_workflow_service.py`: Session cleanup, PDF base64 encoding
- `src/fa/routes/ritm_flow.py`: Published session fallback logic
- `src/fa/cache_service.py`: Packages progress reset per domain
- `src/fa/templates/session_changes.html`: Added session UID display
- `src/fa/services/session_changes_pdf.py`: Added session UID to PDF
- `webui/src/pages/RitmEdit.tsx`: Workflow state restoration, regenerate evidence button

## Testing

Verified with:

- Hot reload scenarios
- Multiple Try & Verify attempts
- Page reload after successful workflow
- Evidence generation (HTML and PDF)
