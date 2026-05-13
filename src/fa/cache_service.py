"""Cache management for Check Point data."""

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cpaiops import CPAIOPSClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from .db import engine
from .models import CachedDomain, CachedPackage, CachedSection, CachedSectionAssignment

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PackageContext:
    """Cached package metadata required for section refresh."""

    domain_uid: str
    domain_name: str
    package_uid: str
    package_name: str


class CacheService:
    """Manages cached Check Point data in SQLite."""

    def __init__(self) -> None:
        self._core_refresh_lock = asyncio.Lock()
        self._sections_background_lock = asyncio.Lock()
        self._package_refresh_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._package_refresh_locks_guard = asyncio.Lock()
        self._sections_task: asyncio.Task[None] | None = None
        self._core_refreshing = False
        self._sections_refreshing = False
        self._domains_total = 0
        self._domains_processed = 0
        self._current_domain_name: str | None = None
        self._packages_total = 0
        self._packages_processed = 0
        self._sections_total = 0
        self._sections_processed = 0

    async def get_status(self) -> dict[str, Any]:
        """Return cache status with timestamps and progress."""
        try:
            async with AsyncSession(engine) as session:
                domain_cached_at_col = col(CachedDomain.cached_at)
                package_cached_at_col = col(CachedPackage.cached_at)
                section_cached_at_col = col(CachedSection.cached_at)

                domain_result = await session.execute(  # type: ignore[misc]
                    select(domain_cached_at_col).order_by(domain_cached_at_col.desc()).limit(1)
                )
                domain_row = domain_result.scalar_one_or_none()
                domain_ts = domain_row.isoformat() if domain_row else None

                package_result = await session.execute(  # type: ignore[misc]
                    select(package_cached_at_col).order_by(package_cached_at_col.desc()).limit(1)
                )
                package_row = package_result.scalar_one_or_none()
                package_ts = package_row.isoformat() if package_row else None

                section_result = await session.execute(  # type: ignore[misc]
                    select(section_cached_at_col).order_by(section_cached_at_col.desc()).limit(1)
                )
                section_row = section_result.scalar_one_or_none()
                section_ts = section_row.isoformat() if section_row else None

                count_result = await session.execute(select(func.count()).select_from(CachedDomain))
                is_empty = count_result.scalar_one() == 0

                return {
                    "domains_cached_at": domain_ts,
                    "packages_cached_at": package_ts,
                    "sections_cached_at": section_ts,
                    "is_empty": is_empty,
                    "refreshing": self._core_refreshing or self._sections_refreshing,
                    "core_refreshing": self._core_refreshing,
                    "sections_refreshing": self._sections_refreshing,
                    "domains_progress": {
                        "processed": self._domains_processed,
                        "total": self._domains_total,
                    },
                    "current_domain_name": self._current_domain_name,
                    "packages_progress": {
                        "processed": self._packages_processed,
                        "total": self._packages_total,
                    },
                    "sections_progress": {
                        "processed": self._sections_processed,
                        "total": self._sections_total,
                    },
                }
        except OperationalError as e:
            if "no such column" in str(e).lower():
                logger.critical(
                    "Database schema mismatch: cache.db is outdated and incompatible with current model. "
                    "RECOMMENDATION: Delete '_tmp/cache.db' and restart the application to recreate the schema."
                )
            else:
                logger.warning(
                    "Cache status query hit a transient database lock; returning in-memory status"
                )
            return {
                "domains_cached_at": None,
                "packages_cached_at": None,
                "sections_cached_at": None,
                "is_empty": False,
                "refreshing": self._core_refreshing or self._sections_refreshing,
                "core_refreshing": self._core_refreshing,
                "sections_refreshing": self._sections_refreshing,
                "domains_progress": {
                    "processed": self._domains_processed,
                    "total": self._domains_total,
                },
                "current_domain_name": self._current_domain_name,
                "packages_progress": {
                    "processed": self._packages_processed,
                    "total": self._packages_total,
                },
                "sections_progress": {
                    "processed": self._sections_processed,
                    "total": self._sections_total,
                },
            }

    async def refresh_all(self, username: str, password: str, mgmt_ip: str) -> None:
        """Refresh domains and packages, then warm sections in the background."""
        await self.refresh_domains_and_packages(username, password, mgmt_ip)

    async def refresh_domains_and_packages(
        self, username: str, password: str, mgmt_ip: str
    ) -> None:
        """Refresh domains and packages synchronously."""
        if self._core_refresh_lock.locked():
            logger.info("Core cache refresh already in progress, waiting for completion")
            async with self._core_refresh_lock:
                return

        async with self._core_refresh_lock:
            self._core_refreshing = True
            self._domains_total = 0
            self._domains_processed = 0
            self._current_domain_name = None
            self._packages_total = 0
            self._packages_processed = 0
            self._sections_total = 0
            self._sections_processed = 0
            try:
                await self._refresh_domains_and_packages(username, password, mgmt_ip)
                logger.info("Domains and packages cache refresh completed")
            finally:
                self._current_domain_name = None
                self._core_refreshing = False

        self.start_sections_refresh(username, password, mgmt_ip)

    async def wait_for_core_refresh(self) -> bool:
        """Wait for core refresh completion when it is currently in progress."""
        if not self._core_refresh_lock.locked():
            return False

        async with self._core_refresh_lock:
            return True

    async def _refresh_domains_and_packages(
        self, username: str, password: str, mgmt_ip: str
    ) -> None:
        """Refresh domains and packages from Check Point API."""
        async with CPAIOPSClient(
            engine=engine,
            username=username,
            password=password,
            mgmt_ip=mgmt_ip,
        ) as client:
            server_names = client.get_mgmt_names()
            if not server_names:
                logger.warning("No management servers found")
                return

            mgmt_name = server_names[0]
            result = await client.api_query(mgmt_name, "show-domains")

            if not result.success:
                logger.error(f"Failed to fetch domains: {result.message}")
                return

            fetched_domains = result.objects or []
            self._domains_total = len(fetched_domains)

            async with AsyncSession(engine) as session:
                try:
                    # Snapshot existing domain metadata as plain values to avoid
                    # ORM attribute refreshes after commit in async context.
                    existing_result = await session.execute(
                        select(
                            col(CachedDomain.uid),
                            col(CachedDomain.name),
                            col(CachedDomain.last_published_session),
                        )
                    )
                    existing_domains = {
                        row[0]: {"name": row[1], "last_published_session": row[2]}
                        for row in existing_result.all()
                    }
                except OperationalError as e:
                    if "no such column" in str(e).lower():
                        logger.critical(
                            "Database schema mismatch: cache.db is outdated and incompatible with current model. "
                            "RECOMMENDATION: Delete '_tmp/cache.db' and restart the application to recreate the schema."
                        )
                        raise
                    raise

                # Detect inconsistent cache state introduced by interrupted refreshes.
                # If any known domain has zero packages, rebuild package/section cache fully once.
                package_counts_result = await session.execute(
                    select(col(CachedPackage.domain_uid), func.count()).group_by(
                        col(CachedPackage.domain_uid)
                    )
                )
                package_counts_by_domain = {
                    row[0]: row[1] for row in package_counts_result.all() if row[0]
                }

                fetched_domain_uids = {
                    obj.get("uid", "") for obj in fetched_domains if obj.get("uid", "")
                }
                missing_package_uids = {
                    uid
                    for uid in fetched_domain_uids
                    if uid in existing_domains and package_counts_by_domain.get(uid, 0) == 0
                }
                full_repair_mode = len(missing_package_uids) > 0

                if full_repair_mode:
                    logger.warning(
                        "Detected inconsistent package cache for %d domain(s); forcing one full package recache",
                        len(missing_package_uids),
                    )
                    await session.execute(delete(CachedSectionAssignment))
                    await session.execute(delete(CachedPackage))
                    await session.commit()

                # Track which domains were processed
                processed_uids: set[str] = set()

                for obj in fetched_domains:
                    domain_uid = obj.get("uid", "")
                    domain_name = obj.get("name", "")
                    current_published_session = obj.get("last-publish-session", "")

                    processed_uids.add(domain_uid)
                    self._current_domain_name = domain_name

                    # Check if domain exists and has same last_published_session
                    existing = existing_domains.get(domain_uid)
                    if (
                        not full_repair_mode
                        and existing
                        and package_counts_by_domain.get(domain_uid, 0) > 0
                        and existing["last_published_session"] == current_published_session
                    ):
                        logger.info(f"Skipping domain: {domain_name} (no changes)")
                        # Package progress is reported for the currently processed domain.
                        self._packages_total = 0
                        self._packages_processed = 0
                        self._domains_processed += 1
                        continue

                    if (
                        not full_repair_mode
                        and existing
                        and existing["last_published_session"] == current_published_session
                    ):
                        logger.warning(
                            "Domain %s has no cached packages despite unchanged publish session; recaching",
                            domain_name,
                        )

                    # Domain is new or changed - cache it
                    logger.info(f"Caching domain: {domain_name} (uid={domain_uid})")
                    self._current_domain_name = domain_name
                    self._packages_total = 0
                    self._packages_processed = 0

                    package_result = await client.api_query(
                        mgmt_name,
                        "show-packages",
                        domain=domain_name,
                        container_key="packages",
                    )

                    current_cached_at = datetime.now(UTC)
                    if existing:
                        await session.execute(
                            update(CachedDomain)
                            .where(col(CachedDomain.uid) == domain_uid)
                            .values(
                                name=domain_name,
                                last_published_session=current_published_session,
                                cached_at=current_cached_at,
                            )
                        )
                    else:
                        session.add(
                            CachedDomain(
                                uid=domain_uid,
                                name=domain_name,
                                last_published_session=current_published_session,
                                cached_at=current_cached_at,
                            )
                        )

                    # Replace package cache only for domains that are new/changed (or need repair).
                    await session.execute(
                        delete(CachedSectionAssignment).where(
                            col(CachedSectionAssignment.domain_uid) == domain_uid
                        )
                    )
                    await session.execute(
                        delete(CachedPackage).where(col(CachedPackage.domain_uid) == domain_uid)
                    )

                    if package_result.success:
                        packages = package_result.objects or []
                        self._packages_total = len(packages)
                        for package_obj in packages:
                            package = CachedPackage(
                                uid=package_obj.get("uid", ""),
                                domain_uid=domain_uid,
                                name=package_obj.get("name", ""),
                                access_layer=package_obj.get("access-layer", ""),
                                cached_at=datetime.now(UTC),
                            )
                            session.add(package)
                            self._packages_processed += 1
                    else:
                        logger.error(
                            "Failed to fetch packages for domain %s: %s",
                            domain_name,
                            package_result.message,
                        )

                    await session.commit()
                    self._domains_processed += 1

                # Delete domains that are no longer in the API response
                for uid, domain in existing_domains.items():
                    if uid not in processed_uids:
                        logger.info(f"Removing domain: {domain['name']} (no longer exists)")
                        await session.execute(
                            delete(CachedSectionAssignment).where(
                                col(CachedSectionAssignment.domain_uid) == uid
                            )
                        )
                        await session.execute(
                            delete(CachedPackage).where(col(CachedPackage.domain_uid) == uid)
                        )
                        await session.execute(
                            delete(CachedDomain).where(col(CachedDomain.uid) == uid)
                        )

                await session.commit()
                self._current_domain_name = None

    def start_sections_refresh(self, username: str, password: str, mgmt_ip: str) -> None:
        """Warm section cache in the background if not already running."""
        if self._sections_task and not self._sections_task.done():
            logger.info("Background sections refresh already in progress")
            return

        self._sections_task = asyncio.create_task(
            self._refresh_all_sections_background(username, password, mgmt_ip)
        )
        self._sections_task.add_done_callback(self._handle_sections_task_done)

    def _handle_sections_task_done(self, task: asyncio.Task[None]) -> None:
        """Log background task failures and release the task reference."""
        self._sections_task = None
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("Background sections refresh task cancelled")
        except Exception:
            logger.exception("Background sections refresh failed")

    async def shutdown(self) -> None:
        """Cancel and await background tasks on application shutdown."""
        task = self._sections_task
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._sections_task = None

    async def _refresh_all_sections_background(
        self, username: str, password: str, mgmt_ip: str
    ) -> None:
        """Refresh missing sections for all cached packages in the background."""
        if self._sections_background_lock.locked():
            logger.info("Background sections refresh already running, skipping")
            return

        async with self._sections_background_lock:
            self._sections_refreshing = True
            try:
                package_contexts = await self._get_all_package_contexts()
                self._sections_total = len(package_contexts)
                self._sections_processed = 0
                if not package_contexts:
                    return

                async with CPAIOPSClient(
                    engine=engine,
                    username=username,
                    password=password,
                    mgmt_ip=mgmt_ip,
                ) as client:
                    server_names = client.get_mgmt_names()
                    if not server_names:
                        logger.warning("No management servers found for section refresh")
                        return

                    mgmt_name = server_names[0]
                    for context in package_contexts:
                        try:
                            cached_sections = await self.get_cached_sections(
                                context.domain_uid, context.package_uid
                            )
                            if not cached_sections:
                                await self._refresh_sections_for_context(client, mgmt_name, context)
                        except Exception:
                            logger.exception(
                                "Failed to refresh sections for domain=%s (uid=%s) package=%s (uid=%s)",
                                context.domain_name,
                                context.domain_uid,
                                context.package_name,
                                context.package_uid,
                            )
                        finally:
                            self._sections_processed += 1
            finally:
                self._sections_refreshing = False

    async def refresh_sections_for_package(
        self,
        username: str,
        password: str,
        mgmt_ip: str,
        domain_uid: str,
        package_uid: str,
    ) -> None:
        """Refresh sections for a single package immediately."""
        context = await self._get_package_context(domain_uid, package_uid)
        if context is None:
            logger.warning(
                "Cannot refresh sections for unknown package domain_uid=%s package_uid=%s",
                domain_uid,
                package_uid,
            )
            return

        async with CPAIOPSClient(
            engine=engine,
            username=username,
            password=password,
            mgmt_ip=mgmt_ip,
        ) as client:
            server_names = client.get_mgmt_names()
            if not server_names:
                logger.warning("No management servers found for package section refresh")
                return

            mgmt_name = server_names[0]
            await self._refresh_sections_for_context(client, mgmt_name, context)

        self.start_sections_refresh(username, password, mgmt_ip)

    async def _refresh_sections_for_context(
        self, client: CPAIOPSClient, mgmt_name: str, context: PackageContext
    ) -> None:
        """Refresh sections for a single package context."""
        lock = await self._get_package_refresh_lock(context.domain_uid, context.package_uid)
        if lock.locked():
            logger.info(
                "Section refresh already in progress for domain=%s package=%s; waiting (timeout=15s)",
                context.domain_name,
                context.package_name,
            )
            try:
                # Wait for the lock with a 15-second timeout
                async with asyncio.timeout(15):
                    async with lock:
                        return
            except TimeoutError:
                logger.warning(
                    "Timeout waiting for section refresh lock for domain=%s package=%s; proceeding anyway",
                    context.domain_name,
                    context.package_name,
                )
                # Proceed without the lock - the other task may have stalled

        async with lock:
            sections = await self._fetch_sections_from_api(client, mgmt_name, context)
            async with AsyncSession(engine) as session:
                assignment_domain_uid_col = col(CachedSectionAssignment.domain_uid)
                assignment_package_uid_col = col(CachedSectionAssignment.package_uid)
                await session.execute(
                    delete(CachedSectionAssignment)
                    .where(assignment_domain_uid_col == context.domain_uid)
                    .where(assignment_package_uid_col == context.package_uid)
                )

                seen_section_uids: set[str] = set()
                for section in sections:
                    section_uid = section["uid"]
                    if not section_uid:
                        logger.warning(
                            "Skipping section with empty uid in domain=%s (uid=%s) package=%s (uid=%s)",
                            context.domain_name,
                            context.domain_uid,
                            context.package_name,
                            context.package_uid,
                        )
                        continue

                    if section_uid in seen_section_uids:
                        logger.warning(
                            "Duplicate section uid=%s within domain=%s (uid=%s) package=%s (uid=%s); skipping duplicate entry",
                            section_uid,
                            context.domain_name,
                            context.domain_uid,
                            context.package_name,
                            context.package_uid,
                        )
                        continue

                    seen_section_uids.add(section_uid)
                    await self._store_section(session, context, section)

                await session.commit()

    async def _fetch_sections_from_api(
        self, client: CPAIOPSClient, mgmt_name: str, context: PackageContext
    ) -> list[dict[str, Any]]:
        """Fetch sections for a single package from Check Point."""
        pkg_result = await client.api_call(
            mgmt_name,
            "show-package",
            domain=context.domain_name,
            payload={"uid": context.package_uid},
        )

        if not pkg_result.success or not pkg_result.data:
            logger.debug(
                "No access details returned for domain=%s (uid=%s) package=%s (uid=%s) — likely a system/built-in package without an access rulebase",
                context.domain_name,
                context.domain_uid,
                context.package_name,
                context.package_uid,
            )
            return []

        package_data = pkg_result.data
        access_layer_id = package_data.get("access-layer")

        layers = package_data.get("access-layers", [])
        if isinstance(layers, list) and layers:
            domain_layers = [
                layer
                for layer in layers
                if isinstance(layer, dict)
                and layer.get("domain", {}).get("uid") == context.domain_uid
            ]
            if domain_layers:
                access_layer_id = domain_layers[0].get("uid") or domain_layers[0].get("name")
            elif not access_layer_id:
                access_layer_id = layers[0].get("uid") or layers[0].get("name")

        if not access_layer_id:
            logger.warning(
                "No access layer found for domain=%s (uid=%s) package=%s (uid=%s)",
                context.domain_name,
                context.domain_uid,
                context.package_name,
                context.package_uid,
            )
            return []

        layer_result = await client.api_query(
            mgmt_name,
            "show-access-rulebase",
            domain=context.domain_name,
            details_level="full",
            payload={"uid" if "-" in str(access_layer_id) else "name": access_layer_id},
            container_key="rulebase",
        )

        if not layer_result.success:
            logger.warning(
                "Failed to get rulebase for domain=%s (uid=%s) package=%s (uid=%s): %s",
                context.domain_name,
                context.domain_uid,
                context.package_name,
                context.package_uid,
                layer_result.message,
            )
            return []

        sections: list[dict[str, Any]] = []
        current_rule = 1

        def _as_int(value: Any) -> int | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                value = value.strip()
                if value.isdigit():
                    return int(value)
            return None

        def _pick_int(obj: dict[str, Any], keys: list[str]) -> int | None:
            for key in keys:
                if key in obj:
                    parsed = _as_int(obj.get(key))
                    if parsed is not None:
                        return parsed
            return None

        rulebase = layer_result.objects
        if not rulebase and isinstance(layer_result.data, dict):
            rulebase = layer_result.data.get("rulebase", [])
        elif not rulebase and isinstance(layer_result.data, list):
            rulebase = layer_result.data

        for rule in rulebase:
            if not isinstance(rule, dict):
                continue
            if rule.get("type") != "access-section":
                # Keep cursor aligned with top-level rule numbering when available.
                top_rule_num = _pick_int(rule, ["rule-number", "rule_number", "number"])
                if top_rule_num is not None:
                    current_rule = max(current_rule, top_rule_num + 1)
                continue

            section_rules = rule.get("rulebase", [])

            # Prefer explicit section bounds from API if present.
            section_min = _pick_int(rule, ["from", "from-rule", "from_rule"])
            section_max = _pick_int(rule, ["to", "to-rule", "to_rule"])

            # Fallback: infer bounds from nested rule numbers.
            if section_min is None or section_max is None:
                nested_nums: list[int] = []
                if isinstance(section_rules, list):
                    for nested_rule in section_rules:
                        if isinstance(nested_rule, dict):
                            nested_num = _pick_int(
                                nested_rule,
                                ["rule-number", "rule_number", "number"],
                            )
                            if nested_num is not None:
                                nested_nums.append(nested_num)
                if nested_nums:
                    section_min = min(nested_nums)
                    section_max = max(nested_nums)

            # Last fallback: sequential approximation.
            if section_min is None or section_max is None:
                section_min = current_rule
                if isinstance(section_rules, list) and len(section_rules) > 0:
                    section_max = current_rule + len(section_rules) - 1
                else:
                    # Empty sections must still advance cursor to avoid duplicate ranges.
                    section_max = section_min

            if section_max < section_min:
                section_max = section_min

            sections.append(
                {
                    "uid": rule.get("uid", ""),
                    "name": rule.get("name", ""),
                    "rulebase_range": json.dumps([section_min, section_max]),
                    "rule_count": len(section_rules),
                    "cached_at": datetime.now(UTC),
                }
            )
            current_rule = section_max + 1

        return sections

    async def _store_section(
        self,
        session: AsyncSession,
        context: PackageContext,
        section: dict[str, Any],
    ) -> None:
        """Insert or update a cached section and record its package assignment."""
        section_uid = section["uid"]
        section_uid_col = col(CachedSection.uid)
        existing_result = await session.execute(
            select(CachedSection).where(section_uid_col == section_uid)
        )
        existing = existing_result.scalar_one_or_none()
        existing_owner = await self._get_existing_section_owner(session, section_uid)

        if existing is None:
            session.add(
                CachedSection(
                    uid=section_uid,
                    name=section["name"],
                    rulebase_range=section["rulebase_range"],
                    rule_count=section["rule_count"],
                    cached_at=section["cached_at"],
                )
            )
        else:
            same_definition = (
                existing.name == section["name"]
                and existing.rulebase_range == section["rulebase_range"]
                and existing.rule_count == section["rule_count"]
            )
            if same_definition:
                if existing_owner is None:
                    logger.warning(
                        "Section uid=%s already cached; current domain=%s (uid=%s) package=%s (uid=%s). Skipping duplicate definition.",
                        section_uid,
                        context.domain_name,
                        context.domain_uid,
                        context.package_name,
                        context.package_uid,
                    )
                else:
                    logger.warning(
                        "Section uid=%s already cached in domain=%s (uid=%s) package=%s (uid=%s); current domain=%s (uid=%s) package=%s (uid=%s). Skipping duplicate definition.",
                        section_uid,
                        existing_owner["domain_name"],
                        existing_owner["domain_uid"],
                        existing_owner["package_name"],
                        existing_owner["package_uid"],
                        context.domain_name,
                        context.domain_uid,
                        context.package_name,
                        context.package_uid,
                    )
            else:
                if existing_owner is None:
                    logger.error(
                        "Conflicting cached section uid=%s for current domain=%s (uid=%s) package=%s (uid=%s); overriding stored definition.",
                        section_uid,
                        context.domain_name,
                        context.domain_uid,
                        context.package_name,
                        context.package_uid,
                    )
                else:
                    logger.error(
                        "Conflicting cached section uid=%s found in domain=%s (uid=%s) package=%s (uid=%s); current domain=%s (uid=%s) package=%s (uid=%s). Overriding stored definition.",
                        section_uid,
                        existing_owner["domain_name"],
                        existing_owner["domain_uid"],
                        existing_owner["package_name"],
                        existing_owner["package_uid"],
                        context.domain_name,
                        context.domain_uid,
                        context.package_name,
                        context.package_uid,
                    )

                existing.name = section["name"]
                existing.rulebase_range = section["rulebase_range"]
                existing.rule_count = section["rule_count"]
                existing.cached_at = section["cached_at"]
                session.add(existing)

        session.add(
            CachedSectionAssignment(
                domain_uid=context.domain_uid,
                package_uid=context.package_uid,
                section_uid=section_uid,
                cached_at=section["cached_at"],
            )
        )

    async def _get_existing_section_owner(
        self, session: AsyncSession, section_uid: str
    ) -> dict[str, str] | None:
        """Return one cached owner for an existing section UID."""
        assignment_section_uid_col = col(CachedSectionAssignment.section_uid)
        assignment_package_uid_col = col(CachedSectionAssignment.package_uid)
        assignment_domain_uid_col = col(CachedSectionAssignment.domain_uid)
        selected_domain_uid_col = col(CachedSectionAssignment.domain_uid)
        selected_domain_name_col = col(CachedDomain.name)
        selected_package_uid_col = col(CachedSectionAssignment.package_uid)
        selected_package_name_col = col(CachedPackage.name)
        package_uid_col = col(CachedPackage.uid)
        domain_uid_col = col(CachedDomain.uid)
        result = await session.execute(
            select(
                selected_domain_uid_col,
                selected_domain_name_col,
                selected_package_uid_col,
                selected_package_name_col,
            )
            .join(CachedPackage, package_uid_col == assignment_package_uid_col)
            .join(CachedDomain, domain_uid_col == assignment_domain_uid_col)
            .where(assignment_section_uid_col == section_uid)
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None

        domain_uid, domain_name, package_uid, package_name = row
        return {
            "domain_uid": domain_uid,
            "domain_name": domain_name,
            "package_uid": package_uid,
            "package_name": package_name,
        }

    async def _get_all_package_contexts(self) -> list[PackageContext]:
        """Return all cached package contexts."""
        async with AsyncSession(engine) as session:
            package_domain_uid_col = col(CachedPackage.domain_uid)
            domain_uid_col = col(CachedDomain.uid)
            result = await session.execute(
                select(CachedDomain, CachedPackage)
                .join(CachedPackage, package_domain_uid_col == domain_uid_col)
                .order_by(CachedDomain.name, CachedPackage.name)
            )
            return [
                PackageContext(
                    domain_uid=domain.uid,
                    domain_name=domain.name,
                    package_uid=package.uid,
                    package_name=package.name,
                )
                for domain, package in result.all()
            ]

    async def _get_package_context(
        self, domain_uid: str, package_uid: str
    ) -> PackageContext | None:
        """Return cached package context for a domain/package pair."""
        async with AsyncSession(engine) as session:
            package_domain_uid_col = col(CachedPackage.domain_uid)
            domain_uid_col = col(CachedDomain.uid)
            package_uid_col = col(CachedPackage.uid)
            result = await session.execute(
                select(CachedDomain, CachedPackage)
                .join(CachedPackage, package_domain_uid_col == domain_uid_col)
                .where(domain_uid_col == domain_uid)
                .where(package_uid_col == package_uid)
                .limit(1)
            )
            row = result.first()
            if row is None:
                return None

            domain, package = row
            return PackageContext(
                domain_uid=domain.uid,
                domain_name=domain.name,
                package_uid=package.uid,
                package_name=package.name,
            )

    async def _get_package_refresh_lock(self, domain_uid: str, package_uid: str) -> asyncio.Lock:
        """Return a shared lock for a package section refresh."""
        key = (domain_uid, package_uid)
        async with self._package_refresh_locks_guard:
            lock = self._package_refresh_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._package_refresh_locks[key] = lock
            return lock

    async def get_cached_domains(self) -> list[CachedDomain]:
        """Return all cached domains."""
        async with AsyncSession(engine) as session:
            result = await session.execute(select(CachedDomain).order_by(CachedDomain.name))
            return list(result.scalars().all())

    async def get_cached_packages(self, domain_uid: str) -> list[CachedPackage]:
        """Return cached packages for a domain."""
        package_domain_uid_col = col(CachedPackage.domain_uid)
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(CachedPackage)
                .where(package_domain_uid_col == domain_uid)
                .order_by(CachedPackage.name)
            )
            return list(result.scalars().all())

    async def get_cached_sections(self, domain_uid: str, pkg_uid: str) -> list[CachedSection]:
        """Return cached sections for a package."""
        assignment_domain_uid_col = col(CachedSectionAssignment.domain_uid)
        assignment_package_uid_col = col(CachedSectionAssignment.package_uid)
        section_uid_col = col(CachedSection.uid)
        assignment_section_uid_col = col(CachedSectionAssignment.section_uid)
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(CachedSection)
                .join(CachedSectionAssignment, section_uid_col == assignment_section_uid_col)
                .where(assignment_domain_uid_col == domain_uid)
                .where(assignment_package_uid_col == pkg_uid)
                .order_by(CachedSection.name)
            )
            sections = list(result.scalars().all())
            for section in sections:
                if isinstance(section.rulebase_range, str):
                    section.rulebase_range = json.loads(section.rulebase_range)
            return sections


# Singleton instance
cache_service = CacheService()
