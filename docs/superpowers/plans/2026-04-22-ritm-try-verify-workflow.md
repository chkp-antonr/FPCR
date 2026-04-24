# RITM Try & Verify Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor RITM workflow from 3-step (Plan → Apply → Verify) to 2-step (Plan → Try & Verify) with automatic rollback, rule disabling, evidence generation, and session persistence.

**Architecture:** Service-layer architecture with `PackageWorkflowService` handling per-package operations (verify → create → verify → rollback/disable) and `RITMWorkflowService` orchestrating across all packages. Evidence is captured per-package, combined at end, and session UIDs are stored for re-creation.

**Tech Stack:** FastAPI, SQLAlchemy, Python 3.13, React (TypeScript), Check Point API (cpaiops)

---

## File Structure

### New Files

- `src/fa/services/package_workflow.py` — Per-package workflow operations
- `src/fa/services/ritm_workflow_service.py` — Try & Verify orchestrator
- `src/fa/tests/test_package_workflow.py` — PackageWorkflowService tests
- `src/fa/tests/test_ritm_workflow_service.py` — RITMWorkflowService tests
- `src/fa/tests/test_ritm_flow_routes.py` — API endpoint tests (update existing)

### Modified Files

- `src/fa/models.py` — Add new models: PackageResult, TryVerifyResponse, CreateResult, EvidenceData, RITMSession
- `src/fa/routes/ritm_flow.py` — Add /try-verify endpoint, comment out /apply and /verify, add /recreate-evidence
- `webui/src/pages/RitmEdit.tsx` — Update to 2-step workflow, add re-create evidence button
- `webui/src/api/endpoints.ts` — Add tryVerifyRitm and recreateEvidence methods
- `webui/src/types.ts` — Add TryVerifyResponse, PackageResult types

---

## Task 1: Add New Models to models.py

**Files:**

- Modify: `src/fa/models.py`

- [ ] **Step 1: Add new response and result models**

Add these classes to `src/fa/models.py` after the existing model definitions (around line 400):

```python
class PackageResult(BaseModel):
    """Result of Try & Verify for a single package."""
    package: str
    status: Literal["success", "skipped", "create_failed", "verify_failed"]
    rules_created: int = 0
    objects_created: int = 0
    errors: list[str] = []


class CreateResult(BaseModel):
    """Result of object and rule creation with UIDs for rollback."""
    objects_created: int
    rules_created: int
    created_rule_uids: list[str]
    created_object_uids: list[str]
    errors: list[str] = field(default_factory=list)


class EvidenceData(BaseModel):
    """Captured evidence for a single package."""
    domain_name: str
    package_name: str
    package_uid: str
    domain_uid: str
    session_changes: dict[str, Any]
    session_uid: str | None = None
    sid: str | None = None


class TryVerifyResponse(BaseModel):
    """Response from Try & Verify operation."""
    results: list[PackageResult]
    evidence_pdf: bytes | None = None
    evidence_html: str | None = None
    published: bool
    session_changes: dict[str, Any] | None = None
```

- [ ] **Step 2: Add RITMSession database model**

Add the table definition to `src/fa/models.py` in the database models section (around line 150, after existing table classes):

```python
class RITMSession(Base):
    """Store session UIDs per domain for each RITM.

    Enables evidence re-creation by storing the session that made changes.
    """
    __tablename__ = "ritm_sessions"

    id: int = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number")
    domain_name: str
    domain_uid: str
    session_uid: str
    sid: str
    created_at: datetime = Field(default_factory=datetime.now(UTC))
```

- [ ] **Step 3: Run type check to verify no errors**

Run: `uv run mypy src/fa/models.py`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add src/fa/models.py
git commit -m "feat: add TryVerify models - PackageResult, CreateResult, EvidenceData, TryVerifyResponse, RITMSession"
```

---

## Task 2: Create PackageWorkflowService

**Files:**

- Create: `src/fa/services/package_workflow.py`
- Test: `src/fa/tests/test_package_workflow.py`

- [ ] **Step 1: Create the service file with class structure**

Create `src/fa/services/package_workflow.py`:

```python
"""Per-package workflow service for Try & Verify operation."""

import logging
from dataclasses import dataclass
from typing import Any

from cpaiops import CPAIOPSClient
from cpcrud.rule_manager import CheckPointRuleManager

from ..services.object_matcher import ObjectMatcher
from ..services.policy_verifier import PolicyVerifier, VerifyResult
from ..models import CreateResult, EvidenceData

logger = logging.getLogger(__name__)


@dataclass
class PackageInfo:
    """Information about a package to process."""
    domain_name: str
    domain_uid: str
    package_name: str
    package_uid: str
    policies: list[Any]  # List of Policy objects


class PackageWorkflowService:
    """Handles per-package workflow operations.

    Workflow: verify_first → create_objects_and_rules → verify_again
    On verify_again failure: rollback_rules
    On verify_again success: disable_rules, capture_evidence
    """

    def __init__(
        self,
        client: CPAIOPSClient,
        package_info: PackageInfo,
        ritm_number: str,
        mgmt_name: str,
    ):
        self.client = client
        self.info = package_info
        self.ritm_number = ritm_number
        self.mgmt_name = mgmt_name
        self.logger = logging.getLogger(__name__)

    async def verify_first(self) -> VerifyResult:
        """Pre-creation verification.

        Returns:
            VerifyResult with success=True to proceed, False to skip package.
        """
        verifier = PolicyVerifier(self.client)
        result = await verifier.verify_policy(
            domain_name=self.info.domain_name,
            package_name=self.info.package_name,
        )
        status = "PASS" if result.success else "FAIL"
        self.logger.info(
            f"[{self.info.package_name}] Step: verify_first | Status: {status}"
        )
        return result

    async def create_objects_and_rules(self) -> CreateResult:
        """Create objects and rules.

        Returns:
            CreateResult with created UIDs for potential rollback.
        """
        matcher = ObjectMatcher(self.client)
        rule_mgr = CheckPointRuleManager(self.client)

        created_rule_uids: list[str] = []
        created_object_uids: list[str] = []
        errors: list[str] = []

        # Access layer resolution - reuse logic from current apply_ritm
        package_result = await self.client.api_call(
            mgmt_name=self.mgmt_name,
            command="show-package",
            domain=self.info.domain_name,
            payload={"uid": self.info.package_uid},
        )

        if not package_result.success or not package_result.data:
            errors.append(
                f"Layer lookup error for package '{self.info.package_name}': "
                f"{package_result.message or package_result.code or 'show-package failed'}"
            )
            return CreateResult(
                objects_created=0,
                rules_created=0,
                created_rule_uids=[],
                created_object_uids=[],
                errors=errors,
            )

        # Resolve access layer
        access_layer = self._resolve_access_layer(package_result.data)
        if not access_layer:
            errors.append(
                f"Layer lookup error for package '{self.info.package_name}': "
                "no access layer found"
            )
            return CreateResult(
                objects_created=0,
                rules_created=0,
                created_rule_uids=[],
                created_object_uids=[],
                errors=errors,
            )

        # Process each policy in this package
        for policy in self.info.policies:
            # Extract IPs and services
            source_ips = self._extract_list(policy.source_ips)
            dest_ips = self._extract_list(policy.dest_ips)
            services = self._extract_list(policy.services)

            # Create/match objects
            try:
                source_objs = await matcher.match_and_create_objects(
                    inputs=source_ips,
                    domain_uid=self.info.domain_uid,
                    domain_name=self.info.domain_name,
                    create_missing=True,
                )
                dest_objs = await matcher.match_and_create_objects(
                    inputs=dest_ips,
                    domain_uid=self.info.domain_uid,
                    domain_name=self.info.domain_name,
                    create_missing=True,
                )
            except Exception as obj_err:
                self.logger.error(
                    f"Object match/create failed for rule '{policy.rule_name}': {obj_err}",
                    exc_info=True,
                )
                errors.append(f"Object error for {policy.rule_name}: {obj_err}")
                continue

            # Track created object UIDs
            for obj in source_objs + dest_objs:
                if obj.get("created"):
                    obj_uid = obj.get("object_uid")
                    if obj_uid:
                        created_object_uids.append(obj_uid)

            # Build rule data
            source_names = [
                r.get("object_name") or r.get("input", "") for r in source_objs
            ]
            dest_names = [
                r.get("object_name") or r.get("input", "") for r in dest_objs
            ]

            position = self._build_position(policy)

            rule_data: dict[str, Any] = {
                "name": policy.rule_name,
                "layer": access_layer,
                "comments": policy.comments,
                "source": source_names or ["Any"],
                "destination": dest_names or ["Any"],
                "service": services if services else ["Any"],
                "action": policy.action,
                "track": {"type": policy.track},
                "position": position,
            }

            # Create rule
            try:
                result = await rule_mgr.add(
                    mgmt_name=self.mgmt_name,
                    domain=self.info.domain_name,
                    rule_type="access-rule",
                    data=rule_data,
                )
            except Exception as rule_err:
                self.logger.error(
                    f"Rule add failed for '{policy.rule_name}': {rule_err}",
                    exc_info=True,
                )
                errors.append(f"Rule error for {policy.rule_name}: {rule_err}")
                continue

            if result["success"]:
                rule_info = result["success"][0]
                created_uid = rule_info.get("uid")
                if isinstance(created_uid, str) and created_uid:
                    created_rule_uids.append(created_uid)
            elif result.get("errors"):
                for e in result["errors"]:
                    errors.append(e.get("error", str(e)))

        self.logger.info(
            f"[{self.info.package_name}] Step: create_objects_and_rules | "
            f"Created: {len(created_object_uids)} objects, {len(created_rule_uids)} rules"
        )

        return CreateResult(
            objects_created=len(created_object_uids),
            rules_created=len(created_rule_uids),
            created_rule_uids=created_rule_uids,
            created_object_uids=created_object_uids,
            errors=errors,
        )

    async def verify_again(self) -> VerifyResult:
        """Post-creation verification.

        Returns:
            VerifyResult with success to keep rules, False to trigger rollback.
        """
        verifier = PolicyVerifier(self.client)
        result = await verifier.verify_policy(
            domain_name=self.info.domain_name,
            package_name=self.info.package_name,
        )
        status = "PASS" if result.success else "FAIL"
        self.logger.info(
            f"[{self.info.package_name}] Step: verify_again | Status: {status}"
        )
        return result

    async def rollback_rules(self, rule_uids: list[str]) -> None:
        """Delete newly created rules when verification fails."""
        rule_mgr = CheckPointRuleManager(self.client)
        for rule_uid in rule_uids:
            try:
                await rule_mgr.delete(
                    mgmt_name=self.mgmt_name,
                    domain=self.info.domain_name,
                    uid=rule_uid,
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to rollback rule {rule_uid}: {e}",
                    exc_info=True,
                )
        self.logger.warning(
            f"[{self.info.package_name}] Step: rollback_rules | "
            f"Rolled back {len(rule_uids)} rules"
        )

    async def disable_rules(self, rule_uids: list[str]) -> None:
        """Disable newly created rules after successful verification."""
        for rule_uid in rule_uids:
            try:
                await self.client.api_call(
                    mgmt_name=self.mgmt_name,
                    domain=self.info.domain_name,
                    command="set-access-rule",
                    payload={"uid": rule_uid, "enabled": False},
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to disable rule {rule_uid}: {e}",
                    exc_info=True,
                )
        self.logger.info(
            f"[{self.info.package_name}] Step: disable_rules | "
            f"Disabled {len(rule_uids)} rules"
        )

    async def capture_evidence(self) -> EvidenceData:
        """Capture show-changes for this package's session.

        Returns:
            EvidenceData with session_changes and session UID.
        """
        # Get SID for this domain
        sid_record = await self.client.cache.get_sid(
            mgmt_name=self.mgmt_name, domain=self.info.domain_name
        )
        if not sid_record or not sid_record.sid:
            self.logger.warning(
                f"[{self.info.package_name}] No SID found for evidence capture"
            )
            return EvidenceData(
                domain_name=self.info.domain_name,
                package_name=self.info.package_name,
                package_uid=self.info.package_uid,
                domain_uid=self.info.domain_uid,
                session_changes={},
            )

        domain_sid = sid_record.sid
        session_uid = await self.client.cache.get_uid_by_sid(domain_sid)

        # Call show-changes scoped to this session
        sc_payload: dict[str, Any] = {}
        if session_uid:
            sc_payload["to-session"] = session_uid

        sc_result = await self.client.api_call(
            mgmt_name=self.mgmt_name,
            domain=self.info.domain_name,
            command="show-changes",
            details_level="full",
            payload=sc_payload,
        )

        session_changes = (
            sc_result.data if sc_result.success and sc_result.data else {}
        )

        self.logger.info(
            f"[{self.info.package_name}] Step: capture_evidence | "
            f"Session UID: {session_uid}"
        )

        return EvidenceData(
            domain_name=self.info.domain_name,
            package_name=self.info.package_name,
            package_uid=self.info.package_uid,
            domain_uid=self.info.domain_uid,
            session_changes=session_changes,
            session_uid=session_uid,
            sid=domain_sid,
        )

    def _resolve_access_layer(self, package_data: dict[str, Any]) -> str | None:
        """Resolve access layer from show-package response."""
        layers = package_data.get("access-layers", [])
        if isinstance(layers, list) and layers:
            domain_layers = [
                layer
                for layer in layers
                if isinstance(layer, dict)
                and layer.get("domain", {}).get("uid") == self.info.domain_uid
            ]
            selected_layer = domain_layers[0] if domain_layers else layers[0]
            if isinstance(selected_layer, dict):
                return selected_layer.get("uid") or selected_layer.get("name")

        fallback_layer = package_data.get("access-layer")
        if isinstance(fallback_layer, dict):
            return fallback_layer.get("uid") or fallback_layer.get("name")
        elif isinstance(fallback_layer, str) and fallback_layer.strip():
            return fallback_layer

        return None

    def _extract_list(self, raw: Any) -> list[str]:
        """Extract list from database field (may be list or JSON string)."""
        import json

        if isinstance(raw, list):
            return [str(v) for v in raw]
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except Exception:
                return [raw]
        return []

    def _build_position(self, policy: Any) -> Any:
        """Build CP API position value from policy."""
        position_type = policy.position_type
        position_number = policy.position_number

        if position_type == "custom" and position_number is not None:
            return position_number
        elif policy.section_name:
            return {position_type: policy.section_name}
        else:
            return position_type
```

- [ ] **Step 2: Create test file structure**

Create `src/fa/tests/test_package_workflow.py`:

```python
"""Tests for PackageWorkflowService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from fa.services.package_workflow import PackageWorkflowService, PackageInfo
from fa.models import CreateResult


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.api_call = AsyncMock()
    client.cache = MagicMock()
    client.cache.get_sid = AsyncMock()
    client.cache.get_uid_by_sid = AsyncMock(return_value="test-session-uid")
    return client


@pytest.fixture
def package_info():
    return PackageInfo(
        domain_name="TestDomain",
        domain_uid="test-domain-uid",
        package_name="TestPackage",
        package_uid="test-package-uid",
        policies=[],
    )


@pytest.mark.asyncio
async def test_verify_first_success(mock_client, package_info):
    """Test verify_first returns success when policy verification passes."""
    from fa.services.policy_verifier import VerifyResult

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Mock PolicyVerifier to return success
    with pytest.mock.patch(
        "fa.services.package_workflow.PolicyVerifier"
    ) as mock_verifier_class:
        mock_verifier = AsyncMock()
        mock_verifier.verify_policy = AsyncMock(
            return_value=VerifyResult(success=True, errors=[])
        )
        mock_verifier_class.return_value = mock_verifier

        result = await service.verify_first()

        assert result.success is True
        assert result.errors == []


@pytest.mark.asyncio
async def test_verify_first_failure(mock_client, package_info):
    """Test verify_first returns failure when policy verification fails."""
    from fa.services.policy_verifier import VerifyResult

    service = PackageWorkflowService(
        client=mock_client,
        package_info=package_info,
        ritm_number="RITM1234567",
        mgmt_name="test-mgmt",
    )

    # Mock PolicyVerifier to return failure
    with pytest.mock.patch(
        "fa.services.package_workflow.PolicyVerifier"
    ) as mock_verifier_class:
        mock_verifier = AsyncMock()
        mock_verifier.verify_policy = AsyncMock(
            return_value=VerifyResult(success=False, errors=["Verification failed"])
        )
        mock_verifier_class.return_value = mock_verifier

        result = await service.verify_first()

        assert result.success is False
        assert result.errors == ["Verification failed"]


def test_extract_list_from_list():
    """Test _extract_list with list input."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d", domain_uid="duid", package_name="p", package_uid="puid", policies=[]
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._extract_list(["a", "b", "c"])
    assert result == ["a", "b", "c"]


def test_extract_list_from_json_string():
    """Test _extract_list with JSON string input."""
    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d", domain_uid="duid", package_name="p", package_uid="puid", policies=[]
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._extract_list('["a", "b", "c"]')
    assert result == ["a", "b", "c"]


def test_build_position_custom():
    """Test _build_position with custom position."""
    mock_policy = MagicMock()
    mock_policy.position_type = "custom"
    mock_policy.position_number = 5
    mock_policy.section_name = None

    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d", domain_uid="duid", package_name="p", package_uid="puid", policies=[]
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._build_position(mock_policy)
    assert result == 5


def test_build_position_with_section():
    """Test _build_position with section."""
    mock_policy = MagicMock()
    mock_policy.position_type = "top"
    mock_policy.position_number = None
    mock_policy.section_name = "MySection"

    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d", domain_uid="duid", package_name="p", package_uid="puid", policies=[]
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._build_position(mock_policy)
    assert result == {"top": "MySection"}


def test_build_position_simple():
    """Test _build_position with simple position type."""
    mock_policy = MagicMock()
    mock_policy.position_type = "bottom"
    mock_policy.position_number = None
    mock_policy.section_name = None

    service = PackageWorkflowService(
        client=MagicMock(),
        package_info=PackageInfo(
            domain_name="d", domain_uid="duid", package_name="p", package_uid="puid", policies=[]
        ),
        ritm_number="RITM123",
        mgmt_name="mgmt",
    )
    result = service._build_position(mock_policy)
    assert result == "bottom"
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest src/fa/tests/test_package_workflow.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/fa/services/package_workflow.py src/fa/tests/test_package_workflow.py
git commit -m "feat: add PackageWorkflowService for per-package Try & Verify operations"
```

---

## Task 3: Create RITMWorkflowService

**Files:**

- Create: `src/fa/services/ritm_workflow_service.py`
- Test: `src/fa/tests/test_ritm_workflow_service.py`

- [ ] **Step 1: Create the orchestrator service**

Create `src/fa/services/ritm_workflow_service.py`:

```python
"""RITM Try & Verify orchestrator service."""

import logging
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from cpaiops import CPAIOPSClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from ..config import settings
from ..db import engine
from ..models import (
    CreateResult,
    EvidenceData,
    PackageResult,
    Policy,
    RITM,
    RITMSession,
    TryVerifyResponse,
)
from ..services.session_changes_pdf import SessionChangesPDFGenerator
from .package_workflow import PackageInfo, PackageWorkflowService

logger = logging.getLogger(__name__)


class RITMWorkflowService:
    """Orchestrates Try & Verify across all packages in a RITM."""

    def __init__(
        self,
        client: CPAIOPSClient,
        ritm_number: str,
        username: str,
    ):
        self.client = client
        self.ritm_number = ritm_number
        self.username = username
        self.mgmt_name = client.get_mgmt_names()[0]
        self.logger = logging.getLogger(__name__)
        self.pdf_generator = SessionChangesPDFGenerator()

    async def try_verify(self) -> TryVerifyResponse:
        """Execute full Try & Verify workflow.

        Returns:
            TryVerifyResponse with per-package results, evidence, and publish status.
        """
        # Group policies by package
        packages = await self._group_by_package()
        self.logger.info(
            f"Try & Verify for RITM {self.ritm_number}: "
            f"Processing {len(packages)} unique package(s)"
        )

        results: list[PackageResult] = []
        all_evidence: list[EvidenceData] = []
        any_success = False

        for pkg_info in packages:
            self.logger.info(
                f"Processing package: {pkg_info.package_name} "
                f"(domain: {pkg_info.domain_name})"
            )

            pkg_workflow = PackageWorkflowService(
                client=self.client,
                package_info=pkg_info,
                ritm_number=self.ritm_number,
                mgmt_name=self.mgmt_name,
            )

            # Step 1: Verify FIRST (pre-check)
            verify1 = await pkg_workflow.verify_first()
            if not verify1.success:
                results.append(
                    PackageResult(
                        package=pkg_info.package_name,
                        status="skipped",
                        errors=verify1.errors,
                    )
                )
                continue

            # Step 2: Create objects and rules
            create_result = await pkg_workflow.create_objects_and_rules()
            if create_result.errors:
                results.append(
                    PackageResult(
                        package=pkg_info.package_name,
                        status="create_failed",
                        objects_created=create_result.objects_created,
                        rules_created=create_result.rules_created,
                        errors=create_result.errors,
                    )
                )
                continue

            # Step 3: Verify AGAIN (post-creation)
            verify2 = await pkg_workflow.verify_again()
            if not verify2.success:
                # Rollback rules
                await pkg_workflow.rollback_rules(create_result.created_rule_uids)
                results.append(
                    PackageResult(
                        package=pkg_info.package_name,
                        status="verify_failed",
                        objects_created=create_result.objects_created,
                        rules_created=create_result.rules_created,
                        errors=verify2.errors,
                    )
                )
                continue

            # Step 4: Success path
            # Capture evidence for this package
            evidence = await pkg_workflow.capture_evidence()
            all_evidence.append(evidence)

            # Disable newly created rules
            await pkg_workflow.disable_rules(create_result.created_rule_uids)

            results.append(
                PackageResult(
                    package=pkg_info.package_name,
                    status="success",
                    objects_created=create_result.objects_created,
                    rules_created=create_result.rules_created,
                )
            )
            any_success = True

        # After all packages: combine evidence and publish
        combined_session_changes = self._combine_evidence(all_evidence)
        evidence_pdf, evidence_html = self._generate_evidence_artifacts(
            combined_session_changes
        )

        # Store session UIDs
        await self._store_session_uids(all_evidence)

        # Store evidence in RITM
        await self._store_evidence(combined_session_changes)

        # Publish if any packages succeeded
        published = False
        if any_success:
            await self._publish_session()
            published = True

        return TryVerifyResponse(
            results=results,
            evidence_pdf=evidence_pdf,
            evidence_html=evidence_html,
            published=published,
            session_changes=combined_session_changes,
        )

    async def _group_by_package(self) -> list[PackageInfo]:
        """Group policies by unique domain/package combinations."""
        async with AsyncSession(engine) as db:
            policy_result = await db.execute(
                select(Policy).where(col(Policy.ritm_number) == self.ritm_number)
            )
            policies = list(policy_result.scalars().all())

        # Group by (domain_uid, package_uid)
        packages_map: dict[tuple[str, str], PackageInfo] = {}
        for policy in policies:
            key = (policy.domain_uid, policy.package_uid)
            if key not in packages_map:
                packages_map[key] = PackageInfo(
                    domain_name=policy.domain_name,
                    domain_uid=policy.domain_uid,
                    package_name=policy.package_name,
                    package_uid=policy.package_uid,
                    policies=[],
                )
            packages_map[key].policies.append(policy)

        return list(packages_map.values())

    def _combine_evidence(self, evidence_list: list[EvidenceData]) -> dict[str, Any]:
        """Combine per-package evidence into single session_changes structure."""
        combined: dict[str, Any] = {
            "apply_sessions": {},
            "apply_session_trace": [],
            "domain_changes": {},
            "show_changes_requests": {},
            "errors": [],
        }

        for evidence in evidence_list:
            domain_name = evidence.domain_name or "SMC User"
            package_name = evidence.package_name

            # Merge domain_changes
            if evidence.session_changes:
                domain_changes = evidence.session_changes.get("domain_changes", {})
                combined["domain_changes"].update(domain_changes)

                # Merge apply_sessions
                apply_sessions = evidence.session_changes.get("apply_sessions", {})
                combined["apply_sessions"].update(apply_sessions)

                # Add to trace
                if evidence.session_uid:
                    combined["apply_session_trace"].append({
                        "domain": domain_name,
                        "package": package_name,
                        "session_uid": evidence.session_uid,
                        "sid": evidence.sid,
                    })

        return combined

    def _generate_evidence_artifacts(
        self, session_changes: dict[str, Any]
    ) -> tuple[bytes | None, str | None]:
        """Generate PDF and HTML from combined session_changes."""
        if not session_changes or not session_changes.get("domain_changes"):
            return None, None

        try:
            pdf_bytes = self.pdf_generator.generate_pdf(
                ritm_number=self.ritm_number,
                evidence_number=1,
                username=self.username,
                session_changes=session_changes,
            )

            html = self.pdf_generator.generate_html(
                ritm_number=self.ritm_number,
                evidence_number=1,
                username=self.username,
                session_changes=session_changes,
            )

            return pdf_bytes, html
        except Exception as e:
            self.logger.error(f"Failed to generate evidence: {e}", exc_info=True)
            return None, None

    async def _store_session_uids(self, evidence_list: list[EvidenceData]) -> None:
        """Store session UIDs in RITMSession table for evidence re-creation."""
        async with AsyncSession(engine) as db:
            for evidence in evidence_list:
                if evidence.session_uid:
                    db.add(
                        RITMSession(
                            ritm_number=self.ritm_number,
                            domain_name=evidence.domain_name,
                            domain_uid=evidence.domain_uid,
                            session_uid=evidence.session_uid,
                            sid=evidence.sid or "",
                            created_at=datetime.now(UTC),
                        )
                    )
            await db.commit()

    async def _store_evidence(self, session_changes: dict[str, Any]) -> None:
        """Store combined session_changes in RITM record."""
        async with AsyncSession(engine) as db:
            ritm_result = await db.execute(
                select(RITM).where(col(RITM.ritm_number) == self.ritm_number)
            )
            ritm = ritm_result.scalar_one_or_none()
            if ritm:
                ritm.session_changes_evidence1 = json.dumps(session_changes)
                await db.commit()

    async def _publish_session(self) -> None:
        """Publish changes with session name format: {ritm_number} {username} Created."""
        session_name = f"{self.ritm_number} {self.username} Created"

        # Get unique domains from packages
        packages = await self._group_by_package()
        domains = set(p.domain_name for p in packages)

        for domain_name in domains:
            try:
                result = await self.client.api_call(
                    mgmt_name=self.mgmt_name,
                    domain=domain_name,
                    command="publish",
                    payload={},
                )
                if result.success:
                    self.logger.info(
                        f"Published to domain '{domain_name}' "
                        f"with session name '{session_name}'"
                    )
                else:
                    self.logger.warning(
                        f"Publish to domain '{domain_name}' failed: "
                        f"{result.message or result.code}"
                    )
            except Exception as e:
                self.logger.error(
                    f"Publish to domain '{domain_name}' error: {e}",
                    exc_info=True,
                )
```

- [ ] **Step 2: Create basic tests**

Create `src/fa/tests/test_ritm_workflow_service.py`:

```python
"""Tests for RITMWorkflowService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from datetime import UTC, datetime

from fa.services.ritm_workflow_service import RITMWorkflowService
from fa.models import PackageResult, EvidenceData


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.api_call = AsyncMock()
    client.cache = MagicMock()
    client.get_mgmt_names = Mock(return_value=["test-mgmt"])
    return client


@pytest.mark.asyncio
async def test_combine_evidence_empty(mock_client):
    """Test _combine_evidence with empty list."""
    service = RITMWorkflowService(
        client=mock_client,
        ritm_number="RITM123",
        username="testuser",
    )
    result = service._combine_evidence([])
    assert result["domain_changes"] == {}
    assert result["apply_sessions"] == {}
    assert result["apply_session_trace"] == []


@pytest.mark.asyncio
async def test_combine_evidence_with_data(mock_client):
    """Test _combine_evidence merges multiple evidence items."""
    service = RITMWorkflowService(
        client=mock_client,
        ritm_number="RITM123",
        username="testuser",
    )

    evidence1 = EvidenceData(
        domain_name="Domain1",
        package_name="Package1",
        package_uid="p1-uid",
        domain_uid="d1-uid",
        session_changes={
            "domain_changes": {"Domain1": {"tasks": []}},
            "apply_sessions": {"Domain1": "sid1"},
        },
        session_uid="session-1",
        sid="sid1",
    )

    evidence2 = EvidenceData(
        domain_name="Domain2",
        package_name="Package2",
        package_uid="p2-uid",
        domain_uid="d2-uid",
        session_changes={
            "domain_changes": {"Domain2": {"tasks": []}},
            "apply_sessions": {"Domain2": "sid2"},
        },
        session_uid="session-2",
        sid="sid2",
    )

    result = service._combine_evidence([evidence1, evidence2])

    assert "Domain1" in result["domain_changes"]
    assert "Domain2" in result["domain_changes"]
    assert "Domain1" in result["apply_sessions"]
    assert "Domain2" in result["apply_sessions"]
    assert len(result["apply_session_trace"]) == 2
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest src/fa/tests/test_ritm_workflow_service.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/fa/services/ritm_workflow_service.py src/fa/tests/test_ritm_workflow_service.py
git commit -m "feat: add RITMWorkflowService orchestrator for Try & Verify"
```

---

## Task 4: Add /try-verify Endpoint

**Files:**

- Modify: `src/fa/routes/ritm_flow.py`

- [ ] **Step 1: Add imports and create endpoint**

Add to `src/fa/routes/ritm_flow.py` after the existing imports and before the first endpoint (around line 35):

```python
from ..models import (
    ApplyResponse,
    EvidenceResponse,
    MatchObjectsRequest,
    MatchObjectsResponse,
    MatchResult,
    PlanYamlResponse,
    RITMVerification,
    VerifyResponse,
    TryVerifyResponse,
    PackageResult,
)

from ..services.ritm_workflow_service import RITMWorkflowService
```

- [ ] **Step 2: Add the /try-verify endpoint**

Add the new endpoint to `src/fa/routes/ritm_flow.py` after the `/plan-yaml` endpoint (around line 290):

```python
@router.post("/ritm/{ritm_number}/try-verify")
async def try_verify_ritm(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> TryVerifyResponse:
    """Execute Try & Verify workflow with automatic rollback and disable.

    Workflow for each package:
    1. Verify policy (pre-check) - skip package on failure
    2. Create objects and rules - skip package on failure
    3. Verify policy again (post-creation)
    4. On verify failure: rollback rules, continue
    5. On verify success: capture evidence, disable rules

    After all packages:
    - Combine evidence into single PDF/HTML
    - Store session UIDs for evidence re-creation
    - Publish if any packages succeeded
    """
    async with AsyncSession(engine) as db:
        from ..models import RITM

        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            workflow = RITMWorkflowService(
                client=client,
                ritm_number=ritm_number,
                username=session.username,
            )
            result = await workflow.try_verify()
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in try_verify for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 3: Comment out old /apply and /verify endpoints**

In `src/fa/routes/ritm_flow.py`, find the `/apply` and `/verify` endpoints and comment them out (around lines 293 and 916):

```python
# DEPRECATED: Use /try-verify instead
# @router.post("/ritm/{ritm_number}/apply")
# async def apply_ritm(...):
#     ...

# DEPRECATED: Verification now internal to /try-verify
# @router.post("/ritm/{ritm_number}/verify")
# async def verify_ritm(...):
#     ...
```

- [ ] **Step 4: Update route tests**

Update `src/fa/tests/test_ritm_flow_routes.py` to add test for new endpoint:

```python
@pytest.mark.asyncio
async def test_try_verify_ritm_success(client, auth_cookies):
    """Test /try-verify endpoint with successful workflow."""
    # This test will need mocking of CPAIOPSClient and related services
    # For now, just verify the endpoint exists and returns 401 without auth

    response = client.post("/api/v1/ritm/RITM1234567/try-verify")
    assert response.status_code == 401  # Unauthorized
```

- [ ] **Step 5: Run type check**

Run: `uv run mypy src/fa/routes/ritm_flow.py`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add src/fa/routes/ritm_flow.py src/fa/tests/test_ritm_flow_routes.py
git commit -m "feat: add /try-verify endpoint, deprecate /apply and /verify"
```

---

## Task 5: Add /recreate-evidence Endpoint

**Files:**

- Modify: `src/fa/routes/ritm_flow.py`

- [ ] **Step 1: Add the /recreate-evidence endpoint**

Add to `src/fa/routes/ritm_flow.py` after the /try-verify endpoint:

```python
@router.post("/ritm/{ritm_number}/recreate-evidence")
async def recreate_evidence(
    ritm_number: str,
    session: SessionData = Depends(get_session_data),
) -> EvidenceResponse:
    """Re-generate evidence from stored session UIDs.

    Fetches fresh show-changes from Check Point to capture any manual changes
    made after the original Try & Verify.
    """
    from ..models import RITM, RITMSession

    async with AsyncSession(engine) as db:
        # Get RITM
        ritm_result = await db.execute(select(RITM).where(col(RITM.ritm_number) == ritm_number))
        ritm = ritm_result.scalar_one_or_none()
        if not ritm:
            raise HTTPException(status_code=404, detail="RITM not found")

        # Get stored session UIDs for this RITM
        sessions_result = await db.execute(
            select(RITMSession).where(col(RITMSession.ritm_number) == ritm_number)
        )
        ritm_sessions = sessions_result.scalars().all()

    if not ritm_sessions:
        raise HTTPException(
            status_code=400,
            detail="No session UIDs found for this RITM. Run Try & Verify first."
        )

    try:
        async with CPAIOPSClient(
            engine=engine,
            username=session.username,
            password=session.password,
            mgmt_ip=settings.api_mgmt,
        ) as client:
            mgmt_name = client.get_mgmt_names()[0]
            pdf_generator = SessionChangesPDFGenerator()

            # Combine fresh show-changes from all stored sessions
            combined_session_changes: dict[str, Any] = {
                "apply_sessions": {},
                "apply_session_trace": [],
                "domain_changes": {},
                "show_changes_requests": {},
                "errors": [],
            }

            for ritm_session in ritm_sessions:
                # Call show-changes with stored session UID
                sc_payload: dict[str, Any] = {}
                if ritm_session.session_uid:
                    sc_payload["to-session"] = ritm_session.session_uid

                sc_result = await client.api_call(
                    mgmt_name=mgmt_name,
                    domain=ritm_session.domain_name,
                    command="show-changes",
                    details_level="full",
                    payload=sc_payload,
                )

                if sc_result.success and sc_result.data:
                    domain_data = sc_result.data
                    combined_session_changes["domain_changes"].update(
                        domain_data.get("domain_changes", {})
                    )
                    combined_session_changes["apply_sessions"].update(
                        domain_data.get("apply_sessions", {})
                    )

            # Generate PDF and HTML
            pdf_bytes = pdf_generator.generate_pdf(
                ritm_number=ritm_number,
                evidence_number=1,
                username=session.username,
                session_changes=combined_session_changes,
            )

            html = pdf_generator.generate_html(
                ritm_number=ritm_number,
                evidence_number=1,
                username=session.username,
                session_changes=combined_session_changes,
            )

            # Update stored evidence
            async with AsyncSession(engine) as db:
                ritm_result = await db.execute(
                    select(RITM).where(col(RITM.ritm_number) == ritm_number)
                )
                ritm = ritm_result.scalar_one_or_none()
                if ritm:
                    ritm.session_changes_evidence1 = json.dumps(combined_session_changes)
                    await db.commit()

            return EvidenceResponse(
                html=html,
                yaml="",  # Not applicable for re-created evidence
                changes=combined_session_changes.get("domain_changes", {}),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in recreate_evidence for RITM {ritm_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 2: Run type check**

Run: `uv run mypy src/fa/routes/ritm_flow.py`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add src/fa/routes/ritm_flow.py
git commit -m "feat: add /recreate-evidence endpoint for fresh evidence generation"
```

---

## Task 6: Update Frontend Types

**Files:**

- Modify: `webui/src/types.ts`

- [ ] **Step 1: Add new TypeScript types**

Add to `webui/src/types.ts` after the existing type definitions:

```typescript
export interface PackageResult {
  package: string;
  status: "success" | "skipped" | "create_failed" | "verify_failed";
  rules_created: number;
  objects_created: number;
  errors: string[];
}

export interface TryVerifyResponse {
  results: PackageResult[];
  evidence_pdf: string | null;  // base64 encoded
  evidence_html: string | null;
  published: boolean;
  session_changes: Record<string, unknown> | null;
}

export interface EvidenceResponse {
  html: string;
  yaml: string;
  changes: Record<string, unknown>;
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/src/types.ts
git commit -m "feat: add TryVerifyResponse and PackageResult types"
```

---

## Task 7: Update API Client

**Files:**

- Modify: `webui/src/api/endpoints.ts`

- [ ] **Step 1: Add new API methods**

Add to `endpoints.ts` in the ritmApi object:

```typescript
// In the ritmApi object, add:
async tryVerifyRitm(ritmNumber: string): Promise<TryVerifyResponse> {
  const response = await this.api.post<TryVerifyResponse>(
    `/ritm/${ritmNumber}/try-verify`
  );
  return response.data;
}

async recreateEvidence(ritmNumber: string): Promise<EvidenceResponse> {
  const response = await this.api.post<EvidenceResponse>(
    `/ritm/${ritmNumber}/recreate-evidence`
  );
  return response.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/src/api/endpoints.ts
git commit -m "feat: add tryVerifyRitm and recreateEvidence API methods"
```

---

## Task 8: Update RitmEdit.tsx Workflow

**Files:**

- Modify: `webui/src/pages/RitmEdit.tsx`

- [ ] **Step 1: Update workflow step type and state**

Find the `WorkflowStep` type definition and update it:

```typescript
// Change from:
// type WorkflowStep = 'idle' | 'planned' | 'applied' | 'verified';
// To:
type WorkflowStep = 'idle' | 'planned' | 'verified';
```

- [ ] **Step 2: Add new state variables**

Add to the component state (after `verifyResult` state):

```typescript
const [tryVerifying, setTryVerifying] = useState(false);
const [tryVerifyResult, setTryVerifyResult] = useState<TryVerifyResponse | null>(null);
const [canRecreateEvidence, setCanRecreateEvidence] = useState(false);
```

- [ ] **Step 3: Replace handleApply with handleTryVerify**

Replace the entire `handleApply` function with:

```typescript
const handleTryVerify = async () => {
  setTryVerifying(true);
  setVerificationErrors([]);
  setEvidenceHtml(null);
  setShowEvidence(false);
  setTryVerifyResult(null);
  addWorkflowLog('Try & Verify started...');
  const hide = message.loading('Try & Verify in progress...', 0);
  try {
    const response = await ritmApi.tryVerifyRitm(ritmNumber || '');
    setTryVerifyResult(response);
    setWorkflowStep('verified');

    // Log per-package results
    response.results.forEach(r => {
      const statusMsg = {
        success: `✓ ${r.package}: SUCCESS (${r.rules_created} rules, ${r.objects_created} objects)`,
        skipped: `⊘ ${r.package}: SKIPPED (pre-verify failed)`,
        create_failed: `✗ ${r.package}: CREATE FAILED`,
        verify_failed: `✗ ${r.package}: VERIFY FAILED (rules rolled back)`,
      }[r.status] || `${r.package}: ${r.status}`;

      addWorkflowLog(statusMsg);

      if (r.errors.length > 0) {
        r.errors.forEach(err => addWorkflowLog(`  Error: ${err}`));
      }
    });

    if (response.published) {
      addWorkflowLog('Changes published successfully');
    }

    if (response.evidence_html) {
      setSessionHtml(response.evidence_html);
      setCanRecreateEvidence(true);
    }

    if (response.results.some(r => r.status === 'success')) {
      message.success({
        content: `Try & Verify complete. ${response.results.filter(r => r.status === 'success').length} package(s) succeeded.`,
        key: 'wf',
        duration: 5,
      });
    } else {
      message.warning({
        content: 'Try & Verify failed. All packages were skipped or had errors.',
        key: 'wf',
        duration: 5,
      });
    }
  } catch (error: any) {
    const msg = extractErrorMsg(error, 'Try & Verify failed');
    setVerificationErrors(prev => [...prev, msg]);
    addWorkflowLog(`Try & Verify failed: ${msg}`);
    message.error({ content: 'Try & Verify failed.', key: 'wf', duration: 5 });
  } finally {
    hide();
    setTryVerifying(false);
  }
};
```

- [ ] **Step 4: Add handleRecreateEvidence function**

Add after the `handleResetWorkflow` function:

```typescript
const handleRecreateEvidence = async () => {
  if (!ritmNumber) return;

  addWorkflowLog('Re-creating evidence from current session state...');
  const hide = message.loading('Re-creating evidence...', 0);
  try {
    const response = await ritmApi.recreateEvidence(ritmNumber);
    setSessionHtml(response.html);
    setShowSessionHtml(true);
    addWorkflowLog('Evidence re-created successfully');
    message.success('Evidence re-created from current Check Point state');
  } catch (error: any) {
    message.error(error.response?.data?.detail || 'Failed to re-create evidence');
  } finally {
    hide();
  }
};
```

- [ ] **Step 5: Update workflow steps display**

Find the `<Steps>` component and update the items:

```typescript
<Steps
  current={
    workflowStep === 'idle' ? 0
    : workflowStep === 'planned' ? 1
    : 2
  }
  size="small"
  style={{ marginBottom: 16 }}
  items={[
    { title: 'Plan' },
    { title: 'Try & Verify' },
  ]}
/>
```

- [ ] **Step 6: Update workflow action buttons**

Replace the workflow action buttons section with:

```typescript
{workflowStep === 'idle' && (
  <Button
    type="primary"
    onClick={handleGeneratePlan}
    disabled={planning || saving || rules.length === 0}
    loading={planning}
    block
  >
    Generate YAML Plan
  </Button>
)}

{workflowStep === 'planned' && (
  <Space style={{ width: '100%' }} direction="vertical">
    <Text type="secondary">
      Review the planned changes above, then run Try & Verify.
    </Text>
    <Space>
      <Button
        type="primary"
        onClick={handleTryVerify}
        disabled={tryVerifying || saving}
        loading={tryVerifying}
      >
        Try & Verify
      </Button>
      <Button onClick={handleResetWorkflow}>Re-plan</Button>
    </Space>
  </Space>
)}

{workflowStep === 'verified' && (
  <Space style={{ width: '100%' }} direction="vertical">
    {tryVerifyResult && (
      <Alert
        type={tryVerifyResult.results.some(r => r.status === 'success') ? 'success' : 'warning'}
        message={
          tryVerifyResult.results.some(r => r.status === 'success')
            ? `Try & Verify complete - ${tryVerifyResult.results.filter(r => r.status === 'success').length} package(s) succeeded`
            : 'Try & Verify completed with errors'
        }
        showIcon
      />
    )}

    {/* Show per-package results */}
    {tryVerifyResult && tryVerifyResult.results.map(r => (
      <div key={r.package} style={{ fontSize: '0.9em' }}>
        <Text type={
          r.status === 'success' ? 'success' :
          r.status === 'skipped' ? 'secondary' :
          'danger'
        }>
          {r.package}: {r.status.toUpperCase()}
          {r.rules_created > 0 && ` (${r.rules_created} rules, ${r.objects_created} objects)`}
        </Text>
        {r.errors.length > 0 && (
          <ul style={{ margin: '4px 0 0 20', padding: 0 }}>
            {r.errors.map((err, i) => (
              <li key={i}><Text type="danger">{err}</Text></li>
            ))}
          </ul>
        )}
      </div>
    ))}

    {canRecreateEvidence && (
      <Button size="small" onClick={handleRecreateEvidence}>
        Re-create Evidence
      </Button>
    )}

    <Button size="small" onClick={handleResetWorkflow}>Reset workflow</Button>
  </Space>
)}
```

- [ ] **Step 7: Remove old Verify result card**

Remove or comment out the `{verifyResult && (` block that shows verification results (around line 1183).

- [ ] **Step 8: Remove old applyResult card handling**

Update the `{applyResult && (` block to use `tryVerifyResult` instead (around line 1091). Either remove it or update to show tryVerify results.

- [ ] **Step 9: Build and check for type errors**

Run: `cd webui && npm run build`
Expected: No type errors

- [ ] **Step 10: Commit**

```bash
git add webui/src/pages/RitmEdit.tsx
git commit -m "feat: update RitmEdit to 2-step workflow with Try & Verify"
```

---

## Task 9: Update CONTEXT.md

**Files:**

- Modify: `docs/CONTEXT.md`

- [ ] **Step 1: Add reference to the new feature**

Add to `docs/CONTEXT.md` in the appropriate section:

```markdown
## RITM Workflow

- **Design:** [Try & Verify Workflow Design](internal/features/260422-ritm-try-verify-workflow/design.md)
- **Implementation:** [Try & Verify Implementation Plan](../superpowers/plans/2026-04-22-ritm-try-verify-workflow.md)
- **Raw Logs:** `docs/_AI_/260422-ritm-try-verify-workflow/`
```

- [ ] **Step 2: Commit**

```bash
git add docs/CONTEXT.md
git commit -m "docs: add RITM Try & Verify workflow reference"
```

---

## Task 10: Integration Testing

**Files:**

- No file creation - manual testing

- [ ] **Step 1: Test database schema**

Delete cache.db and let it recreate:

```bash
rm -f _tmp/cache.db
# Start the application and verify schema is created correctly
```

- [ ] **Step 2: Test full workflow**

1. Create a new RITM with multiple rules across different domains/packages
2. Generate YAML Plan
3. Run Try & Verify
4. Verify:
   - Evidence PDF is generated
   - Evidence HTML shows created rules as disabled
   - Session UIDs are stored
   - Publish is called
5. Test "Re-create Evidence" button
6. Submit for approval

- [ ] **Step 3: Test rollback scenarios**

1. Create RITM with a rule that will fail verification
2. Run Try & Verify
3. Verify:
   - Failed package shows "verify_failed" status
   - Rules were rolled back (check Check Point)
   - Other packages succeeded if applicable

- [ ] **Step 4: Test pre-verify skip**

1. Create RITM with a package that has existing policy errors
2. Run Try & Verify
3. Verify:
   - Package shows "skipped" status
   - No objects/rules created for that package

- [ ] **Step 5: Document test results**

Create a brief test report in `docs/_AI_/260422-ritm-try-verify-workflow/test-results.md`:

```markdown
# Test Results - RITM Try & Verify Workflow

Date: YYYY-MM-DD
Tester: [Your Name]

## Test Scenarios

### 1. Successful Try & Verify
- Status: PASS/FAIL
- Notes: [...]

### 2. Rollback on Verification Failure
- Status: PASS/FAIL
- Notes: [...]

### 3. Pre-verify Skip
- Status: PASS/FAIL
- Notes: [...]

### 4. Evidence Re-creation
- Status: PASS/FAIL
- Notes: [...]

### 5. Multi-domain Processing
- Status: PASS/FAIL
- Notes: [...]
```

- [ ] **Step 6: Commit test results**

```bash
git add docs/_AI_/260422-ritm-try-verify-workflow/test-results.md
git commit -m "test: document RITM Try & Verify integration test results"
```

---

## Final Review

- [ ] **Self-Review Checklist**

1. **Spec Coverage:**
   - [ ] Per-package workflow (verify → create → verify → rollback/disable) ✓
   - [ ] Evidence generation per package ✓
   - [ ] Combined evidence PDF/HTML ✓
   - [ ] Session UID persistence ✓
   - [ ] Evidence re-creation endpoint ✓
   - [ ] 2-step workflow in frontend ✓
   - [ ] Rollback on verification failure ✓
   - [ ] Disable rules after success ✓
   - [ ] Publish after successful verification ✓

2. **Placeholder Scan:**
   - [ ] No TBD, TODO, or "implement later" in code
   - [ ] All steps have actual code, not descriptions
   - [ ] All file paths are exact
   - [ ] All imports are included

3. **Type Consistency:**
   - [ ] PackageResult status values match between backend and frontend
   - [ ] TryVerifyResponse structure matches
   - [ ] Method names are consistent (try_verify, tryVerifyRitm, handleTryVerify)

4. **Dependencies:**
   - [ ] All required imports are included
   - [ ] Existing services (ObjectMatcher, PolicyVerifier, etc.) are reused
   - [ ] No circular dependencies

---

## Completion

After all tasks are complete and tested:

1. Run full test suite: `uv run pytest`
2. Run type check: `uv run mypy src/fa/`
3. Build frontend: `cd webui && npm run build`
4. Create final PR with description referencing this plan

**Estimated effort:** 8-12 hours for implementation, 2-4 hours for testing
