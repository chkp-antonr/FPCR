"""Mock data source for WebUI testing without Check Point API."""

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from .models import DomainItem, PackageItem, SectionItem, TopologyEntry

logger = logging.getLogger(__name__)


class MockDataSource:
    """Mock data source that reads from local file instead of Check Point API."""

    def __init__(self, file_path: str):
        """Load and parse mock data file (JSON or YAML)."""
        self.file_path = Path(file_path)
        logger.info(
            f"MockDataSource: Loading from {self.file_path.absolute()} (exists: {self.file_path.exists()})"
        )
        self.data: dict[str, Any] = self._load_file()
        logger.info(f"MockDataSource: Loaded data: {self.data}")
        self._uids: dict[str, str] = {}  # Cache for generated UIDs
        self._ensure_uids()

    def _load_file(self) -> dict[str, Any]:
        """Load file based on extension (json or yaml)."""
        if not self.file_path.exists():
            logger.warning(f"MockDataSource: File {self.file_path} does not exist")
            return {"domains": {}}

        suffix = self.file_path.suffix.lower()
        logger.info(f"MockDataSource: File suffix is '{suffix}'")

        try:
            if suffix == ".json":
                with open(self.file_path) as f:
                    return cast(dict[str, Any], json.load(f))
            elif suffix in [".yaml", ".yml"]:
                yaml = YAML(typ="safe")
                with open(self.file_path) as f:
                    result = yaml.load(f)
                    logger.info(f"MockDataSource: YAML loaded, result type: {type(result)}")
                    if isinstance(result, dict):
                        return cast(dict[str, Any], result)
                    return {}
            else:
                logger.warning(f"MockDataSource: Unsupported file format: {suffix}")
                return {"domains": {}}
        except Exception as exc:
            logger.error(f"MockDataSource: Error loading file: {exc}")
            # Return empty dict on parse errors
            return {"domains": {}}

    def _generate_uid(self, key: str) -> str:
        """Generate deterministic UUID from key using MD5 hash."""
        hash_bytes = hashlib.md5(key.encode()).digest()
        # Convert first 16 bytes to UUID format
        return str(uuid.UUID(bytes=hash_bytes[:16]))

    def _ensure_uids(self) -> None:
        """Auto-generate UIDs for entities missing them."""
        domains = self.data.get("domains", {})
        logger.info(f"MockDataSource: Ensuring UIDs for {len(domains)} domains")

        for domain_name, domain_data in domains.items():
            domain_key = f"domain:{domain_name}"
            if domain_key not in self._uids:
                self._uids[domain_key] = self._generate_uid(domain_key)

            policies = domain_data.get("policies", {})
            for policy_name, policy_data in policies.items():
                policy_key = f"policy:{domain_name}:{policy_name}"
                if policy_key not in self._uids:
                    self._uids[policy_key] = self._generate_uid(policy_key)

                sections = policy_data.get("sections", {})
                for section_name in sections:
                    section_key = f"section:{domain_name}:{policy_name}:{section_name}"
                    if section_key not in self._uids:
                        self._uids[section_key] = self._generate_uid(section_key)

                firewalls = policy_data.get("firewalls", {})
                for fw_name in firewalls:
                    fw_key = f"firewall:{domain_name}:{policy_name}:{fw_name}"
                    if fw_key not in self._uids:
                        self._uids[fw_key] = self._generate_uid(fw_key)

    def _ip_in_subnet(self, ip: str, subnet: str) -> bool:
        """Check if an IP is within a subnet (CIDR or single IP)."""
        try:
            import ipaddress

            ip_obj = ipaddress.ip_address(ip)
            if "/" in subnet:
                network = ipaddress.ip_network(subnet, strict=False)
                return ip_obj in network
            else:
                return ip == subnet
        except ValueError:
            logger.warning(f"Invalid IP or subnet: ip={ip}, subnet={subnet}")
            return False

    def _get_domain_uid(self, domain_name: str) -> str:
        """Get or generate UID for a domain."""
        key = f"domain:{domain_name}"
        if key not in self._uids:
            self._uids[key] = self._generate_uid(key)
        return self._uids[key]

    def _get_policy_uid(self, domain_name: str, policy_name: str) -> str:
        """Get or generate UID for a policy."""
        key = f"policy:{domain_name}:{policy_name}"
        if key not in self._uids:
            self._uids[key] = self._generate_uid(key)
        return self._uids[key]

    def _get_section_uid(self, domain_name: str, policy_name: str, section_name: str) -> str:
        """Get or generate UID for a section."""
        key = f"section:{domain_name}:{policy_name}:{section_name}"
        if key not in self._uids:
            self._uids[key] = self._generate_uid(key)
        return self._uids[key]

    def get_domains(self) -> list[DomainItem]:
        """Return all domains with auto-generated UIDs."""
        domains = []
        domain_names = list(self.data.get("domains", {}).keys())
        logger.info(f"MockDataSource.get_domains: Found domain names: {domain_names}")
        for name in domain_names:
            uid = self._get_domain_uid(name)
            logger.info(f"MockDataSource.get_domains: Creating DomainItem({name}, {uid})")
            domains.append(DomainItem(name=name, uid=uid))
        logger.info(f"MockDataSource.get_domains: Returning {len(domains)} domains")
        return domains

    def get_packages(self, domain_uid: str) -> list[PackageItem]:
        """Return packages for a domain."""
        logger.info(
            f"MockDataSource.get_packages: Looking for packages for domain_uid={domain_uid}"
        )
        # Find domain name by UID
        domain_name = None
        for name in self.data.get("domains", {}):
            if self._get_domain_uid(name) == domain_uid:
                domain_name = name
                break

        if not domain_name:
            logger.warning(f"MockDataSource.get_packages: No domain found for uid={domain_uid}")
            return []

        packages = []
        policies = self.data.get("domains", {}).get(domain_name, {}).get("policies", {})
        for policy_name in policies:
            packages.append(
                PackageItem(
                    name=policy_name,
                    uid=self._get_policy_uid(domain_name, policy_name),
                    access_layer=f"{policy_name}-layer",  # Auto-generate layer name
                )
            )
        logger.info(
            f"MockDataSource.get_packages: Returning {len(packages)} packages for {domain_name}"
        )
        return packages

    def get_sections(self, domain_uid: str, package_uid: str) -> tuple[list[SectionItem], int]:
        """Return sections with sequential rulebase ranges and total rule count."""
        # Find domain and policy by UIDs
        domain_name = None
        policy_name = None

        for d_name in self.data.get("domains", {}):
            if self._get_domain_uid(d_name) == domain_uid:
                domain_name = d_name
                policies = self.data.get("domains", {}).get(d_name, {}).get("policies", {})
                for p_name in policies:
                    if self._get_policy_uid(d_name, p_name) == package_uid:
                        policy_name = p_name
                        break
                break

        if not domain_name or not policy_name:
            return [], 0

        sections_data = (
            self.data.get("domains", {})
            .get(domain_name, {})
            .get("policies", {})
            .get(policy_name, {})
            .get("sections", {})
        )

        sections = []
        current_rule = 1

        for section_name, rule_count in sections_data.items():
            section_min = current_rule
            section_max = current_rule + rule_count - 1
            sections.append(
                SectionItem(
                    name=section_name,
                    uid=self._get_section_uid(domain_name, policy_name, section_name),
                    rulebase_range=(section_min, section_max),
                    rule_count=rule_count,
                )
            )
            current_rule = section_max + 1

        total_rules = current_rule - 1
        return sections, total_rules

    def get_topology(self) -> list[TopologyEntry]:
        """Extract topology from mock data for prediction engine."""
        topology: list[TopologyEntry] = []

        if not self.data or "domains" not in self.data:
            return topology

        # Build IP -> hostname mapping from hosts section
        hosts_map = self.data.get("hosts", {})

        for domain_name, domain_data in self.data["domains"].items():
            domain = DomainItem(name=domain_name, uid=self._get_domain_uid(domain_name))

            if "policies" not in domain_data:
                continue

            for policy_name, policy_data in domain_data["policies"].items():
                package = PackageItem(
                    name=policy_name,
                    uid=self._get_policy_uid(domain_name, policy_name),
                    access_layer="network",
                )

                if "firewalls" not in policy_data:
                    continue

                for fw_name, fw_data in policy_data["firewalls"].items():
                    subnets = fw_data.get("subnets", [])

                    # Find hosts whose IPs are within this entry's subnets
                    hosts = []
                    ip_hostnames = {}
                    for hostname, host_ip in hosts_map.items():
                        for subnet in subnets:
                            if self._ip_in_subnet(host_ip, subnet):
                                hosts.append(hostname)
                                ip_hostnames[host_ip] = hostname
                                break

                    entry = TopologyEntry(
                        domain=domain,
                        package=package,
                        firewall=fw_name,
                        subnets=subnets,
                        hosts=hosts,
                        ip_hostnames=ip_hostnames,
                    )
                    topology.append(entry)

        return topology
