# RITM Integration Test Suite — Design Spec

**Date:** 2026-05-13

**Status:** Approved for implementation

**Author:** Anton Razumov

---

## Overview

Comprehensive integration tests for the RITM (Requested Item) firewall-change workflow. Tests run against a real Check Point management server using four distinct CP user accounts, covering the full lifecycle from creation through correction cycles, rejection, and final publication.

Key design decisions:

- **Real CP environment** — no mocks; tests exercise actual verify-policy, object creation, and publish calls.
- **Pytest class-based ordered scenarios** — each scenario is a `pytest` class with steps enforced via `pytest-order`; state flows between steps via class-level variables.
- **CP revision restore** — a named CP revision (`ritm_integration_baseline`) is restored before each scenario, giving deterministic starting state without full rebuild.
- **Four CP user accounts** — enforces and validates the permanent separation-of-duties rules (editor block, approver block) across correction cycles.

---

## Project Structure

```
tests/
└── integration/
    ├── conftest.py                      # env loading, 4 user clients, revision fixtures
    ├── cp_setup/
    │   ├── seed.py                      # one-time domain/object/section/rule seeding
    │   ├── revision.py                  # create / restore named CP revision
    │   └── schema.yaml                  # declarative CP objects, sections, services
    ├── scenarios/
    │   ├── test_scenario_01_happy_path.py
    │   ├── test_scenario_02_preverify_error.py
    │   ├── test_scenario_03_postcheck_rollback.py
    │   ├── test_scenario_04_rejection_cycle.py
    │   └── test_scenario_05_domain_change.py
    └── .env.test                        # credentials, domain names, revision name
```

Run the full suite:

```bash
pytest tests/integration/ -v
```

Run a single scenario:

```bash
pytest tests/integration/scenarios/test_scenario_01_happy_path.py -v
```

Seed the CP environment (run once, or when `--check` reports missing state):

```bash
python tests/integration/cp_setup/seed.py
```

---

## Environment Configuration (`.env.test`)

```ini
# Check Point management server
API_MGMT=192.168.1.100
API_USERNAME=admin
API_PASSWORD=secret

# Four test engineers (real CP accounts)
ENGINEER1_USER=eng1    ENGINEER1_PASS=pass1
ENGINEER2_USER=eng2    ENGINEER2_PASS=pass2
ENGINEER3_USER=eng3    ENGINEER3_PASS=pass3
ENGINEER4_USER=eng4    ENGINEER4_PASS=pass4

# Configurable domain names
TEST_DOMAIN_A=TestDomainA
TEST_DOMAIN_B=TestDomainB

# Named CP revision baseline
CP_REVISION_NAME=ritm_integration_baseline
```

---

## CP Seed Schema (`cp_setup/schema.yaml`)

The seed script creates the following in both `TEST_DOMAIN_A` and `TEST_DOMAIN_B`:

| Resource | Name | Notes |
|----------|------|-------|
| Policy section | `RITM_TEST_SECTION` | Target section for all test rules |
| Host | `Host_10.0.0.1` | Clean object, reused across scenarios |
| Host | `Host_10.0.0.2` | Clean object |
| Network | `Net_10.1.0.0_24` | Clean network object |
| Service | `svc_http_8080` | Custom TCP service |
| Service | `svc_custom_9999` | Custom TCP service |
| Host | `Host_BROKEN` | Intentionally misconfigured; triggers verify-policy failure |
| Rule (broken) | `BROKEN_RULE` | Rule in `RITM_TEST_SECTION` that causes pre-verify to fail; used only in Scenario 2 |

After seeding, `revision.py` creates (or updates) the named revision `CP_REVISION_NAME`.

---

## Fixtures (`conftest.py`)

### CP revision fixtures

```python
@pytest.fixture(scope="session")
async def cp_baseline():
    """Verifies the named revision exists; creates it via seed.py if absent."""

@pytest.fixture(scope="class")
async def cp_restored(cp_baseline):
    """Restores CP_REVISION_NAME before each scenario class runs."""
```

### Four authenticated clients

Each client logs in via `POST /api/v1/auth/login` at session start and retains its cookie.

```python
@pytest.fixture(scope="session")
async def eng1_client() -> AsyncClient: ...   # initial editor

@pytest.fixture(scope="session")
async def eng2_client() -> AsyncClient: ...   # first approver / rejecter

@pytest.fixture(scope="session")
async def eng3_client() -> AsyncClient: ...   # correction editor

@pytest.fixture(scope="session")
async def eng4_client() -> AsyncClient: ...   # second approver / rejecter
```

### Database

Fresh in-memory SQLite per pytest session (same pattern as `src/fa/tests/conftest.py`). The integration test DB is separate from the existing unit test DB.

---

## Scenario Class Pattern

```python
@pytest.mark.usefixtures("cp_restored")
class TestScenarioName:
    ritm_id: str = ""
    attempt: int = 0

    @pytest.mark.order(1)
    async def test_01_step_name(self, eng1_client): ...

    @pytest.mark.order(2)
    async def test_02_next_step(self, eng1_client, eng2_client): ...
```

State (`ritm_id`, `attempt`, evidence UIDs, session tokens) is stored as class-level variables. `pytest-order` enforces sequential execution within the class. A failure at step N skips all subsequent steps.

---

## Universal Per-Scenario Assertions

Every scenario verifies these guardrails as it progresses:

- **Lock exclusivity** — acquiring a second lock while one is held returns 409 or 400.
- **Role blocks** — after any actor touches the RITM, their now-blocked action returns HTTP 400.
- **DB state** — RITM status enum, `ritm_package_attempt.state`, and `ritm_editors` / `ritm_reviewers` rows match expected values after each transition.
- **Evidence structure** — `GET /ritm/{id}/evidence-history` returns the correct domain → package → attempt hierarchy with the correct `session_type` (`initial`, `correction`, `approval`).
- **Visibility** — the RITM does not appear in the creating editor's "available for approval" list; it appears only for eligible approvers.

---

## Scenario 1 — Happy Path

**CP state at start:** Clean baseline (both domains, clean sections, no RITM records in DB).

**Actors:** eng1 (editor), eng2 (approver).

| Step | Endpoint | Assertion |
|------|----------|-----------|
| 01 | `POST /ritm` (eng1) | 201; `ritm_id` saved; status=WIP; eng1 in `ritm_editors` |
| 02 | `POST /ritm/{id}/policy` (eng1) | 200; policy rows for DomainA + DomainB saved |
| 03 | `POST /ritm/{id}/pre-verify` (eng1) | `all_passed=true` |
| 04 | `POST /ritm/{id}/plan-yaml` (eng1) | YAML contains expected object names and `RITM_TEST_SECTION` |
| 05 | `POST /ritm/{id}/try-verify` (eng1) | attempt=1; both packages `VERIFIED_PENDING_APPROVAL_DISABLED`; evidence HTML non-empty |
| 06 | `GET /ritm/{id}/evidence-history` | 2 sessions; `session_type="initial"`; correct domain/package names |
| 07 | `GET /ritm/{id}/session-pdf?attempt=1` | 200; `content-type: application/pdf` |
| 08 | `POST /ritm/{id}/submit-for-approval` (eng1) | status=`READY_FOR_APPROVAL` |
| 09 | `GET /ritm` (eng1) | RITM absent from eng1's editable list |
| 10 | `PUT /ritm/{id}` approve (eng1) | 400 — eng1 is in `ritm_editors` |
| 11 | `POST /ritm/{id}/lock` (eng2) | 200; approver lock acquired |
| 12 | `GET /ritm/{id}/evidence-history` (eng2) | Same hierarchy; evidence intact |
| 13 | `PUT /ritm/{id}` approve (eng2) | status=`APPROVED`; eng2 in `ritm_reviewers` with `action="approved"` |
| 14 | `POST /ritm/{id}/publish` (eng2) | Both packages `APPROVAL_ENABLED_PUBLISHED` |
| 15 | `GET /ritm/{id}` | status=`COMPLETED` |

---

## Scenario 2 — Pre-Verify Error and Correction

**CP state at start:** Baseline + `BROKEN_RULE` active in `RITM_TEST_SECTION` (DomainA).

**Actors:** eng1 (editor), eng2 (approver).

| Step | Action | Assertion |
|------|--------|-----------|
| 01–02 | Create RITM + policy targeting `RITM_TEST_SECTION` in DomainA | Saved |
| 03 | `pre-verify` | `all_passed=false`; errors reference `BROKEN_RULE` |
| 04 | Fix via CP API: delete `BROKEN_RULE` directly | CP API 200 |
| 05 | `pre-verify` again | `all_passed=true` |
| 06 | `try-verify` | attempt=1; `VERIFIED_PENDING_APPROVAL_DISABLED` |
| 07–10 | submit → eng2 approves → publish → COMPLETED | status=`COMPLETED` |

---

## Scenario 3 — Post-Check Rollback

**CP state at start:** Clean baseline.

**Actors:** eng1 (editor), eng3 (approver — fresh, not involved in Scenarios 1–2 on this RITM).

| Step | Action | Assertion |
|------|--------|-----------|
| 01–02 | Create RITM with policy containing a conflicting rule (duplicate position in same section) | Saved |
| 03 | `pre-verify` | `all_passed=true` — baseline is clean |
| 04 | `try-verify` | Pre-check passes; rules created; post-check fails; rollback triggered |
| 05 | DB: `ritm_package_attempt.state` | `POSTCHECK_FAILED_RULES_DELETED` |
| 06 | CP API: verify created rules are absent | Rules deleted from CP |
| 07 | Update policy — remove conflicting rule | 200 |
| 08 | `try-verify` attempt=2 | `VERIFIED_PENDING_APPROVAL_DISABLED`; `session_type="correction"` |
| 09 | `GET /evidence-history` | Attempt 1: `POSTCHECK_FAILED_RULES_DELETED` (no evidence session); Attempt 2: evidence present |
| 10–12 | submit → eng3 approves → publish | status=`COMPLETED` |

---

## Scenario 4 — Rejection Cycle / 4-User Separation of Duties

**CP state at start:** Clean baseline.

**Actors:** eng1 (initial editor), eng2 (first rejecter), eng3 (correction editor), eng4 (second rejecter).

| Steps | Actor | Action | Key Assertion |
|-------|-------|--------|---------------|
| 01–04 | eng1 | create, policy, try-verify, submit | status=`READY_FOR_APPROVAL` |
| 05 | eng1 | `PUT` approve own RITM | 400 — in `ritm_editors` |
| 06 | eng2 | acquire approver lock + review evidence | Evidence hierarchy correct |
| 07 | eng2 | `PUT status=0` reject with feedback text | status=WIP; feedback stored; eng2 in `ritm_reviewers` |
| 08 | eng2 | try to acquire editor lock | 400 — in `ritm_reviewers` |
| 09 | eng3 | acquire editor lock | 200 — eng3 not in `ritm_reviewers` |
| 10–12 | eng3 | update policy (add host, change service), try-verify attempt=2 | `session_type="correction"` |
| 13 | eng3 | submit for approval | status=`READY_FOR_APPROVAL` |
| 14 | eng2 | try to approve again | 400 — still in `ritm_reviewers` |
| 15 | eng3 | try to approve own correction | 400 — in `ritm_editors` |
| 16 | eng4 | acquire approver lock + review evidence | Sees attempt 1 (`initial`) and attempt 2 (`correction`) |
| 17 | eng4 | reject with feedback (2nd rejection) | status=WIP; eng4 in `ritm_reviewers` |
| 18 | eng4 | try to acquire editor lock | 400 — in `ritm_reviewers` |
| 19 | eng3 | try to approve | 400 — in `ritm_editors` |
| 20 | eng1 | re-acquire editor lock | 200 — eng1 not in `ritm_reviewers`; can still edit |
| 21 | eng1 | try-verify attempt=3, submit | status=`READY_FOR_APPROVAL`; scenario ends here — 4 named users are all blocked |
| 22 | — | **Dead-end verification**: eng1 in `ritm_editors`, eng3 in `ritm_editors`, eng2 in `ritm_reviewers`, eng4 in `ritm_reviewers` | All four users confirmed blocked; final approval would require a 5th CP account (e.g. `API_USERNAME` admin) — not asserted in this scenario; scenario is complete at step 21 |

---

## Scenario 5 — Domain Change After Rejection

**CP state at start:** Clean baseline.

**Actors:** eng1 (editor), eng2 (rejecter with domain-change feedback), eng3 (correction editor), eng4 (final approver).

| Step | Action | Assertion |
|------|--------|-----------|
| 01–04 | eng1 creates RITM with policy in DomainA only, try-verify, submit | DomainA package `VERIFIED_PENDING_APPROVAL_DISABLED` |
| 05–06 | eng2 rejects: feedback = "move rules to DomainB" | status=WIP |
| 07 | eng3 acquires editor lock, updates policy to DomainB | Policy rows updated |
| 08 | `POST /plan-yaml` | YAML contains DomainB objects; DomainA objects/rules from attempt 1 absent |
| 09 | `try-verify` attempt=2 | DomainB package `VERIFIED_PENDING_APPROVAL_DISABLED`; `session_type="correction"` |
| 10 | CP state: DomainA rules from attempt 1 | Still present in CP as published-disabled (submit-for-approval published them); `plan-yaml` for attempt 2 must include explicit removal steps for DomainA rules — assert YAML contains a delete/disable action for the DomainA rule UIDs recorded in `ritm_created_rules` |
| 11 | `GET /evidence-history` | Attempt 1: DomainA session; Attempt 2: DomainB session |
| 12 | eng3 submits | status=`READY_FOR_APPROVAL` |
| 13–14 | eng4 approves + publishes | DomainB package `APPROVAL_ENABLED_PUBLISHED`; status=`COMPLETED` |

---

## New Dependencies

| Package | Purpose | License |
|---------|---------|---------|
| `pytest-order` | Enforce step ordering within scenario classes | MIT |
| `python-dotenv` | Load `.env.test` before fixtures run | BSD-3 |

Both are already compatible with the project's MIT/BSD dependency policy.

---

## Out of Scope

- Load / performance testing
- UI / browser automation (WebUI is not exercised here)
- Mock-based CI pipeline (future hybrid profile)
- Evidence PDF visual correctness (content-type check only)
