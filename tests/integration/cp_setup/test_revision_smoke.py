"""
Smoke test — not run in normal suite; invoke manually to verify revision
module works against your CP environment:

    uv run pytest tests/integration/cp_setup/test_revision_smoke.py -v -s
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.test")


@pytest.mark.skip(reason="Manual smoke test — requires live CP environment")
async def test_list_revisions_returns_list():
    """Verify list_revisions returns a list (may be empty on fresh server)."""
    from cpaiops import CPAIOPSClient

    from tests.integration.cp_setup.revision import list_revisions

    mgmt_ip = os.environ["API_MGMT"]
    username = os.environ["API_USERNAME"]
    password = os.environ["API_PASSWORD"]

    async with CPAIOPSClient(
        username=username,
        password=password,
        mgmt_ip=mgmt_ip,
    ) as client:
        mgmt_name = client.get_mgmt_names()[0]
        revisions = await list_revisions(client, mgmt_name)
        assert isinstance(revisions, list)
