"""Per-package workflow service for Try & Verify operation."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from cpaiops import CPAIOPSClient

from cpcrud.rule_manager import CheckPointRuleManager

from ..models import CreateResult, EvidenceData
from .object_matcher import ObjectMatcher
from .policy_verifier import PolicyVerifier, VerificationResult

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
        self.current_session_uid: str | None = None

    async def _update_current_session_uid(self) -> None:
        """Get and store the current session UID from Check Point API."""
        try:
            result = await self.client.api_call(
                mgmt_name=self.mgmt_name,
                domain=self.info.domain_name,
                command="show-session",
                payload={},
            )
            if result.success and result.data:
                # The session UID is typically in the "uid" field of the response
                self.current_session_uid = result.data.get("uid") or result.data.get("session-uid")
                self.logger.info(
                    f"[{self.info.package_name}] Current session UID: {self.current_session_uid}"
                )
            else:
                self.logger.warning(
                    f"[{self.info.package_name}] Failed to get current session UID: "
                    f"{result.message or result.code}"
                )
        except Exception as e:
            self.logger.warning(f"[{self.info.package_name}] Error getting session UID: {e}")

    async def verify_first(self) -> VerificationResult:
        """Pre-creation verification.

        Returns:
            VerificationResult with success=True to proceed, False to skip package.
        """
        verifier = PolicyVerifier(self.client)
        result = await verifier.verify_policy(
            domain_name=self.info.domain_name,
            package_name=self.info.package_name,
        )
        status = "PASS" if result.success else "FAIL"
        self.logger.info(f"[{self.info.package_name}] Step: verify_first | Status: {status}")
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
                f"Layer lookup error for package '{self.info.package_name}': no access layer found"
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
            source_names = [r.get("object_name") or r.get("input", "") for r in source_objs]
            dest_names = [r.get("object_name") or r.get("input", "") for r in dest_objs]

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

        # Get current session UID after changes are made
        await self._update_current_session_uid()

        return CreateResult(
            objects_created=len(created_object_uids),
            rules_created=len(created_rule_uids),
            created_rule_uids=created_rule_uids,
            created_object_uids=created_object_uids,
            errors=errors,
        )

    async def verify_again(self) -> VerificationResult:
        """Post-creation verification.

        Returns:
            VerificationResult with success to keep rules, False to trigger rollback.
        """
        verifier = PolicyVerifier(self.client)
        result = await verifier.verify_policy(
            domain_name=self.info.domain_name,
            package_name=self.info.package_name,
        )
        status = "PASS" if result.success else "FAIL"
        self.logger.info(f"[{self.info.package_name}] Step: verify_again | Status: {status}")
        return result

    async def rollback_rules(self, rule_uids: list[str]) -> None:
        """Delete newly created rules when verification fails."""
        rule_mgr = CheckPointRuleManager(self.client)
        for rule_uid in rule_uids:
            try:
                await rule_mgr.delete(
                    mgmt_name=self.mgmt_name,
                    domain=self.info.domain_name,
                    rule_type="access-rule",
                    key={"uid": rule_uid},
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to rollback rule {rule_uid}: {e}",
                    exc_info=True,
                )
        self.logger.warning(
            f"[{self.info.package_name}] Step: rollback_rules | Rolled back {len(rule_uids)} rules"
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
            f"[{self.info.package_name}] Step: disable_rules | Disabled {len(rule_uids)} rules"
        )

    async def discard_session(self) -> None:
        """Discard all uncommitted changes in the current domain session.

        Called after a post-create verify failure when rules have been deleted
        but the session still contains orphaned objects that cannot be cleaned up
        by re-verification alone.
        """
        try:
            result = await self.client.api_call(
                mgmt_name=self.mgmt_name,
                domain=self.info.domain_name,
                command="discard",
                payload={},
            )
            if result.success:
                self.logger.info(
                    f"[{self.info.package_name}] Step: discard_session | Session discarded"
                )
            else:
                self.logger.warning(
                    f"[{self.info.package_name}] Step: discard_session | "
                    f"Failed: {result.message or result.code}"
                )
        except Exception as e:
            self.logger.warning(
                f"[{self.info.package_name}] Error discarding session: {e}",
                exc_info=True,
            )

    async def verify_post_delete(self) -> VerificationResult:
        """Verify policy after rules have been deleted.

        Called after rollback_rules() to confirm the domain is clean before
        deciding whether to also discard the session.
        """
        verifier = PolicyVerifier(self.client)
        result = await verifier.verify_policy(
            domain_name=self.info.domain_name,
            package_name=self.info.package_name,
        )
        status = "PASS" if result.success else "FAIL"
        self.logger.info(f"[{self.info.package_name}] Step: verify_post_delete | Status: {status}")
        return result

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
            self.logger.warning(f"[{self.info.package_name}] No SID found for evidence capture")
            return EvidenceData(
                domain_name=self.info.domain_name,
                package_name=self.info.package_name,
                package_uid=self.info.package_uid,
                domain_uid=self.info.domain_uid,
                session_changes={},
            )

        domain_sid = sid_record.sid

        # Use the current session UID that was captured after creating changes
        session_uid = self.current_session_uid

        # Call show-changes with to-session to scope to our specific changes
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

        # Store the entire show-changes response data
        # The evidence generator will parse it to extract operations
        session_changes = sc_result.data if sc_result.success and sc_result.data else {}

        # Debug: log what show-changes returned
        self.logger.info(
            f"[{self.info.package_name}] show-changes API response: success={sc_result.success}, "
            f"data_keys={list(session_changes.keys()) if session_changes else 'None'}, "
            f"message={sc_result.message if not sc_result.success else 'N/A'}"
        )
        if session_changes and "domain_changes" in session_changes:
            dc = session_changes["domain_changes"]
            self.logger.info(
                f"[{self.info.package_name}] domain_changes keys: {list(dc.keys()) if dc else 'empty dict'}"
            )

        self.logger.info(
            f"[{self.info.package_name}] Step: capture_evidence | Session UID: {session_uid}"
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
