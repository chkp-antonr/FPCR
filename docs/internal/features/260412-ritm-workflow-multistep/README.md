# RITM Multi-Step Workflow (Plan → Apply → Verify)

**Date:** 2026-04-12

**Status:** ✅ Complete

**Raw Logs:** `docs/_AI_/260412-flow/`

---

## Overview

Extended the RITM workflow from a single "Generate YAML Plan" button to a proper multi-step
execution pipeline: **Plan → Apply → Verify**. Enforced the architecture boundary that all logic
lives on the backend and the frontend is input/output only.

---

## Problems Solved

### Bug: `PolicyItem` vs `Policy` in `generate-evidence`

`generate-evidence` was querying `select(PolicyItem)` (a Pydantic model) instead of `select(Policy)`
(the SQLModel table). This caused a SQLAlchemy `ArgumentError` at runtime.

**Fix:** Import and use `Policy` (the table class) for DB queries.

**Regression test:** `test_generate_evidence_uses_policy_table_when_no_created_objects`

### Bug: Object lookup using wrong API payload key

`_find_cp_objects_in_domain` sent `{"ip-address": search}` to `show-hosts`, but Check Point
API expects `{"filter": search}`. Objects were never found → spurious host create attempts →
`Validation failed` errors from the API.

**Fix:** Use `filter`-based queries for all object type lookups (matching `cpsearch` patterns).
Added exact-IP post-filter: `if obj.get("ipv4-address") != search: continue`.

**Regression test:** `test_match_reuses_existing_host_without_create`

---

## Architecture Enforcement

**Requirement (from user):** "No logic on frontend. Everything must be available via backend
(from CI/CD). Frontend is for input/output only."

The YAML plan generation logic was originally written in the React handler (`handleTryAndVerify`).
It was moved to a dedicated backend endpoint:

```
POST /api/v1/ritm/{ritm_number}/plan-yaml
```

The `_build_plan_yaml_from_policies()` helper on the backend:

- Parses IP/CIDR/range patterns with compiled regex
- Generates `add-host`, `add-network`, `add-address-range` entries (deduplicated by domain+name key)
- Generates `add-access-rule` entries with source/destination/service lists
- Returns YAML string + `changes` summary dict

---

## Multi-Step Workflow

### Frontend (`RitmEdit.tsx`)

Replaced the flat "Generate YAML Plan" card with a three-step `Steps` component:

| Step | State | Action | Result |
|------|-------|--------|--------|
| Plan | `idle` | "Generate YAML Plan" | YAML display card appears |
| Apply | `planned` | "Apply (Try)" | Apply Results card appears |
| Verify | `applied` | "Verify" | Verify Results card appears |

- Each step has its own loading state (`planning`, `applying`, `verifying`)
- "Re-plan" and "Reset" buttons allow going back at any stage
- "Submit for Approval" gated on `workflowStep === 'verified'`

### New Backend Endpoints

#### `POST /ritm/{ritm_number}/apply` → `ApplyResponse`

1. Loads all `Policy` rows for the RITM
2. Pre-loads `CachedPackage` rows to resolve `access_layer` per policy
3. For each policy:
   - Calls `ObjectMatcher.match_and_create_objects()` for source and dest IPs
   - Persists newly created objects to `ritm_created_objects`
   - Builds CP API `rule_data` (resolves position: top/bottom/section-relative/absolute)
   - Calls `CheckPointRuleManager.add()` to create the access rule
   - Persists created rule to `ritm_created_rules`
4. After all rules created, calls `show-changes` on the open Management API session
5. Returns `ApplyResponse(objects_created, rules_created, errors, warnings, session_changes)`

#### `POST /ritm/{ritm_number}/verify` → `VerifyResponse`

1. Loads all `Policy` rows, deduplicates to unique `(domain_uid, package_uid)` combos
2. For each combo calls `PolicyVerifier.verify_policy(domain_name, package_name)`
3. Persists each result to `ritm_verification`
4. Returns `VerifyResponse(verified, errors)`

### `show-changes` Integration

After apply completes, calls `show-changes` with no parameters (returns current open session diff).
Result stored in `session_changes: dict | None` on `ApplyResponse`.

Displayed in frontend as an Ant Design `Collapse` panel ("Session Changes") — **collapsed by
default**, with Copy and Download (JSON) buttons in the panel header.

**Bug fix:** Used `sc_result.data is not None` (not truthiness) to handle empty `{}` response,
and removed `payload={}` which caused the call to fail.

---

## New Models

### `src/fa/models.py`

```python
class ApplyResponse(BaseModel):
    objects_created: int
    rules_created: int
    errors: list[str]
    warnings: list[str]
    session_changes: dict | None = None

class VerifyResponse(BaseModel):
    verified: bool
    errors: list[str]

class PlanYamlResponse(BaseModel):
    yaml: str
    changes: dict
```

---

## Key Files Changed

| File | Change |
|------|--------|
| `src/fa/models.py` | Added `PlanYamlResponse`, `ApplyResponse`, `VerifyResponse` |
| `src/fa/routes/ritm_flow.py` | Added `plan_yaml`, `apply_ritm`, `verify_ritm` endpoints; `_build_plan_yaml_from_policies()`; `_as_list()` helper; `show-changes` call |
| `src/fa/services/object_matcher.py` | Fixed `filter`-based lookup; added exact-IP post-filter; `logger.debug` instrumentation |
| `webui/src/pages/RitmEdit.tsx` | Multi-step `Steps` component; `handleGeneratePlan`, `handleApply`, `handleVerify`, `handleResetWorkflow` handlers; Collapse panel for session changes |
| `webui/src/api/endpoints.ts` | Added `generatePlanYaml`, `applyRitm`, `verifyRitm` |
| `webui/src/types/index.ts` | Added `PlanYamlResponse`, `ApplyResponse`, `VerifyResponse` TS interfaces |

---

## Tests

| Test | File | Validates |
|------|------|-----------|
| `test_generate_evidence_uses_policy_table_when_no_created_objects` | `test_ritm.py` | PolicyItem vs Policy bug |
| `test_plan_yaml_generated_by_backend` | `test_ritm.py` | `/plan-yaml` endpoint |
| `test_match_reuses_existing_host_without_create` | `test_object_matcher.py` | filter-based lookup |

**16 tests passing** in `test_ritm.py`. Frontend build clean (no TS errors).

---

## `_as_list` Helper

DB stores `source_ips`/`dest_ips`/`services` as JSON strings (e.g. `'["1.1.1.1"]'`).
Module-level `_as_list(raw)` decodes both native `list` and JSON-encoded `str` transparently.
Previously nested inside `_build_plan_yaml_from_policies`, now a standalone module-level helper
reused by the `apply_ritm` endpoint.
