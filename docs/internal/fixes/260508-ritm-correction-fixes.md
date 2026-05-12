# Small Fixes — 2026-05-08 RITM Correction Attempt

## RulesTable: Comments and Rule Name Made Editable

**File:** `webui/src/components/RulesTable.tsx`

The Comments and Rule Name table columns were rendering as static text. Changed both to Ant Design
`Input` components wired to `updateRule`. They are disabled when the table is in read-only mode
(e.g. during approval review).

## `col()` Wrapper for SQLModel `order_by`

**File:** `src/fa/services/package_workflow.py`

`.order_by(RITMCreatedRule.id)` caused a pyright/mypy error because the PK field is typed as
`int | None` in SQLModel. Wrapped with `col()` from `sqlmodel`: `.order_by(col(RITMCreatedRule.id))`.

## `html` Import for PDF Markup Escaping

**File:** `src/fa/services/session_changes_pdf.py`

Added `import html` at module level. Object names used in ReportLab XML markup are now passed
through `html.escape()` inside `_build_ref_items` to prevent markup injection from object names
containing `&`, `<`, or `>`.
