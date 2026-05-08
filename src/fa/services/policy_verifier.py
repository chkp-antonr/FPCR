"""Policy verification via CPAIOPS."""

import logging
from dataclasses import dataclass, field
from typing import Any

from cpaiops import CPAIOPSClient

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of policy verification."""

    success: bool
    errors: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class PackageVerifyInput:
    """Input for grouped policy verification."""

    domain_name: str
    domain_uid: str
    package_name: str
    package_uid: str


def _extract_messages(items: object) -> list[str]:
    """Extract message strings from a Check Point error/warning array.

    Items may be plain strings or dicts with a "message" key.
    """
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, str) and item.strip():
            result.append(item)
        elif isinstance(item, dict) and item.get("message"):
            result.append(item["message"])
    return result


def _parse_result_data(data: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) extracted from a raw API result data dict.

    Checks both top-level fields and task-details arrays produced by show-task.
    """
    if not data:
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    # Top-level errors / blocking-errors / warnings
    errors.extend(_extract_messages(data.get("errors")))
    errors.extend(_extract_messages(data.get("blocking-errors")))
    warnings.extend(_extract_messages(data.get("warnings")))

    # Task-based results from show-task polling
    for task in data.get("tasks", []) if isinstance(data.get("tasks"), list) else []:
        for detail in (
            task.get("task-details", []) if isinstance(task.get("task-details"), list) else []
        ):
            errors.extend(_extract_messages(detail.get("errors")))
            errors.extend(_extract_messages(detail.get("blocking-errors")))
            warnings.extend(_extract_messages(detail.get("warnings")))

    return errors, warnings


class PolicyVerifier:
    """Verify policy integrity via CPAIOPS."""

    def __init__(self, client: CPAIOPSClient):
        """Initialize with CPAIOPS client."""
        self.client = client

    async def verify_policy(
        self, domain_name: str, package_name: str, session_name: str | None = None
    ) -> VerificationResult:
        """Verify policy via Check Point API."""
        mgmt_name = self.client.get_mgmt_names()[0]

        payload: dict[str, Any] = {"policy-package": package_name}
        if session_name:
            payload["session-name"] = session_name

        result = await self.client.api_call(
            mgmt_name, "verify-policy", domain=domain_name, payload=payload
        )

        logger.debug(
            "verify-policy raw result: success=%s code=%r message=%r data=%s",
            result.success,
            result.code,
            result.message,
            result.data,
        )

        errors, warnings = _parse_result_data(result.data)

        if result.success:
            if warnings:
                logger.warning(
                    "Policy verification succeeded with warnings for %s: %s",
                    package_name,
                    warnings,
                )
            else:
                logger.info("Policy verification successful for %s", package_name)
            return VerificationResult(success=True, errors=[], warnings=warnings)

        # Failure — fall back to result.message if no structured errors found
        if not errors and result.message:
            errors.append(result.message)

        logger.warning(
            "Policy verification failed for %s: errors=%s warnings=%s",
            package_name,
            errors,
            warnings,
        )
        return VerificationResult(success=False, errors=errors, warnings=warnings)

    async def verify_policy_grouped(
        self, packages: list[PackageVerifyInput]
    ) -> list[tuple[PackageVerifyInput, VerificationResult]]:
        """Verify policy for multiple (domain, package) pairs sequentially.

        Check Point MDS rejects parallel domain logins from the same credentials,
        so verifications must be serialized. Streaming results are handled by the
        SSE endpoint which yields each result as it arrives.
        """
        results: list[tuple[PackageVerifyInput, VerificationResult]] = []
        for pkg in packages:
            result = await self.verify_policy(pkg.domain_name, pkg.package_name)
            results.append((pkg, result))
        return results
