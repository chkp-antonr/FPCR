"""Pydantic models for API requests and responses."""

from datetime import UTC, datetime
from enum import IntEnum
from typing import Any, Literal, cast

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Column, Field, SQLModel

# Hot reload guard: clear metadata if tables are already defined
# This prevents "Table is already defined" errors during uvicorn hot reload
_known_tables = {
    "cached_domains",
    "cached_packages",
    "cached_sections",
    "cached_section_assignments",
    "ritm",
    "ritm_policy",
    "ritm_created_objects",
    "ritm_created_rules",
    "ritm_verification",
    "ritm_editors",
    "ritm_reviewers",
    "ritm_evidence_sessions",
}
if _known_tables & SQLModel.metadata.tables.keys():
    SQLModel.metadata.clear()


class RITMStatus(IntEnum):
    """RITM workflow status codes."""

    WORK_IN_PROGRESS = 0
    READY_FOR_APPROVAL = 1
    APPROVED = 2
    COMPLETED = 3


class LoginRequest(BaseModel):
    """Login request payload."""

    username: str
    password: str


class AuthResponse(BaseModel):
    """Authentication response."""

    message: str
    username: str | None = None


class UserInfo(BaseModel):
    """Current user information."""

    username: str
    logged_in_at: str


class DomainItem(BaseModel):
    """Single domain item."""

    name: str
    uid: str


class DomainsResponse(BaseModel):
    """Domains list response."""

    domains: list[DomainItem]


class ErrorResponse(BaseModel):
    """Error response."""

    error: str


class PackageItem(BaseModel):
    """Single policy package item."""

    name: str
    uid: str
    access_layer: str


class SectionItem(BaseModel):
    """Single access section item with rule range."""

    name: str
    uid: str
    rulebase_range: tuple[int, int]  # (min_rule, max_rule)
    rule_count: int


class PackagesResponse(BaseModel):
    """Packages list response."""

    packages: list[PackageItem]


class SectionsResponse(BaseModel):
    """Sections list response."""

    sections: list[SectionItem]
    total_rules: int


class PositionChoice(BaseModel):
    """Rule position choice."""

    type: str  # 'top', 'bottom', 'custom'
    custom_number: int | None = None


class RuleDefinition(BaseModel):
    """Rule definition for a single line."""

    domain_uid: str
    package_uid: str
    section_uid: str | None = None
    position: PositionChoice
    action: str  # 'accept' or 'drop'
    track: str  # 'log' or 'none'
    source_ip: str
    dest_ip: str


class CreateRuleRequest(BaseModel):
    """Request to create a rule pair."""

    source: RuleDefinition
    destination: RuleDefinition


class BatchRulesResponse(BaseModel):
    """Response from batch rule creation."""

    success: bool
    created: int
    failed: int
    errors: list[dict[str, str]]


class TopologyEntry(BaseModel):
    """Single topology entry mapping domain/package/firewall to subnets."""

    domain: DomainItem
    package: PackageItem
    firewall: str
    subnets: list[str]
    hosts: list[str] = []  # Hostnames whose IPs match these subnets
    ip_hostnames: dict[str, str] = {}  # IP to hostname mapping for exact matching


class TopologyResponse(BaseModel):
    """Topology response for prediction engine."""

    topology: list[TopologyEntry]


class Domains2RuleRequest(BaseModel):
    """Request for a single domains2 rule with multiple IPs."""

    source_ips: list[str]
    dest_ips: list[str]
    services: list[str]
    domain_uid: str
    package_uid: str
    section_uid: str | None = None
    position: PositionChoice
    action: str  # 'accept' or 'drop'
    track: str  # 'log' or 'none'


class Domains2BatchRequest(BaseModel):
    """Request to create multiple domains2 rules."""

    rules: list[Domains2RuleRequest]


# Cache models for Check Point data


class CachedDomain(SQLModel, table=True):
    """Cached Check Point domain."""

    __tablename__ = "cached_domains"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    name: str
    last_published_session: str | None = Field(default=None, index=True)
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class CachedPackage(SQLModel, table=True):
    """Cached policy package for a domain."""

    __tablename__ = "cached_packages"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    domain_uid: str = Field(foreign_key="cached_domains.uid", index=True)
    name: str
    access_layer: str
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class CachedSection(SQLModel, table=True):
    """Cached access section for a package."""

    __tablename__ = "cached_sections"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    uid: str = Field(index=True, unique=True)
    name: str
    rulebase_range: str  # JSON stored as string: "[min, max]"
    rule_count: int
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class CachedSectionAssignment(SQLModel, table=True):
    """Mapping between cached sections and package/domain pairs."""

    __tablename__ = "cached_section_assignments"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]
    __table_args__ = (UniqueConstraint("domain_uid", "package_uid", "section_uid"),)

    id: int | None = Field(default=None, primary_key=True)
    domain_uid: str = Field(index=True)
    package_uid: str = Field(foreign_key="cached_packages.uid", index=True)
    section_uid: str = Field(foreign_key="cached_sections.uid", index=True)
    cached_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITM(SQLModel, table=True):
    """RITM (Requested Item) approval workflow metadata."""

    __tablename__ = "ritm"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]

    ritm_number: str = Field(primary_key=True)
    username_created: str
    date_created: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))
    date_updated: datetime | None = None
    date_approved: datetime | None = None
    username_approved: str | None = None
    feedback: str | None = None
    status: int = Field(default=RITMStatus.WORK_IN_PROGRESS)
    approver_locked_by: str | None = None
    approver_locked_at: datetime | None = None
    editor_locked_by: str | None = None
    editor_locked_at: datetime | None = None
    source_ips: str | None = Field(default=None, description="JSON array of source IPs")
    dest_ips: str | None = Field(default=None, description="JSON array of destination IPs")
    services: str | None = Field(default=None, description="JSON array of services")


class Policy(SQLModel, table=True):
    """Individual policy rule linked to a RITM."""

    __tablename__ = "ritm_policy"  # pyright: ignore[reportAssignmentType,reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    comments: str
    rule_name: str
    domain_uid: str
    domain_name: str
    package_uid: str
    package_name: str
    section_uid: str | None = None
    section_name: str | None = None
    position_type: str  # 'top', 'bottom', 'custom'
    position_number: int | None = None
    action: str  # 'accept', 'drop'
    track: str  # 'log', 'none'
    source_ips: str  # JSON array
    dest_ips: str  # JSON array
    services: str  # JSON array


class RITMCreatedObject(SQLModel, table=True):
    """Track objects created during RITM workflow."""

    __tablename__ = cast(Any, "ritm_created_objects")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    object_uid: str
    object_type: str  # 'host', 'network', 'address-range', 'network-group'
    object_name: str
    domain_uid: str
    created_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMCreatedRule(SQLModel, table=True):
    """Track rules created during RITM workflow."""

    __tablename__ = cast(Any, "ritm_created_rules")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    rule_uid: str
    rule_number: int | None = None
    package_uid: str
    domain_uid: str
    verification_status: str = Field(default="pending")  # 'pending', 'verified', 'failed'
    disabled: bool = Field(default=False)
    created_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMVerification(SQLModel, table=True):
    """Store verification results per package."""

    __tablename__ = cast(Any, "ritm_verification")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    package_uid: str
    domain_uid: str
    verified: bool
    errors: str | None = Field(default=None, description="JSON array of error messages")
    changes_snapshot: str | None = Field(
        default=None, description="JSON: show-changes API response"
    )
    created_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMEditor(SQLModel, table=True):
    """Engineers who have edited this RITM – permanently blocked from approving."""

    __tablename__ = cast(Any, "ritm_editors")
    __table_args__ = (UniqueConstraint("ritm_number", "username"),)

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    username: str
    added_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMReviewer(SQLModel, table=True):
    """Engineers who have approved/rejected this RITM – permanently blocked from editing."""

    __tablename__ = cast(Any, "ritm_reviewers")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    username: str
    action: str  # "approved" | "rejected"
    acted_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


class RITMEvidenceSession(SQLModel, table=True):
    """Cumulative evidence history – one row per successful package per Try & Verify / publish run."""

    __tablename__ = cast(Any, "ritm_evidence_sessions")

    id: int | None = Field(default=None, primary_key=True)
    ritm_number: str = Field(foreign_key="ritm.ritm_number", index=True)
    attempt: int
    domain_name: str
    domain_uid: str
    package_name: str
    package_uid: str
    session_uid: str | None = None
    sid: str | None = None
    session_type: str  # "initial" | "correction" | "approval"
    session_changes: str | None = None  # JSON blob: raw show-changes API response
    created_at: datetime = Field(sa_column=Column(DateTime(), default=lambda: datetime.now(UTC)))


# Backward compatibility alias
RITMSession = RITMEvidenceSession


class ReviewerItem(BaseModel):
    """Single reviewer action."""

    username: str
    action: str  # "approved" | "rejected"
    acted_at: str


class RITMItem(BaseModel):
    """RITM item for API responses."""

    ritm_number: str
    username_created: str
    date_created: str
    date_updated: str | None = None
    date_approved: str | None = None
    username_approved: str | None = None
    feedback: str | None = None
    status: int
    approver_locked_by: str | None = None
    approver_locked_at: str | None = None
    editor_locked_by: str | None = None
    editor_locked_at: str | None = None
    source_ips: list[str] | None = None
    dest_ips: list[str] | None = None
    services: list[str] | None = None
    editors: list[str] = []
    reviewers: list[ReviewerItem] = []


class RITMCreateRequest(BaseModel):
    """Request to create a new RITM."""

    ritm_number: str


class RITMUpdateRequest(BaseModel):
    """Request to update RITM status."""

    status: int | None = None
    feedback: str | None = None


class PolicyItem(BaseModel):
    """Single policy rule for API."""

    id: int | None = None
    ritm_number: str
    comments: str
    rule_name: str
    domain_uid: str
    domain_name: str
    package_uid: str
    package_name: str
    section_uid: str | None = None
    section_name: str | None = None
    position_type: str
    position_number: int | None = None
    action: str
    track: str
    source_ips: list[str]
    dest_ips: list[str]
    services: list[str]


class RITMWithPolicies(BaseModel):
    """RITM with associated policies."""

    ritm: RITMItem
    policies: list[PolicyItem]


class RITMListResponse(BaseModel):
    """Response listing RITMs."""

    ritms: list[RITMItem]


class PublishResponse(BaseModel):
    """Response from RITM publish."""

    success: bool
    message: str
    created: int | None = None
    errors: list[str] = []


class MatchResult(BaseModel):
    """Result of object matching/creation."""

    input: str  # Original input (IP, network, etc.)
    object_uid: str
    object_name: str
    object_type: str
    created: bool  # True if object was just created
    matches_convention: bool
    usage_count: int | None = None


class MatchObjectsRequest(BaseModel):
    """Request to match/create objects."""

    source_ips: list[str]
    dest_ips: list[str]
    services: list[str]
    domain_uid: str


class MatchObjectsResponse(BaseModel):
    """Response from object matching endpoint."""

    source: list[MatchResult]
    dest: list[MatchResult]
    services: list[MatchResult]
    created_count: int


class PackageErrorResponse(BaseModel):
    """Package-level error response."""

    package_uid: str
    package_name: str
    domain_name: str
    verified: bool
    created_count: int
    kept_count: int
    deleted_count: int
    errors: list[str]


class CreateRulesRequest(BaseModel):
    """Request to create rules with verification."""

    rules: list[PolicyItem]


class CreationResult(BaseModel):
    """Result of rule creation with verification."""

    ritm_number: str
    total_created: int
    total_kept: int
    total_deleted: int
    packages: list[PackageErrorResponse]

    @property
    def has_failures(self) -> bool:
        return any(not p.verified for p in self.packages)


class EvidenceResponse(BaseModel):
    """Response from evidence generation."""

    html: str
    yaml: str
    changes: dict[str, Any]


class EvidenceSessionItem(BaseModel):
    """Single session entry in the evidence history."""

    id: int
    attempt: int
    session_type: str
    session_uid: str | None = None
    sid: str | None = None
    created_at: str
    session_changes: dict[str, Any] | None = None


class PackageEvidenceItem(BaseModel):
    """Package entry in the evidence history."""

    package_name: str
    package_uid: str
    sessions: list[EvidenceSessionItem]


class DomainEvidenceItem(BaseModel):
    """Domain entry in the evidence history."""

    domain_name: str
    domain_uid: str
    packages: list[PackageEvidenceItem]


class EvidenceHistoryResponse(BaseModel):
    """Full cumulative evidence history for a RITM."""

    domains: list[DomainEvidenceItem]


class PlanYamlResponse(BaseModel):
    """Response for plan-only CPCRUD YAML generation."""

    yaml: str
    changes: dict[str, int]


class ApplyResponse(BaseModel):
    """Response for RITM apply (object + rule creation) step."""

    objects_created: int
    rules_created: int
    errors: list[str]
    warnings: list[str]
    session_changes: dict[str, Any] | None = None


class VerifyResponse(BaseModel):
    """Response for RITM verify step."""

    verified: bool
    errors: list[str]


class PackageResult(BaseModel):
    """Result of Try & Verify for a single package."""

    domain: str = ""
    package: str
    status: Literal["success", "skipped", "create_failed", "verify_failed"]
    rules_created: int = 0
    objects_created: int = 0
    errors: list[str] = PydanticField(default_factory=list)


class CreateResult(BaseModel):
    """Result of object and rule creation with UIDs for rollback."""

    objects_created: int
    rules_created: int
    created_rule_uids: list[str]
    created_object_uids: list[str]
    errors: list[str] = PydanticField(default_factory=list)


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
    evidence_pdf: str | None = Field(default=None, description="Base64 encoded PDF bytes")
    evidence_html: str | None = None
    published: bool
    session_changes: dict[str, Any] | None = None
