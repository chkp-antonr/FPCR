# RITM Correction Attempt Evidence — Rule Deduplication & Diff Display

**Date:** 2026-05-08

**Branch:** dev/ritm-v3

**Status:** ✅ Complete

---

## Overview

Four related improvements to the RITM correction attempt workflow: preventing rule duplication on
re-submission, fixing blank evidence panels, and displaying source/destination diffs so reviewers can
see exactly what changed between the original and corrected attempt.

---

## Problems Solved

### 1. Rule Duplication on Correction Attempts

When a RITM was rejected and re-submitted, `create_objects_and_rules()` unconditionally called
`add-access-rule`, creating duplicate rules. The `ritm_created_rules` table tracked UIDs from the
first attempt but they were never consulted on subsequent attempts.

### 2. Evidence Panel Blank After Correction

The Check Point `show-changes` API returns modified objects in `{new-object, old-object}` wrapper
format. The code was treating wrappers as flat objects, causing:

- Rules missing from the evidence rules table
- "Modified: other: undefined" in the Objects Summary

### 3. Source/Destination Diff Not Displayed

Modified rules showed only their final state. Reviewers could not tell which hosts were added to or
removed from Source/Destination.

---

## Implementation

### Rule Deduplication (`src/fa/services/package_workflow.py`)

- Added `_find_existing_rule_uids()` async method: queries `ritm_created_rules` ordered by `id` for
  the current RITM/domain/package combination.
- `create_objects_and_rules()` loads existing UIDs as a queue; pops one per rule slot.
  - If a UID exists → calls `set-access-rule` (update). Falls back to `add-access-rule` on failure.
  - If no UID → calls `add-access-rule` (create).
- `CreateResult` gained `updated_rule_uids: list[str]` to separate pre-existing rules (no rollback)
  from newly created ones (rollback-eligible).
- `ritm_workflow_service.py`: `disable_rules` now receives `created_rule_uids + updated_rule_uids`.

### Modified-Objects Unwrap (`src/fa/services/session_changes_pdf.py` + `RitmEdit.tsx`)

Both the PDF generator and the React `SessionChangesDisplay` component were updated to unwrap
`{new-object, old-object}` entries from `modified-objects` before processing. Non-rule objects
continue to use `process_objects()`; access-rule objects are handled inline.

### Source/Destination Diff Display

**React (`webui/src/pages/RitmEdit.tsx` — `SessionChangesDisplay`):**

- `annotateRule(newObj, oldObj)` helper compares UID sets of old vs new source/destination arrays,
  tagging each ref with `_change: 'same' | 'added' | 'removed'`. Items absent from `new-object` but
  present in `old-object` are appended with `_change: 'removed'`.
- `modifiedRules` derivation now calls `annotateRule` per pair from `rawModified`.
- `renderRefList` returns `React.ReactNode` with color coding when diff tags are present:
  - **Added**: green bold `+name`
  - **Removed**: red strikethrough `−name`
  - **Same / initial attempt**: plain text (backward compatible)

**PDF (`src/fa/services/session_changes_pdf.py`):**

- `_build_ref_items(new_refs, old_refs)` nested helper builds `[{name, change}]` lists
  with html-escaped names.
- Modified access-rules store `source_items` / `dest_items` alongside the existing `source` /
  `destination` plain-name lists.
- `_render_ref_items()` in `_add_rules_table` produces ReportLab XML markup:
  `<font color="#389e0d"><b>+name</b></font>` for added,
  `<font color="#cf1322"><strike>-name</strike></font>` for removed.
- `_data_row` uses `_render_ref_items` when `source_items`/`dest_items` are present; falls back to
  plain join for initial-attempt rules (no regression).

---

## Key Files

| File | Change |
|---|---|
| `src/fa/models.py` | Added `updated_rule_uids` field to `CreateResult` |
| `src/fa/services/package_workflow.py` | `_find_existing_rule_uids()`, update-or-create loop |
| `src/fa/services/ritm_workflow_service.py` | `disable_rules` includes both UID lists |
| `src/fa/services/session_changes_pdf.py` | `_build_ref_items`, `_render_ref_items`, diff-aware modified-rule handling |
| `webui/src/components/RulesTable.tsx` | Comments and Rule Name columns made editable (`Input`) |
| `webui/src/pages/RitmEdit.tsx` | `annotateRule`, `renderRefList` with diff colors |

---

## Design Decisions

- **Rollback semantics**: only `created_rule_uids` are deleted on failure; `updated_rule_uids` are
  pre-existing rules that must not be deleted even on rollback.
- **`annotateRule` no-op on initial attempts**: when `old-object` is absent (or has no source UIDs),
  all items get `_change: 'same'` and render as plain text — zero visual regression for initial
  attempts.
- **Existing hosts scan** in the PDF now covers both `new_obj` and `old_obj` source/dest refs so
  removed hosts still appear in the "Existing" objects summary.
