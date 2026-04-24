"""Tests for MockDataSource."""

import uuid
import pytest
from fa.mock_source import MockDataSource


def test_mock_data_source_init_with_yaml(tmp_path):
    """Test MockDataSource initializes with YAML file."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))
    assert mock.data is not None
    assert "TEST_DOMAIN" in mock.data.get("domains", {})


def test_mock_data_source_init_with_json(tmp_path):
    """Test MockDataSource initializes with JSON file."""
    json_file = tmp_path / "test.json"
    json_file.write_text('{"domains": {"TEST_DOMAIN": {"policies": {"TEST_POLICY": {"sections": {"init": 3}}}}}}')
    mock = MockDataSource(str(json_file))
    assert mock.data is not None
    assert "TEST_DOMAIN" in mock.data.get("domains", {})


def test_auto_generate_domain_uids(tmp_path):
    """Test that UIDs are auto-generated for domains."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))
    domains = mock.get_domains()

    assert len(domains) == 1
    assert domains[0].name == "TEST_DOMAIN"
    assert domains[0].uid is not None
    # Should be a valid UUID string
    uuid.UUID(domains[0].uid)  # Raises ValueError if invalid


def test_uids_consistent_across_calls(tmp_path):
    """Test that same UID is returned on subsequent calls."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))
    domains1 = mock.get_domains()
    domains2 = mock.get_domains()

    assert domains1[0].uid == domains2[0].uid


def test_get_packages_for_domain(tmp_path):
    """Test getting packages for a specific domain."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  DOMAIN_1:
    policies:
      POLICY_A:
        sections:
          init: 3
  DOMAIN_2:
    policies:
      POLICY_B:
        sections:
          init: 5
""")
    mock = MockDataSource(str(yaml_file))
    domain_uid = mock._get_domain_uid("DOMAIN_1")

    packages = mock.get_packages(domain_uid)

    assert len(packages) == 1
    assert packages[0].name == "POLICY_A"
    assert packages[0].uid is not None


def test_get_packages_unknown_domain(tmp_path):
    """Test getting packages for unknown domain returns empty list."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  DOMAIN_1:
    policies:
      POLICY_A:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))

    packages = mock.get_packages("unknown-uid")

    assert len(packages) == 0


def test_get_sections_with_sequential_ranges(tmp_path):
    """Test that sections have sequential rulebase ranges."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
          ingress: 5
          egress: 2
""")
    mock = MockDataSource(str(yaml_file))
    domain_uid = mock._get_domain_uid("TEST_DOMAIN")
    policy_uid = mock._get_policy_uid("TEST_DOMAIN", "TEST_POLICY")

    sections, total = mock.get_sections(domain_uid, policy_uid)

    assert len(sections) == 3
    # init: rules 1-3 (3 rules)
    assert sections[0].name == "init"
    assert sections[0].rulebase_range == (1, 3)
    assert sections[0].rule_count == 3
    # ingress: rules 4-8 (5 rules)
    assert sections[1].name == "ingress"
    assert sections[1].rulebase_range == (4, 8)
    assert sections[1].rule_count == 5
    # egress: rules 9-10 (2 rules)
    assert sections[2].name == "egress"
    assert sections[2].rulebase_range == (9, 10)
    assert sections[2].rule_count == 2
    # total rules
    assert total == 10


def test_get_sections_unknown_policy(tmp_path):
    """Test getting sections for unknown policy returns empty."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
domains:
  TEST_DOMAIN:
    policies:
      TEST_POLICY:
        sections:
          init: 3
""")
    mock = MockDataSource(str(yaml_file))

    sections, total = mock.get_sections("unknown", "unknown")

    assert len(sections) == 0
    assert total == 0


def test_missing_file_returns_empty_domains(tmp_path):
    """Test that missing file returns empty domain list."""
    mock = MockDataSource(str(tmp_path / "nonexistent.yaml"))
    domains = mock.get_domains()
    assert domains == []


def test_invalid_yaml_returns_empty_results(tmp_path):
    """Test that invalid YAML returns empty results gracefully."""
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text("domains: [invalid yaml structure")

    mock = MockDataSource(str(yaml_file))
    domains = mock.get_domains()
    # Should return empty, not crash
    assert domains == []
