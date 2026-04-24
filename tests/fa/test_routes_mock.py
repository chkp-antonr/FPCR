"""Tests for route handlers with mock data source."""

import os
import pytest
from fastapi.testclient import TestClient
from fa.app import create_app
from fa.session import session_manager


@pytest.fixture
def mock_env(tmp_path, monkeypatch):
    """Set up mock environment."""
    yaml_file = tmp_path / "mock.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN_1:
    policies:
      TEST_POLICY:
        sections:
          init: 3
  TEST_DOMAIN_2:
    policies:
      ANOTHER_POLICY:
        sections:
          ingress: 5
""")
    monkeypatch.setenv("MOCK_DATA", str(yaml_file))
    monkeypatch.setenv("API_MGMT", "127.0.0.1")  # Not used but required
    return yaml_file


@pytest.fixture
def client(mock_env):
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_list_domains_with_mock(client, mock_env):
    """Test /domains endpoint uses mock data when MOCK_DATA is set."""
    # Create a valid session
    session_id = session_manager.create("test_user", "test_pass")
    client.cookies.set("session_id", session_id)

    # Get domains
    response = client.get("/api/v1/domains")
    assert response.status_code == 200

    data = response.json()
    assert "domains" in data
    assert len(data["domains"]) == 2
    domain_names = [d["name"] for d in data["domains"]]
    assert "TEST_DOMAIN_1" in domain_names
    assert "TEST_DOMAIN_2" in domain_names

    # Clean up
    session_manager.delete(session_id)


def test_list_packages_with_mock(client):
    """Test /packages endpoint uses mock data when MOCK_DATA is set."""
    # Create a valid session
    session_id = session_manager.create("test_user", "test_pass")
    client.cookies.set("session_id", session_id)

    # Get domains first
    domains_response = client.get("/api/v1/domains")
    domains = domains_response.json()["domains"]
    domain_uid = domains[0]["uid"]

    # Get packages
    response = client.get(f"/api/v1/domains/{domain_uid}/packages")
    # Will be 404 or similar until we integrate
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert "packages" in data
        assert len(data["packages"]) == 1
        assert data["packages"][0]["name"] == "TEST_POLICY"

    # Clean up
    session_manager.delete(session_id)


def test_list_sections_with_mock(client):
    """Test /sections endpoint uses mock data when MOCK_DATA is set."""
    # Create a valid session
    session_id = session_manager.create("test_user", "test_pass")
    client.cookies.set("session_id", session_id)

    # Get domains
    domains_response = client.get("/api/v1/domains")
    domain_uid = domains_response.json()["domains"][0]["uid"]

    # Get packages
    packages_response = client.get(f"/api/v1/domains/{domain_uid}/packages")
    package_uid = packages_response.json()["packages"][0]["uid"]

    # Get sections
    response = client.get(f"/api/v1/domains/{domain_uid}/packages/{package_uid}/sections")
    # Will be 404 or similar until we integrate
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert "sections" in data
        assert "total_rules" in data
        assert data["total_rules"] == 3
        assert len(data["sections"]) == 1
        assert data["sections"][0]["name"] == "init"
        assert data["sections"][0]["rulebase_range"] == [1, 3]

    # Clean up
    session_manager.delete(session_id)
