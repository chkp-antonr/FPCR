# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- **RITM State Machine & Pre-Verify Step** (`dev/ritm-v3`)
  - Explicit `RITMStatus` transition table replacing ad-hoc `if/elif` chains in `update_ritm()`
  - New `POST /ritm/{number}/pre-verify` endpoint — standalone verify of all affected packages
    before the apply step, surfacing errors early without consuming a correction attempt
  - Removed `force_continue` flag — `try-verify` is now All-or-No: all packages must succeed or
    none are committed

- **RITM Correction Evidence — Rule Deduplication & Source/Dest Diff**
  - Re-submission no longer duplicates rules: `create_objects_and_rules()` queries
    `ritm_created_rules` and reuses existing UIDs via `set-access-rule` (update) with
    `add-access-rule` as fallback
  - `CreateResult` tracks `updated_rule_uids` separately from `created_rule_uids` so rollback
    only deletes truly new rules; `disable_rules` covers both lists
  - Evidence panel for correction attempts now correctly unwraps `{new-object, old-object}`
    wrappers from `modified-objects` in both React UI and PDF generator
  - Source/destination diff display: added/removed hosts highlighted in green/red with `+`/`−`
    prefix and strikethrough in both the in-page evidence table and generated PDF

- **Copilot Archive Command Prompt**
  - Added workspace prompt command: `.github/prompts/archive-task.prompt.md`
  - Canonical workflow path standardized to `.agents/workflows/archive-task.md`

- **Session Changes Visualization** - PDF evidence generation and HTML visualization for RITM session changes
  - PDF generation using ReportLab (Windows-compatible, landscape orientation)
  - HTML visualization showing Domain → Section → Rules hierarchy
  - Objects Summary grouped by type and action (added/modified/deleted)
  - Download buttons on RitmEdit and RitmApprove pages
  - Both visual HTML and raw JSON display in WebUI
  - API endpoint: GET /ritm/{ritm_number}/session-pdf?evidence=1
  - Database columns: session_changes_evidence1, session_changes_evidence2

- **FPCR Create & Verify Flow** - Complete workflow implementation with object matching, policy verification, and evidence generation
  - Object matching with naming conventions via cpsearch integration
  - Policy verification via CPAIOPS with structured error reporting
  - Evidence generation (Smart Console-style HTML cards, CPCRUD-compatible YAML export)
  - 4 new API endpoints: match-objects, verify-policy, generate-evidence, export-errors
  - 3 new database tables for tracking created objects, rules, and verification results
  - 18 passing tests (services, routes, integration)
  - Services: InitialsLoader, ObjectMatcher, PolicyVerifier, EvidenceGenerator
  - Configuration: 8 new .env settings for initials path, templates, and behavior flags

- **CPCRUD Enhancement** - NAT settings and firewall rule management for template-based object configuration
  - NAT settings support for hosts, networks, and address ranges (static/hide methods)
  - Firewall rule CRUD operations: access-rule, nat-rule, threat-prevention-rule, https-rule
  - Rule positioning system (absolute, layer-level, section-relative)
  - JSON schema validation for templates
  - Separate CheckPointObjectManager and CheckPointRuleManager classes
  - Example templates for NAT settings and firewall rules
  - 16 passing unit tests

- **RITM Approval Workflow Module** - Complete approval/audit trail for firewall changes
  - RITM and Policy database tables with natural keys
  - Dashboard with RITM lists (My RITMs, For Approval, Approved)
  - RITM Edit page with auto-save and input pool persistence
  - RITM Approve page with approve/return functionality and locking
  - Approval locking mechanism (30-minute timeout)
  - 14 passing integration tests

### Changed

- Migrated from localStorage to AuthContext for username management
- Fixed timezone-aware datetime comparison bug in approval lock endpoint
- Session changes visualization now groups rules by package and section in both HTML and PDF renderers
- Added section-row-in-body table layout (column headers remain the first row)
- Added workflow activity logging card in RITM edit flow for user-visible plan/apply/verify/reset progress
- Added backend access-rule enrichment (`show-access-rule` + `show-access-rulebase`) to improve section/rule metadata and full rule field visibility
- Repository history sanitized to single-commit lineage (`73bcee6`) for local branch state, `cpar/master`, and `gitea/master`
- Removed remote branch `feature/ritm` from both `cpar` and `gitea`
- Deferred Azure history rewrite because branch policy blocks force pushes to `master`

### Fixed

- "You can only view your own RITMs" error - now uses AuthContext user
- Domain/package/section dropdowns now load properly in RITM edit
- Input pools (Source/Dest IPs, Services) now persisted per RITM
- Favicon routing handled correctly by SPA fallback route
- **Hot reload startup failure** - Fixed `KeyError: 'ritm_created_objects'` by removing duplicate `SQLModel.metadata.clear()` from app.py lifespan
- **Evidence generation failures** - Fixed session UID tracking by calling `show-session` API after creating changes and storing `try_verify_session_uid` in database
- **Empty evidence in show-changes** - Fixed response parsing to correctly extract operations from nested `tasks[0].task-details[0].changes[0].operations` structure
- **PDF serialization error** - Fixed UnicodeDecodeError by base64 encoding PDF bytes in JSON response
- **Lost workflow state after reload** - Fixed "Submit for Approval" button being disabled by restoring `workflowStep='verified'` when evidence exists
- **Session accumulation** - Fixed duplicate sessions (10+ entries) by deleting old sessions before adding new ones
- **Packages progress bar** - Fixed progress counter not resetting when moving to next domain
- **Regenerate evidence functionality** - Added ability to regenerate evidence after page reload with fallback to original evidence if session was published
