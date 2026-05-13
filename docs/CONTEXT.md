# Project Context Map

This file serves as a directory for AI assistants to find relevant research, plans, and historical context that might be hidden in gitignored folders.

---

## 📅 Chronological Research & Features

### 2026-02-12: Project Initialization

* **Topic**: Initial project setup for Firewall Policy Change Request (FPCR) tool.
* **Tracked Results**: `docs/internal/features/260212-init/`
* **Raw Logs (Ignored)**: `docs/_AI_/260212-init/`
* **Summary**: Created basic FPCR tool structure using `cpaiops` library for Check Point management API interaction.

### 2026-02-12: CPObject Search Implementation

* **Topic**: Implemented search functionality for Check Point objects across domains.
* **Tracked Results**: `docs/internal/features/26012-search_cpobject/`
* **Raw Logs (Ignored)**: `docs/_AI_/26012-search_cpobject/`
* **Implementation**: `src/cpsearch.py` (find_cp_objects, DomainSearchResult, GroupNode)
* **Summary**: Added domain-aware object search with group membership traversal and Rich console output.

### 2026-02-12: CRUD Templates

* **Topic**: Implemented YAML-based CRUD template processing for Check Point objects.
* **Tracked Results**: `docs/internal/features/260212-ops/`
* **Implementation**: `src/cpcrud/` (apply_crud_templates)
* **Summary**: Added ability to process YAML templates for creating, updating, and deleting Check Point objects.

### 2026-02-19: WebUI Design

* **Topic**: Design for FastAPI + React WebUI with per-user RADIUS authentication.
* **Tracked Results**: `docs/internal/features/260219-webui/DESIGN.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260219-init_webui/`
* **Status**: Design approved, implementation pending.
* **Summary**: Designed monolithic FastAPI backend with session-based auth and React TypeScript frontend (Ant Design). Per-user Check Point credentials via RADIUS validation.

### 2026-02-20: Package Selection Flow

* **Topic**: Cascading selection flow for domains, policy packages, and sections with position selection.
* **Tracked Results**: `docs/internal/features/260220-package-selection/IMPLEMENTATION_SUMMARY.md`
* **Implementation Plan**: `docs/plans/260220-package-selection.md`
* **Status**: Complete (Phase 1).
* **Summary**: Extended WebUI with packages/sections API endpoints and rewritten Domains page featuring AutoComplete selectors, section list with rule ranges, and position selector (Top/Bottom/Custom). Foundation for Phase 2 rule insertion operations.

### 2026-02-20: WebUI Styling System

* **Topic**: CSS Modules-based styling system with security-themed color palette.
* **Design**: `docs/internal/features/260220-webui-styling/DESIGN.md`
* **Implementation Plan**: `docs/plans/260220-webui-styling.md`
* **Status**: Complete.
* **Summary**: Implemented CSS Modules architecture with global CSS variables for theming. Security-themed palette (red/teal/gray) with dark/light mode support via Ant Design ConfigProvider. Type-safe class name generation and component-scoped styles.

### 2026-03-06: Domains Rule Cards

* **Status**: Implemented
* **Design**: `docs/plans/260306-domains-rule-cards-design.md`
* **Plan**: `docs/plans/260306-domains-rule-cards-plan.md`
* **Implementation Summary**: `docs/internal/features/260306-domains-rule-cards/IMPLEMENTATION_SUMMARY.md`
* **Summary**: Card-based interface for creating firewall rules across multiple domains. IP pools panel with validation, horizontal card container, keyboard shortcuts. Key components: IpPoolsPanel (IP input panel), RuleCard (individual rule card), CardsContainer (cards wrapper), ipValidator (IP validation logic), and backend endpoint at src/fa/routes/domains.py.

### 2026-03-06: UI Layout Optimization

* **Status**: Complete
* **Documentation**: `docs/internal/features/260306-domains-rule-cards//README.md`
* **Summary**: Optimized `/domains` page UI for small data volumes. Key changes: IP Pools Panel horizontal layout (3 text areas in one row), cards full width with vertical stacking, submit confirmation modal, buttons on same row (Add | Submit), cards-only scrolling with fixed IP Pools panel. CSS fix: `min-height: 0` on nested flex containers for proper overflow behavior.

### 2026-03-07: Hostname Display in Predictions

* **Status**: Complete
* **Documentation**: `docs/internal/features/260307-hostname-predictions/feature-summary.md`
* **Summary**: Enhanced Predictions panel to display hostnames alongside IPs when a match is found in mock data. Format: `10.76.64.10 (USNY-CORP-WST-1) → AME_CORP US-NY-CORP`. Backend uses `ip_hostnames` dict for exact IP-to-hostname mapping via Python `ipaddress` module. Frontend displays hostname in parentheses with bolded domain names.

### 2026-03-15: Domains Cache Migration (Completed)

* **Topic**: Migrate Domains page to use RulesTable UX with real Check Point API data and SQLite caching.
* **Status**: Complete
* **Documentation**: `docs/internal/features/20260315-domains-cache-migration/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/20260315-domains-cache-migration/`
* **Summary**: Migrated Domains.tsx to RulesTable-based interface (same as Domains2.tsx) without predictions panel. Implemented SQLite caching with SQLModel tables (CachedDomain, CachedPackage, CachedSection) and CacheService singleton. Added cache refresh endpoint with manual trigger and status polling. Fixed race condition in cache refresh (fetch before clear). Added reload buttons and better error handling in UI.
* **Key Files**:
  * `src/fa/models.py` - Cache tables
  * `src/fa/cache_service.py` - Cache management (270 lines)
  * `src/fa/routes/domains.py` - Cache endpoints
  * `src/fa/routes/packages.py` - Cache-first approach
  * `webui/src/pages/Domains.tsx` - UX migration
  * `webui/src/components/RulesTable.tsx` - Reload buttons

### 2026-04-01: Cache Refresh Stability and Single-DB Consolidation

* **Topic**: Stabilization of cache refresh, relogin behavior, and SQLite locking after moving to single database mode.
* **Tracked Results**: `docs/internal/features/260401-cache-refresh-stability/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260401-cache-refresh-stability/`
* **Status**: In progress (major fixes implemented; runtime relogin verification pending final confirmation)
* **Summary**: Added publish-session based domain skip with explicit `Caching` vs `Skipping` logs, schema mismatch CRITICAL guidance, read-consistency waits on domains/packages, startup schema recreation checks, frontend progress UX improvements, and lock-contention mitigations (shorter DB write windows plus async task error callbacks).

### 2026-04-08: RITM Approval Workflow Module

* **Topic**: Complete RITM (Requested Item) approval workflow implementation.
* **Status**: Completed
* **Tracked Results**: `docs/internal/features/260408-ritm-implementation/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260408-ritm/`
* **Design Spec**: `docs/superpowers/specs/2026-04-08-ritm-design.md`
* **Implementation Plan**: `docs/superpowers/plans/2026-04-08-ritm-implementation.md`
* **Summary**: Implemented full RITM approval workflow with separation of duties, input pool persistence, and 14 passing integration tests. Key components:
  * Database: RITM and Policy SQLModel tables with natural keys
  * API: 9 endpoints for CRUD, approval locking, and publishing
  * Frontend: Dashboard, RitmEdit (with auto-save), RitmApprove pages
  * Input pools saved per RITM (source_ips, dest_ips, services as JSON)
  * Approval locking with 30-minute timeout
  * 14 comprehensive integration tests

### 2026-04-11: CPCRUD Enhancement

* **Topic**: Enhance CPCRUD functionality with NAT settings and firewall rule management.
* **Status**: ✅ Complete
* **Tracked Results**:
  * `docs/internal/features/260411-cpcrud-enhancement/README.md` (Design Spec)
  * `docs/internal/features/260411-cpcrud-enhancement/IMPLEMENTATION_SUMMARY.md` (Implementation Summary)
* **Raw Logs (Ignored)**: `docs/_AI_/260411-CPCRUD/`
* **Reference**: `W:\MMP\src\plugins\actions\cpcrud\`
* **Implementation Plan**: `docs/superpowers/plans/2026-04-11-cpcrud-enhancement.md`
* **Summary**: Implemented full CPCRUD enhancement with NAT settings support for network objects (host, network, address-range) and firewall rule management (access-rule, nat-rule, threat-prevention-rule, https-rule). Split into separate CheckPointObjectManager and CheckPointRuleManager classes following reference implementation. Features include rule positioning (absolute, top/bottom, section-relative), JSON schema validation, and example templates. 16 tests passing, type checking clean.
* **Key Components**:
  * `src/cpcrud/position_helper.py` - Rule position validation
  * `src/cpcrud/object_manager.py` - Network object CRUD with NAT transformation
  * `src/cpcrud/rule_manager.py` - Firewall rule CRUD with positioning
  * `src/cpcrud/business_logic.py` - Template processing orchestration
  * `ops/templates/example-with-nat.yaml` - NAT settings examples
  * `ops/templates/example-with-rules.yaml` - Rule creation examples

### 2026-04-12: FPCR Create & Verify Flow

* **Topic**: Complete implementation of Create & Verify workflow including object matching, policy verification, and evidence generation.
* **Status**: ✅ Implementation Complete
* **Tracked Results**:
  * `docs/internal/features/260412-fpcr-create-verify-flow.md` (Implementation Summary)
  * `docs/internal/features/260412-fpcr-flow-design.md` (Design Spec)
  * `docs/internal/features/260412-fpcr-flow-diagrams.md` (Mermaid Flow Diagrams)
  * `docs/internal/features/260412-fpcr-technical-overview.md` (Technical Explanation)
* **Raw Logs (Ignored)**: `docs/_AI_/260412-fpcr-create-verify-flow/`
* **Summary**: Fully implemented FPCR Create & Verify flow with 18 passing tests using Subagent-Driven Development. Includes object matching with naming conventions, policy verification via CPAIOPS, evidence generation (HTML/YAML/PDF ready), and comprehensive error handling. Components: InitialsLoader, ObjectMatcher, PolicyVerifier, EvidenceGenerator services, 4 API endpoints, and 3 database tables.
* **Key Implementation Details**:
  * **Services**: InitialsLoader (CSV initials mapping), ObjectMatcher (cpsearch + scoring), PolicyVerifier (CPAIOPS integration), EvidenceGenerator (HTML/YAML/PDF)
  * **API Endpoints**: POST /ritm/{id}/match-objects, POST /ritm/{id}/verify-policy, POST /ritm/{id}/generate-evidence, GET /ritm/{id}/export-errors
  * **Database**: ritm_created_objects, ritm_created_rules, ritm_verification tables
  * **Dependencies**: weasyprint >=60, jinja2 >=3.1.0, jsonschema >=4.0.0
  * **Configuration**: Added 8 new .env settings for initials path, templates, timeouts, and behavior flags
* **Methodology**: Subagent-Driven Development with two-stage reviews (spec compliance, then code quality) for each of 12 tasks

### 2026-04-12: RITM Multi-Step Workflow (Plan → Apply → Verify)

* **Topic**: Multi-step execution pipeline for RITM changes. Architecture enforcement (no frontend logic). Bug fixes for object lookup and DB querying. Session changes capture via `show-changes`.
* **Status**: ✅ Complete
* **Tracked Results**: `docs/internal/features/260412-ritm-workflow-multistep/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260412-flow/`
* **Summary**: Extended RITM workflow to Plan → Apply → Verify stepper. Moved all YAML planning to backend. Added `/apply` and `/verify` endpoints. Integrated `show-changes` CP API call after apply with collapsed JSON panel in UI. Fixed two bugs: `PolicyItem` vs `Policy` SQLAlchemy crash; `filter`-based object lookup (was using wrong `ip-address` key). 16 backend tests passing, frontend build clean.
* **Key Files**:
  * `src/fa/routes/ritm_flow.py` - New `plan_yaml`, `apply_ritm`, `verify_ritm` endpoints; `_build_plan_yaml_from_policies()`; `_as_list()`; `show-changes`
  * `src/fa/models.py` - `PlanYamlResponse`, `ApplyResponse`, `VerifyResponse`
  * `src/fa/services/object_matcher.py` - Corrected API query key; exact-IP post-filter
  * `webui/src/pages/RitmEdit.tsx` - Steps component; three-step handlers; Collapse panel
  * `webui/src/api/endpoints.ts` - `generatePlanYaml`, `applyRitm`, `verifyRitm`
* **Architecture Principle**: Backend owns all logic; frontend collects inputs, shows outputs only

### 2026-04-22: Session Changes Visualization

* **Topic**: PDF evidence generation and HTML visualization for RITM session changes.
* **Status**: ✅ Complete
* **Tracked Results**: `docs/internal/features/260422-session-changes-visualization.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260421-show_changes/`
* **Related**:
  * Design: `docs/superpowers/specs/2026-04-21-session-changes-visualization-design.md`
  * Implementation: `docs/superpowers/plans/2026-04-21-session-changes-visualization-implementation.md`
* **Summary**: Generate PDF evidence and HTML visualization of RITM session changes showing applied rules and objects. Uses ReportLab (Windows-compatible) for PDF generation in landscape orientation. Includes Domain → Section → Rules hierarchy, Objects Summary by type (added/modified/deleted), and both visual HTML and raw JSON display in WebUI. Download buttons on both RitmEdit and RitmApprove pages.

### 2026-04-22: Session Changes Visualization Follow-Up (Data Correctness + UX Logging)

* **Topic**: Correct section/rule metadata, restore full rule fields from API details, align HTML/PDF layout behavior, and improve in-UI workflow progress visibility.
* **Tracked Results**: `docs/internal/features/260422-session-changes-followup/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260421-show_changes/`
* **Status**: Completed
* **Summary**: Added enrichment pipeline using `show-access-rule` and `show-access-rulebase` to resolve section names and rule numbers, backfilled Source/Destination/Service/Action/Track/Comments from real API rule details, kept `show-changes` at `details-level=full`, normalized stale evidence payloads at read-time, and added workflow activity logs in `RitmEdit`. Also standardized local workflow command path to `.agents/workflows/archive-task.md` and added a Copilot prompt command at `.github/prompts/archive-task.prompt.md`.

### 2026-04-23: RITM Evidence Tracking Fixes

* **Topic**: Fixed critical issues with RITM Try & Verify evidence generation, session tracking, and workflow state management.
* **Status**: ✅ Complete
* **Tracked Results**: `docs/internal/features/240423-ritm-evidence-tracking/`
* **Summary**: Fixed hot reload bug, session UID tracking, show-changes parsing, PDF serialization, workflow state restoration, session cleanup, evidence display, packages progress reset, and regenerate evidence functionality.
* **Key Fixes**:
  * Hot reload: Removed duplicate `SQLModel.metadata.clear()` from app.py
  * Session tracking: Added `try_verify_session_uid` column, call `show-session` API after changes
  * Response parsing: Correctly parse nested `tasks[0].task-details[0].changes[0].operations`
  * PDF serialization: Base64 encode PDF bytes in JSON response
  * Workflow state: Restore `workflowStep='verified'` on page load if evidence exists
  * Session cleanup: Delete old sessions before adding new ones
  * Evidence display: Show Session UID in HTML and PDF
  * Packages progress: Reset counter for each new domain
  * Regenerate evidence: Button to recreate evidence after page reload

### 2026-04-24: RITM Section Name Resolution

* **Topic**: Fixed evidence generation showing "Section: Rules" fallback instead of actual access layer names.
* **Status**: ✅ Implementation Complete (Testing pending)
* **Tracked Results**: `docs/internal/features/260424-ritm-section-name-resolution/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260424-ritm-section-resolution/debug-notes.md`
* **Summary**: Modified `ritm_flow.py` to fetch access layers from `show-access-layers` API command and build combined UID-to-name mapping. Updated `SessionChangesPDFGenerator` to accept and use the mapping. Switched to `arlogi` for consistent logging. Section names now display correctly (e.g., "pyTestPolicy Network" instead of "Section: Rules").
* **Root Cause**: Access layers and sections are different concepts in Check Point. The `layer` field contains a layer UID, but `cached_sections` only stores sections (within layers).
* **Files Modified**:
  * `src/fa/routes/ritm_flow.py` - Added layer fetching logic
  * `src/fa/services/session_changes_pdf.py` - Updated to accept and use UID mapping
  * `src/fa/app.py` - Added arlogi `setup_logging()` initialization

### 2026-05-13: RITM Workflow Guide (Current Procedure)

* **Topic**: Comprehensive, up-to-date reference for the RITM lifecycle as currently implemented.
* **Status**: ✅ Complete
* **Tracked Results**: `docs/internal/features/260513-ritm-workflow-guide/RITM_WORKFLOW.md`
* **Raw Logs (Ignored)**: `docs/_AI_/2605/260513-RITM_flow_doc/`
* **Summary**: Documents current RITM workflow including state machine (WORK_IN_PROGRESS → READY_FOR_APPROVAL → APPROVED → COMPLETED), editor/approver separation-of-duties guardrails, Try & Verify per-package attempt states, Mermaid sequence diagram covering rejection and correction cycles, and evidence session structure (no consolidation, session grouping only). Supersedes the older `260423-ritm-evidence-tracking/ritm-flow.md`.

### 2026-05-08: RITM Correction Attempt — Rule Dedup & Diff Display

* **Topic**: Rule deduplication on re-submission, blank evidence fix, source/dest diff display.
* **Status**: ✅ Complete
* **Tracked Results**: `docs/internal/features/260508-ritm-correction-evidence/README.md`
* **Small Fixes**: `docs/internal/fixes/260508-ritm-correction-fixes.md`
* **Raw Logs (Ignored)**: `docs/_AI_/2605/260508-ritm-correction-evidence/`
* **Branch**: `dev/ritm-v3`
* **Summary**: Four improvements to the correction attempt workflow. (1) Rule dedup: `create_objects_and_rules()` now queries `ritm_created_rules` and calls `set-access-rule` to reuse existing UIDs instead of duplicating rules. `CreateResult` tracks `updated_rule_uids` separately so rollback only deletes truly new rules. (2) Evidence panel fix: unwrap `{new-object, old-object}` wrappers from `modified-objects` in both React `SessionChangesDisplay` and PDF generator. (3) Source/dest diff: `annotateRule()` helper compares old vs new UID sets, tagging items `added/removed/same`; `renderRefList` renders colored JSX; PDF `_render_ref_items` produces ReportLab markup with green/red diff. (4) Comments and Rule Name columns in `RulesTable` made editable.

### 2026-04-24: Repository History Sanitization

* **Topic**: Repository cleanup after accidental secret file commit in historical revisions.
* **Status**: ✅ Completed (except protected/default-branch restrictions on external remotes)
* **Tracked Results**: `docs/internal/features/260424-repo-history-sanitization/README.md`
* **Raw Logs (Ignored)**: `docs/_AI_/260424-repo-history-sanitization/`
* **Summary**: Squashed history to a single commit (`73bcee6`) and force-updated local/cpar/gitea master branches to the clean tip. Removed feature branches from cpar and gitea where allowed. Azure cleanup was deferred due to branch protection; gitea `dev` deletion remains blocked until default branch is switched from `dev` to `master`.

---

## 🚀 RITM Workflow

* **Design**: [Try & Verify Workflow Design](internal/features/260422-ritm-try-verify-workflow/design.md)
* **Implementation**: [Try & Verify Implementation Plan](../superpowers/plans/2026-04-22-ritm-try-verify-workflow.md)
* **Raw Logs**: `docs/_AI_/260422-ritm-try-verify-workflow/`
* **Summary**: End-to-end RITM processing workflow with Try & Verify functionality, evidence recreation, and result verification.

---

## 🛠️ AI Working Model

For instructions on how to organize further artifacts, see `CLAUDE.md`.

---

## 📊 Knowledge Graph

### Quick Access

The project has a **knowledge graph** built with graphify that captures relationships between code, documentation, and features.

**Generated Files:**

* `graphify-out/graph.html` - Interactive visualization (open in browser)
* `graphify-out/wiki/index.md` - Community documentation
* `graphify-out/GRAPH_REPORT.md` - Audit report with insights

* `graphify-out/community_labels.json` - Community name mappings

### Key Statistics

*
* **Nodes**: 2,303 (classes, functions, docs, concepts)
* **Edges**: 6,189 (imports, calls, references, relationships)

* **Communities**: 76 (auto-clustered groups)

### Top Communities (by size)

1. **Rulebase Processing** (262 nodes) - Rulebase extractors, parsers, refresh
2. **Client API Layer** (180+ nodes) - API clients, adapters
3. **Caching Layer** (150+ nodes) - Cache repositories, database
4. **Domain Management** (100+ nodes) - Domain services, models
5. **WebUI Components** (80+ nodes) - React components, pages

### Key Hub Nodes (most connected)

1. **Domain** - Central domain model (131 connections)
2. **CacheOrchestrationService** - Cache orchestration (127 connections)
3. **CPAIOPSClient** - Main API client (125 connections)
4. **CPObject** - Check Point object model (121 connections)

### How to Use the Graph

**When planning features:**

* Check `graphify-out/wiki/` for community context
* Query: `/graphify query "how does CPCRUD work?"`

* Path: `/graphify path "CPCRUD" "Domain"`

**When analyzing code:**

* Check `GRAPH_REPORT.md` for "Surprising Connections"
* Look at `graphify-out/obsidian/notes/` for node details

* Use `graph.html` for visual exploration

**After code changes:**

* Rebuild: `/graphify-labeled`

* Or quick relabel: `python graphify-relabel.py`

### Integration with AI Assistants

**Claude Code:**

* Native integration configured via `graphify claude install`

* AI automatically checks graph before planning

**GitHub Copilot:**

* See `.copilot-instructions.md` for context sources

* Graph is exported as markdown for Copilot to read

**MCP Server:**

* Configure with `setup-mcp.bat` for Claude Desktop

* See `docs/MCP_CONFIG.md` for details

### Documentation

* **Integration Guide**: `docs/GRAPHIFY_INTEGRATION.md`
* **MCP Configuration**: `docs/MCP_CONFIG.md`

* **Quick Reference**: Run `/graphify-labeled --help`

---
