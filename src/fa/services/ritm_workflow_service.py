"""RITM Try & Verify orchestrator service."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from cpaiops import CPAIOPSClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ..db import engine
from ..models import (
    CachedSection,
    EvidenceData,
    GroupedVerifyResponse,
    PackageResult,
    PackageVerifyResult,
    Policy,
    RITMCreatedRule,
    RITMEvidenceSession,
    RITMPackageAttempt,
    RITMPackageAttemptState,
    TryVerifyResponse,
)
from ..services.session_changes_pdf import SessionChangesPDFGenerator
from .package_workflow import PackageInfo, PackageWorkflowService
from .policy_verifier import PackageVerifyInput, PolicyVerifier

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
        self.mgmt_name = client.get_mgmt_names()[0] if client is not None else ""
        self.logger = logging.getLogger(__name__)
        self.pdf_generator = SessionChangesPDFGenerator()

    async def try_verify(
        self,
        force_continue: bool = False,
        skip_package_uids: set[str] | None = None,
    ) -> TryVerifyResponse:
        """Execute full Try & Verify workflow.

        Args:
            force_continue: When True, packages that fail pre-check are recorded
                as PRECHECK_FAILED_SKIPPED and workflow continues for the rest.
                When False (default), any pre-check failure aborts the whole run.
            skip_package_uids: Optional explicit set of package UIDs to skip
                (e.g. pre-populated from a prior /verify-policy call).
        """
        packages = await self._group_by_package()
        if not packages:
            self.logger.warning(f"No packages found for RITM {self.ritm_number}")
            return TryVerifyResponse(
                results=[],
                evidence_pdf=None,
                evidence_html=None,
                published=False,
                session_changes=None,
            )

        self.logger.info(
            f"Try & Verify for RITM {self.ritm_number}: "
            f"Processing {len(packages)} unique package(s) "
            f"(force_continue={force_continue})"
        )

        # Compute attempt number ONCE – shared across all packages in this run
        attempt = await self._next_attempt()
        session_type = "initial" if attempt == 1 else "correction"

        results: list[PackageResult] = []
        all_evidence: list[EvidenceData] = []
        any_success = False

        for pkg_info in packages:
            self.logger.info(
                f"Processing package: {pkg_info.package_name} (domain: {pkg_info.domain_name})"
            )

            # Honour explicit skip list (e.g. from prior /verify-policy results)
            if skip_package_uids and pkg_info.package_uid in skip_package_uids:
                await self._record_package_state(
                    attempt,
                    pkg_info,
                    RITMPackageAttemptState.PRECHECK_FAILED_SKIPPED,
                    "Explicitly skipped via skip_package_uids",
                )
                results.append(
                    PackageResult(
                        domain=pkg_info.domain_name,
                        package=pkg_info.package_name,
                        status="skipped",
                        errors=["Skipped via explicit skip list"],
                    )
                )
                continue

            pkg_workflow = PackageWorkflowService(
                client=self.client,
                package_info=pkg_info,
                ritm_number=self.ritm_number,
                mgmt_name=self.mgmt_name,
            )

            # ── Pre-check ──────────────────────────────────────────────────
            verify1 = await pkg_workflow.verify_first()
            if not verify1.success:
                await self._record_package_state(
                    attempt,
                    pkg_info,
                    RITMPackageAttemptState.PRECHECK_FAILED_SKIPPED,
                    "; ".join(verify1.errors),
                )
                results.append(
                    PackageResult(
                        domain=pkg_info.domain_name,
                        package=pkg_info.package_name,
                        status="skipped",
                        errors=verify1.errors,
                    )
                )
                if not force_continue:
                    # Abort the whole run – caller must retry with force_continue=True
                    self.logger.warning(
                        f"Pre-check failed for {pkg_info.package_name}; "
                        "aborting (force_continue=False)"
                    )
                    return TryVerifyResponse(
                        results=results,
                        evidence_pdf=None,
                        evidence_html=None,
                        published=False,
                        session_changes=None,
                    )
                continue

            await self._record_package_state(
                attempt, pkg_info, RITMPackageAttemptState.PRECHECK_PASSED
            )

            # ── Create objects and rules ────────────────────────────────────
            create_result = await pkg_workflow.create_objects_and_rules()
            if create_result.errors:
                results.append(
                    PackageResult(
                        domain=pkg_info.domain_name,
                        package=pkg_info.package_name,
                        status="create_failed",
                        objects_created=create_result.objects_created,
                        rules_created=create_result.rules_created,
                        errors=create_result.errors,
                    )
                )
                continue

            await self._record_package_state(
                attempt, pkg_info, RITMPackageAttemptState.CREATE_APPLIED
            )

            # ── Post-create verification ────────────────────────────────────
            verify2 = await pkg_workflow.verify_again()
            if not verify2.success:
                # Delete the created rules; keep objects in session
                await pkg_workflow.rollback_rules(create_result.created_rule_uids)

                # Re-verify to see if rule deletion was sufficient
                verify3 = await pkg_workflow.verify_post_delete()
                if not verify3.success:
                    # Still failing – discard entire session to clean up objects too
                    await pkg_workflow.discard_session()

                await self._record_package_state(
                    attempt,
                    pkg_info,
                    RITMPackageAttemptState.POSTCHECK_FAILED_RULES_DELETED,
                    "; ".join(verify2.errors),
                )
                results.append(
                    PackageResult(
                        domain=pkg_info.domain_name,
                        package=pkg_info.package_name,
                        status="verify_failed",
                        objects_created=create_result.objects_created,
                        rules_created=create_result.rules_created,
                        errors=verify2.errors,
                    )
                )
                continue

            # ── Success path ────────────────────────────────────────────────
            await pkg_workflow.disable_rules(create_result.created_rule_uids)
            await self._record_package_state(
                attempt,
                pkg_info,
                RITMPackageAttemptState.VERIFIED_PENDING_APPROVAL_DISABLED,
            )

            evidence = await pkg_workflow.capture_evidence()
            all_evidence.append(evidence)

            await self._store_evidence_session(evidence, attempt, session_type)
            await self._store_created_rules(
                create_result.created_rule_uids,
                pkg_info.domain_uid,
                pkg_info.package_uid,
            )

            results.append(
                PackageResult(
                    domain=pkg_info.domain_name,
                    package=pkg_info.package_name,
                    status="success",
                    objects_created=create_result.objects_created,
                    rules_created=create_result.rules_created,
                )
            )
            any_success = True

        combined_session_changes = self._combine_evidence(all_evidence)
        section_uid_to_name = await self._build_section_uid_mapping()
        evidence_pdf, evidence_html = self._generate_evidence_artifacts(
            combined_session_changes, section_uid_to_name
        )

        import base64

        evidence_pdf_b64 = base64.b64encode(evidence_pdf).decode("utf-8") if evidence_pdf else None

        return TryVerifyResponse(
            results=results,
            evidence_pdf=evidence_pdf_b64,
            evidence_html=evidence_html,
            published=any_success,
            session_changes=combined_session_changes,
        )

    async def verify_policy_grouped(self, packages: list[PackageInfo]) -> GroupedVerifyResponse:
        """Run pre-check verify-policy for every (domain, package) pair.

        Used by the standalone /verify-policy endpoint so the user can review
        failures before deciding to force_continue.
        """
        verifier = PolicyVerifier(self.client)
        inputs = [
            PackageVerifyInput(
                domain_name=p.domain_name,
                domain_uid=p.domain_uid,
                package_name=p.package_name,
                package_uid=p.package_uid,
            )
            for p in packages
        ]
        raw = await verifier.verify_policy_grouped(inputs)

        pkg_results: list[PackageVerifyResult] = [
            PackageVerifyResult(
                domain_name=pkg.domain_name,
                domain_uid=pkg.domain_uid,
                package_name=pkg.package_name,
                package_uid=pkg.package_uid,
                success=res.success,
                errors=res.errors,
            )
            for pkg, res in raw
        ]
        all_passed = all(r.success for r in pkg_results)
        return GroupedVerifyResponse(all_passed=all_passed, results=pkg_results)

    async def _next_attempt(self) -> int:
        """Compute next attempt number – MAX(attempt)+1 for this RITM, or 1 if none."""
        async with AsyncSession(engine) as db:
            result = await db.execute(
                select(func.max(RITMPackageAttempt.attempt)).where(
                    col(RITMPackageAttempt.ritm_number) == self.ritm_number
                )
            )
            max_val = result.scalar_one_or_none()
            return (max_val or 0) + 1

    async def _record_package_state(
        self,
        attempt: int,
        pkg_info: PackageInfo,
        state: RITMPackageAttemptState,
        error_message: str | None = None,
    ) -> None:
        """Persist a per-package state transition row in ritm_package_attempt."""
        async with AsyncSession(engine) as db:
            db.add(
                RITMPackageAttempt(
                    ritm_number=self.ritm_number,
                    attempt=attempt,
                    domain_uid=pkg_info.domain_uid,
                    domain_name=pkg_info.domain_name,
                    package_uid=pkg_info.package_uid,
                    package_name=pkg_info.package_name,
                    state=state,
                    error_message=error_message,
                    created_at=datetime.now(UTC),
                )
            )
            await db.commit()

    async def _store_evidence_session(
        self, evidence: EvidenceData, attempt: int, session_type: str
    ) -> None:
        """Persist one package's evidence as a row in ritm_evidence_sessions."""
        async with AsyncSession(engine) as db:
            db.add(
                RITMEvidenceSession(
                    ritm_number=self.ritm_number,
                    attempt=attempt,
                    domain_name=evidence.domain_name,
                    domain_uid=evidence.domain_uid,
                    package_name=evidence.package_name,
                    package_uid=evidence.package_uid,
                    session_uid=evidence.session_uid,
                    sid=evidence.sid,
                    session_type=session_type,
                    session_changes=json.dumps(evidence.session_changes)
                    if evidence.session_changes
                    else None,
                    created_at=datetime.now(UTC),
                )
            )
            await db.commit()

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

            # Store the entire show-changes response under domain name
            if evidence.session_changes:
                # Store the raw show-changes response data under domain name
                if domain_name not in combined["domain_changes"]:
                    combined["domain_changes"][domain_name] = {}
                # Merge with existing data for this domain
                combined["domain_changes"][domain_name].update(evidence.session_changes)

                # Add to trace
                if evidence.session_uid:
                    combined["apply_session_trace"].append(
                        {
                            "domain": domain_name,
                            "package": package_name,
                            "session_uid": evidence.session_uid,
                            "sid": evidence.sid,
                        }
                    )

        return combined

    def _generate_evidence_artifacts(
        self, session_changes: dict[str, Any], section_uid_to_name: dict[str, str] | None = None
    ) -> tuple[bytes | None, str | None]:
        """Generate PDF and HTML from combined session_changes.

        Args:
            session_changes: Combined session changes from all packages
            section_uid_to_name: Optional UID-to-name mapping for section resolution
        """
        if not session_changes or not session_changes.get("domain_changes"):
            return None, None

        if section_uid_to_name is None:
            section_uid_to_name = {}

        try:
            pdf_bytes = self.pdf_generator.generate_pdf(
                ritm_number=self.ritm_number,
                evidence_number=1,
                username=self.username,
                session_changes=session_changes,
                section_uid_to_name=section_uid_to_name,
            )

            html = self.pdf_generator.generate_html(
                ritm_number=self.ritm_number,
                evidence_number=1,
                username=self.username,
                session_changes=session_changes,
                section_uid_to_name=section_uid_to_name,
            )

            return pdf_bytes, html
        except Exception as e:
            self.logger.error(f"Failed to generate evidence: {e}", exc_info=True)
            return None, None

    async def _publish_session(self) -> None:
        """Publish changes with session name format: {ritm_number} {username} Created."""
        session_name = f"{self.ritm_number} {self.username} Created"

        # Get unique domains from packages
        packages = await self._group_by_package()
        domains = {p.domain_name for p in packages}

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
                        f"Published to domain '{domain_name}' with session name '{session_name}'"
                    )
                else:
                    self.logger.warning(
                        f"Publish to domain '{domain_name}' failed: {result.message or result.code}"
                    )
            except Exception as e:
                self.logger.error(
                    f"Publish to domain '{domain_name}' error: {e}",
                    exc_info=True,
                )

    async def _store_created_rules(
        self, rule_uids: list[str], domain_uid: str, package_uid: str
    ) -> None:
        """Persist created rule UIDs to ritm_created_rules for use during approval."""
        if not rule_uids:
            return
        async with AsyncSession(engine) as db:
            for uid in rule_uids:
                db.add(
                    RITMCreatedRule(
                        ritm_number=self.ritm_number,
                        rule_uid=uid,
                        package_uid=package_uid,
                        domain_uid=domain_uid,
                        verification_status="verified",
                        disabled=False,
                        created_at=datetime.now(UTC),
                    )
                )
            await db.commit()

    async def _build_section_uid_mapping(self) -> dict[str, str]:
        """Build mapping of section/layer UIDs to human-readable names.

        Returns:
            Dictionary mapping UIDs to names for both cached sections and access layers.
        """
        section_uid_to_name: dict[str, str] = {}

        async with AsyncSession(engine) as db:
            # 1. Fetch cached sections from database
            sections_result = await db.execute(select(CachedSection))
            sections = sections_result.scalars().all()
            for s in sections:
                section_uid_to_name[s.uid] = s.name

        # 2. Fetch access layers from API for each domain we're working with
        packages = await self._group_by_package()
        unique_domains = {p.domain_name for p in packages}

        for domain_name in unique_domains:
            try:
                layers_result = await self.client.api_call(
                    mgmt_name=self.mgmt_name,
                    domain=domain_name,
                    command="show-access-layers",
                    payload={},
                )
                if layers_result.success and layers_result.data:
                    for layer in layers_result.data.get("access-layers", []):
                        layer_uid = layer.get("uid")
                        layer_name = layer.get("name")
                        if layer_uid and layer_name:
                            section_uid_to_name[layer_uid] = layer_name
                            self.logger.debug(
                                f"Loaded access layer: {layer_name} ({layer_uid[:8]}...)"
                            )
            except Exception as e:
                self.logger.warning(f"Failed to fetch access layers for {domain_name}: {e}")

        self.logger.info(f"Built UID-to-name mapping: {len(section_uid_to_name)} entries")
        return section_uid_to_name
