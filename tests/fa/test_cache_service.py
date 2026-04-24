"""Tests for cache service section deduplication and assignments."""

import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fa.app import init_database
from fa.cache_service import PackageContext, cache_service
from fa.db import engine
from fa.models import CachedDomain, CachedPackage, CachedSection, CachedSectionAssignment


async def _reset_cache_tables() -> None:
    """Clear cache tables between tests."""
    async with AsyncSession(engine) as session:
        await session.execute(delete(CachedSectionAssignment))
        await session.execute(delete(CachedSection))
        await session.execute(delete(CachedPackage))
        await session.execute(delete(CachedDomain))
        await session.commit()


@pytest.mark.asyncio
async def test_store_duplicate_section_adds_second_assignment(caplog: pytest.LogCaptureFixture) -> None:
    """Identical section UIDs across packages should reuse the section and keep both assignments."""
    await init_database()
    await _reset_cache_tables()

    context_one = PackageContext(
        domain_uid="domain-1",
        domain_name="Domain One",
        package_uid="package-1",
        package_name="Package One",
    )
    context_two = PackageContext(
        domain_uid="domain-2",
        domain_name="Domain Two",
        package_uid="package-2",
        package_name="Package Two",
    )
    section = {
        "uid": "section-1",
        "name": "Shared Section",
        "rulebase_range": "[1, 2]",
        "rule_count": 2,
        "cached_at": datetime.now(UTC),
    }

    async with AsyncSession(engine) as session:
        session.add(CachedDomain(uid=context_one.domain_uid, name=context_one.domain_name))
        session.add(CachedDomain(uid=context_two.domain_uid, name=context_two.domain_name))
        session.add(
            CachedPackage(
                uid=context_one.package_uid,
                domain_uid=context_one.domain_uid,
                name=context_one.package_name,
                access_layer="layer-1",
            )
        )
        session.add(
            CachedPackage(
                uid=context_two.package_uid,
                domain_uid=context_two.domain_uid,
                name=context_two.package_name,
                access_layer="layer-2",
            )
        )
        await session.commit()

    with caplog.at_level(logging.WARNING):
        async with AsyncSession(engine) as session:
            await cache_service._store_section(session, context_one, section)
            await cache_service._store_section(session, context_two, section)
            await session.commit()

    async with AsyncSession(engine) as session:
        sections = list((await session.execute(select(CachedSection))).scalars().all())
        assignments = list((await session.execute(select(CachedSectionAssignment))).scalars().all())

    cached_for_one = await cache_service.get_cached_sections(context_one.domain_uid, context_one.package_uid)
    cached_for_two = await cache_service.get_cached_sections(context_two.domain_uid, context_two.package_uid)

    assert len(sections) == 1
    assert len(assignments) == 2
    assert len(cached_for_one) == 1
    assert len(cached_for_two) == 1
    assert "already cached in domain=Domain One" in caplog.text


@pytest.mark.asyncio
async def test_store_conflicting_section_overrides_definition(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Conflicting section definitions should log and replace the canonical section."""
    await init_database()
    await _reset_cache_tables()

    context_one = PackageContext(
        domain_uid="domain-1",
        domain_name="Domain One",
        package_uid="package-1",
        package_name="Package One",
    )
    context_two = PackageContext(
        domain_uid="domain-2",
        domain_name="Domain Two",
        package_uid="package-2",
        package_name="Package Two",
    )

    async with AsyncSession(engine) as session:
        session.add(CachedDomain(uid=context_one.domain_uid, name=context_one.domain_name))
        session.add(CachedDomain(uid=context_two.domain_uid, name=context_two.domain_name))
        session.add(
            CachedPackage(
                uid=context_one.package_uid,
                domain_uid=context_one.domain_uid,
                name=context_one.package_name,
                access_layer="layer-1",
            )
        )
        session.add(
            CachedPackage(
                uid=context_two.package_uid,
                domain_uid=context_two.domain_uid,
                name=context_two.package_name,
                access_layer="layer-2",
            )
        )
        await session.commit()

    original = {
        "uid": "section-1",
        "name": "Shared Section",
        "rulebase_range": "[1, 2]",
        "rule_count": 2,
        "cached_at": datetime.now(UTC),
    }
    conflicting = {
        "uid": "section-1",
        "name": "Shared Section Updated",
        "rulebase_range": "[10, 12]",
        "rule_count": 3,
        "cached_at": datetime.now(UTC),
    }

    with caplog.at_level(logging.ERROR):
        async with AsyncSession(engine) as session:
            await cache_service._store_section(session, context_one, original)
            await cache_service._store_section(session, context_two, conflicting)
            await session.commit()

    async with AsyncSession(engine) as session:
        stored = (await session.execute(select(CachedSection))).scalar_one()
        assignments = list((await session.execute(select(CachedSectionAssignment))).scalars().all())

    assert stored.name == "Shared Section Updated"
    assert stored.rulebase_range == "[10, 12]"
    assert stored.rule_count == 3
    assert len(assignments) == 2
    assert "Conflicting cached section uid=section-1" in caplog.text