"""Policy verification via CPAIOPS."""

import logging
from dataclasses import dataclass

from cpaiops import CPAIOPSClient

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of policy verification."""

    success: bool
    errors: list[str]
    warnings: list[str] | None = None


@dataclass
class PackageVerifyInput:
    """Input for grouped policy verification."""

    domain_name: str
    domain_uid: str
    package_name: str
    package_uid: str


class PolicyVerifier:
    """Verify policy integrity via CPAIOPS."""

    def __init__(self, client: CPAIOPSClient):
        """Initialize with CPAIOPS client."""
        self.client = client

    async def verify_policy(
        self, domain_name: str, package_name: str, session_name: str | None = None
    ) -> VerificationResult:
        """Verify policy via Check Point API.

        Args:
            domain_name: Domain name
            package_name: Policy package name
            session_name: Optional session name for context

        Returns:
            VerificationResult with success status and errors
        """
        mgmt_name = self.client.get_mgmt_names()[0]

        payload = {"policy-package": package_name}
        if session_name:
            payload["session-name"] = session_name

        result = await self.client.api_call(
            mgmt_name, "verify-policy", domain=domain_name, payload=payload
        )

        if result.success:
            logger.info(f"Policy verification successful for {package_name}")
            return VerificationResult(success=True, errors=[], warnings=None)

        # Extract errors from response
        errors = []
        if result.message:
            errors.append(result.message)

        logger.warning(f"Policy verification failed for {package_name}: {errors}")
        return VerificationResult(success=False, errors=errors)

    async def verify_policy_grouped(
        self, packages: list[PackageVerifyInput]
    ) -> list[tuple[PackageVerifyInput, VerificationResult]]:
        """Verify policy for multiple (domain, package) pairs.

        Args:
            packages: List of packages to verify.

        Returns:
            List of (input, result) pairs in the same order as inputs.
        """
        results: list[tuple[PackageVerifyInput, VerificationResult]] = []
        for pkg in packages:
            result = await self.verify_policy(
                domain_name=pkg.domain_name,
                package_name=pkg.package_name,
            )
            results.append((pkg, result))
        return results
