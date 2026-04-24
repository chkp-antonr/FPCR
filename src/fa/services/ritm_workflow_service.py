"""RITM Try & Verify orchestrator service."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from cpaiops import CPAIOPSClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ..db import engine
from ..models import (
    RITM,
    CachedSection,
    EvidenceData,
    PackageResult,
    Policy,
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
            f"Processing {len(packages)} unique package(s)"
        )

        results: list[PackageResult] = []
        all_evidence: list[EvidenceData] = []
        any_success = False

        for pkg_info in packages:
            self.logger.info(
                f"Processing package: {pkg_info.package_name} (domain: {pkg_info.domain_name})"
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

        # Build UID-to-name mapping for section resolution in evidence
        section_uid_to_name = await self._build_section_uid_mapping()

        evidence_pdf, evidence_html = self._generate_evidence_artifacts(
            combined_session_changes, section_uid_to_name
        )

        # Base64 encode PDF bytes for JSON serialization
        import base64

        evidence_pdf_b64 = base64.b64encode(evidence_pdf).decode("utf-8") if evidence_pdf else None

        # Store session UIDs and get the primary session UID
        session_uid = await self._store_session_uids(all_evidence)

        # Store evidence in RITM with session UID
        await self._store_evidence(combined_session_changes, session_uid)

        # Publish if any packages succeeded
        published = False
        if any_success:
            await self._publish_session()
            published = True

        return TryVerifyResponse(
            results=results,
            evidence_pdf=evidence_pdf_b64,
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

    async def _store_session_uids(self, evidence_list: list[EvidenceData]) -> str | None:
        """Store session UIDs in RITMSession table for evidence re-creation.

        Returns:
            The first session UID found (for storing in RITM record).
        """
        first_session_uid: str | None = None
        async with AsyncSession(engine) as db:
            try:
                # Delete old sessions for this RITM to avoid accumulation
                from sqlalchemy import delete

                await db.execute(
                    delete(RITMSession).where(col(RITMSession.ritm_number) == self.ritm_number)
                )

                # Add new sessions
                for evidence in evidence_list:
                    if evidence.session_uid:
                        if first_session_uid is None:
                            first_session_uid = evidence.session_uid
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
            except Exception as e:
                self.logger.error(f"Failed to store session UIDs: {e}", exc_info=True)
        return first_session_uid

    async def _store_evidence(
        self, session_changes: dict[str, Any], session_uid: str | None = None
    ) -> None:
        """Store combined session_changes in RITM record."""
        async with AsyncSession(engine) as db:
            try:
                ritm_result = await db.execute(
                    select(RITM).where(col(RITM.ritm_number) == self.ritm_number)
                )
                ritm = ritm_result.scalar_one_or_none()
                if ritm:
                    ritm.session_changes_evidence1 = json.dumps(session_changes)
                    ritm.try_verify_session_uid = session_uid
                    await db.commit()
                else:
                    self.logger.warning(f"RITM {self.ritm_number} not found for evidence storage")
            except Exception as e:
                self.logger.error(f"Failed to store evidence: {e}", exc_info=True)

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
