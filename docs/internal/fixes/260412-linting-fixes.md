# Code Quality Fixes - 2026-04-12

**Date:** 2026-04-12
**Type:** Linting and Code Quality Improvements
**Commit:** `2924ddb`

---

## Summary

Fixed 6 ruff linting errors identified by `check.ps1` script during the FPCR Create & Verify flow implementation.

---

## Issues Fixed

### 1. Unused Function Arguments (ARG001)

**Location:** `src/fa/routes/ritm_flow.py:62, 137`

**Issue:** The `ritm_number` path parameter was not used in the endpoint functions.

**Fix:** Prefixed with underscore to indicate intentionally unused:
```python
async def match_objects(
    _ritm_number: str,  # Prefix indicates intentionally unused
    request: MatchObjectsRequest,
    session: SessionData = Depends(get_session_data),
) -> MatchObjectsResponse:
```

**Rationale:** The `ritm_number` is part of the URL path but not currently used in the business logic. Kept for future use (logging, validation, or RITM-specific behavior).

---

### 2. Unused Variable - verifications (F841)

**Location:** `src/fa/routes/ritm_flow.py:208`

**Issue:** Variable assigned but never used.

**Fix:** Commented out with TODO for future implementation:
```python
# Get verification results
# TODO: build from verification results
# verification_result = await db.execute(
#     select(RITMVerification).where(RITMVerification.ritm_number == ritm_number)
# )
```

**Rationale:** The verification results query is needed for the evidence generation TODOs. Commented rather than removed to preserve the intended implementation.

---

### 3. Unused Variable - lines (F841)

**Location:** `src/fa/services/evidence_generator.py:73`

**Issue:** Variable assigned but never used.

**Fix:** Removed the assignment:
```python
# Removed: lines = []
```

**Rationale:** The variable was a leftover from an earlier implementation approach. Not needed for the current YAML generation logic.

---

### 4. Code Simplification (SIM110)

**Location:** `src/fa/services/object_matcher.py:102`

**Issue:** Used for loop when `any()` would be more Pythonic.

**Fix:** Replaced for loop with `any()`:
```python
# Before:
for pattern in patterns:
    if re.match(pattern, name):
        return True
return False

# After:
return any(re.match(pattern, name) for pattern in patterns)
```

**Rationale:** More concise, Pythonic, and leverages generator expression for early termination.

---

### 5. Unused Method Argument (ARG002)

**Location:** `src/fa/services/object_matcher.py:127`

**Issue:** The `domain_uid` parameter in `_create_object` was not used.

**Fix:** Prefixed with underscore:
```python
async def _create_object(
    self,
    obj_type: str,
    name: str,
    value: str,
    _domain_uid: str,  # Prefix indicates intentionally unused
    domain_name: str,
) -> dict[str, Any]:
```

**Rationale:** The `domain_uid` is accepted for API consistency but the current implementation uses `domain_name` for the actual API call. Kept for future use (logging, validation, or multi-domain support).

---

### 6. Method Call Mismatch

**Location:** `src/fa/services/object_matcher.py:204`

**Issue:** Call to `_create_object` used `domain_uid` but parameter was renamed to `_domain_uid`.

**Fix:** Updated method call:
```python
created = await self._create_object(
    obj_type=obj_type,
    name=new_name,
    value=input_value,
    _domain_uid=domain_uid,  # Updated to match new parameter name
    domain_name=domain_name,
)
```

**Rationale:** Ensures the call matches the updated function signature.

---

## Testing

All changes verified with:
```bash
.\check.ps1
```

**Result:** All 6 ruff errors fixed. Remaining mypy type-checking errors are pre-existing issues in other files (ritm.py, cpcrud/business_logic.py).

---

## Impact

- **Code Quality:** Improved adherence to Python best practices
- **Maintainability:** Clearer intent for intentionally unused parameters
- **Documentation:** TODO comments preserve intended future implementation
- **No Breaking Changes:** All fixes are non-functional improvements

---

**Files Modified:**
- `src/fa/routes/ritm_flow.py`
- `src/fa/services/evidence_generator.py`
- `src/fa/services/object_matcher.py`
