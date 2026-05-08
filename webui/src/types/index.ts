/** API request and response types */

export interface LoginRequest {
  username: string;
  password: string;
}

export interface AuthResponse {
  message: string;
  username?: string;
}

export interface UserInfo {
  username: string;
  logged_in_at: string;
}

export interface DomainItem {
  name: string;
  uid: string;
}

export interface SectionInfo {
  name: string;
  uid: string;
  rulebase_range: [number, number];  // [min, max]
  rule_count: number;
}

export interface PackageInfo {
  name: string;
  uid?: string;
  access_layer?: string;
  sections: SectionInfo[];
}

export interface DomainInfo {
  name: string;
  uid: string;
  packages: PackageInfo[];
}

export interface DomainsResponse {
  domains: DomainItem[];
}

export interface ErrorResponse {
  error: string;
}

export interface PackageItem {
  name: string;
  uid: string;
  access_layer: string;
}

export interface SectionItem {
  name: string;
  uid: string;
  rulebase_range: [number, number];  // [min, max]
  rule_count: number;
}

export interface SectionsResponse {
  sections: SectionItem[];
  total_rules: number;
}

export interface PackagesResponse {
  packages: PackageItem[];
}

export interface PositionChoice {
  type: 'top' | 'bottom' | 'custom';
  custom_number?: number;
}

export interface PreparedRule {
  id: string;
  domain: DomainItem;
  package: PackageItem;
  section: SectionItem | null;
  position: PositionChoice;
}

export interface IpEntry {
  original: string;
  type: 'ipv4' | 'ipv6' | 'ipv4-cidr' | 'ipv6-cidr' | 'fqdn' | 'range' | 'any' | 'prefixed';
  normalized: string;
}

export interface IpPool {
  raw: string;
  validated: IpEntry[];
  invalid: string[];
  errors: string[];
}

export interface RuleLine {
  ip: IpEntry | null;
  domain: DomainItem | null;
  package: PackageItem | null;
  section: SectionItem | null;
  position: PositionChoice;
  action: 'accept' | 'drop';
  track: 'log' | 'none';
}

export interface RuleCard {
  id: string;
  source: RuleLine;
  destination: RuleLine;
  samePackage: boolean;
}

export interface CreateRuleRequest {
  source: {
    domain_uid: string;
    package_uid: string;
    section_uid: string | null;
    position: PositionChoice;
    action: 'accept' | 'drop';
    track: 'log' | 'none';
    source_ip: string;
    dest_ip: string;
  };
  destination: {
    domain_uid: string;
    package_uid: string;
    section_uid: string | null;
    position: PositionChoice;
    action: 'accept' | 'drop';
    track: 'log' | 'none';
    source_ip: string;
    dest_ip: string;
  };
}

export interface BatchRulesResponse {
  success: boolean;
  created: number;
  failed: number;
  errors: Array<{ rule_id: string; message: string }>;
}

// === Domains_2 Types ===
// Note: Domains_2 uses camelCase for frontend state (RuleRow) and
// snake_case for API requests (Domains2BatchRequest) to match
// existing API conventions.

export interface ServiceEntry {
  original: string;
  normalized: string;
  type: 'protocol' | 'port' | 'any' | 'named';
}

export interface Prediction {
  ip: IpEntry;
  candidates: PredictionCandidate[];
  source: 'source' | 'dest'; // Track which pool this prediction came from
  hostname: string | null;  // First matching hostname, or null
}

export interface PredictionCandidate {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnet: string;
  hostnames: string[];  // Copied from TopologyEntry.hosts
  ip_hostnames: Record<string, string>;  // IP to hostname mapping
}

export interface RuleRow {
  id: string;
  sourceIps: IpEntry[];
  destIps: IpEntry[];
  domain: DomainItem | null;
  package: PackageItem | null;
  section: SectionItem | null;
  position: PositionChoice;
  action: 'accept' | 'drop';
  track: 'log' | 'none';
  services: ServiceEntry[];
  comments?: string;
  rule_name?: string;
}

export interface TopologyEntry {
  domain: DomainItem;
  package: PackageItem;
  firewall: string;
  subnets: string[];
  hosts: string[];  // Hostnames matching this topology entry
  ip_hostnames: Record<string, string>;  // IP to hostname mapping for exact matching
}

export interface TopologyResponse {
  topology: TopologyEntry[];
}

export interface Domains2BatchRequest {
  rules: Array<{
    source_ips: string[];
    dest_ips: string[];
    services: string[];
    domain_uid: string;
    package_uid: string;
    section_uid: string | null;
    position: PositionChoice;
    action: 'accept' | 'drop';
    track: 'log' | 'none';
  }>;
}

export interface CacheStatusResponse {
  domains_cached_at: string | null;
  packages_cached_at: string | null;
  sections_cached_at: string | null;
  is_empty: boolean;
  refreshing: boolean;
  core_refreshing: boolean;
  sections_refreshing: boolean;
  domains_progress: {
    processed: number;
    total: number;
  };
  current_domain_name: string | null;
  packages_progress: {
    processed: number;
    total: number;
  };
  sections_progress: {
    processed: number;
    total: number;
  };
}

// === RITM Types ===

export interface RITMItem {
  ritm_number: string;
  username_created: string;
  date_created: string;
  date_updated: string | null;
  date_approved: string | null;
  username_approved: string | null;
  feedback: string | null;
  status: number;
  approver_locked_by: string | null;
  approver_locked_at: string | null;
  editor_locked_by: string | null;
  editor_locked_at: string | null;
  // Input pools
  source_ips?: string[];
  dest_ips?: string[];
  services?: string[];
  // Evidence data
  session_changes_evidence1?: string | null;
}

export interface RITMCreateRequest {
  ritm_number: string;
}

export interface RITMUpdateRequest {
  status?: number;
  feedback?: string;
}

export interface PolicyItem {
  id?: number;
  ritm_number: string;
  comments: string;
  rule_name: string;
  domain_uid: string;
  domain_name: string;
  package_uid: string;
  package_name: string;
  section_uid: string | null;
  section_name: string | null;
  position_type: 'top' | 'bottom' | 'custom';
  position_number?: number;
  action: 'accept' | 'drop';
  track: 'log' | 'none';
  source_ips: string[];
  dest_ips: string[];
  services: string[];
}

export interface RITMWithPolicies {
  ritm: RITMItem;
  policies: PolicyItem[];
}

export interface RITMListResponse {
  ritms: RITMItem[];
}

export interface PublishResponse {
  success: boolean;
  message: string;
  created?: number;
  errors: string[];
}

export interface PlanYamlResponse {
  yaml: string;
  changes: Record<string, number>;
}

export interface ApplyResponse {
  objects_created: number;
  rules_created: number;
  errors: string[];
  warnings: string[];
  session_changes: Record<string, unknown> | null;
}

export interface VerifyResponse {
  verified: boolean;
  errors: string[];
}

export interface RITMStatus {
  WORK_IN_PROGRESS: 0;
  READY_FOR_APPROVAL: 1;
  APPROVED: 2;
  COMPLETED: 3;
}

export const RITM_STATUS: RITMStatus = {
  WORK_IN_PROGRESS: 0,
  READY_FOR_APPROVAL: 1,
  APPROVED: 2,
  COMPLETED: 3,
};

export interface PackageResult {
  domain: string;
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

export interface EvidenceSessionItem {
  id: number;
  attempt: number;
  session_type: string;
  session_uid: string | null;
  sid: string | null;
  created_at: string;
  session_changes: Record<string, unknown> | null;
}

export interface PackageEvidenceItem {
  package_name: string;
  package_uid: string;
  sessions: EvidenceSessionItem[];
}

export interface DomainEvidenceItem {
  domain_name: string;
  domain_uid: string;
  packages: PackageEvidenceItem[];
}

export interface EvidenceHistoryResponse {
  domains: DomainEvidenceItem[];
}

// === RITM V3 Workflow Types ===

export interface PackageVerifyResult {
  domain_name: string;
  domain_uid: string;
  package_name: string;
  package_uid: string;
  success: boolean;
  errors: string[];
}

export interface GroupedVerifyResponse {
  all_passed: boolean;
  results: PackageVerifyResult[];
}

export interface TryVerifyRequest {
  force_continue: boolean;
  skip_package_uids: string[];
}

