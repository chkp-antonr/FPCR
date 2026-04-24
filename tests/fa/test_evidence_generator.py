"""Tests for EvidenceGenerator."""

from datetime import UTC, datetime

import pytest

from fa.services.evidence_generator import EvidenceGenerator


@pytest.fixture
def generator():
    """Create EvidenceGenerator instance."""
    return EvidenceGenerator()


def test_generate_html_basic(generator):
    """Test basic HTML generation."""
    html = generator.generate_html(
        ritm_number="RITM1234567",
        created_at=datetime.now(UTC),
        engineer="a-johndoe",
        initials="JD",
        changes_by_domain=[],
        errors=None
    )

    assert "RITM1234567" in html
    assert "a-johndoe" in html
    assert "(JD)" in html
    assert "<html>" in html
    assert "</html>" in html


def test_generate_html_with_errors(generator):
    """Test HTML generation with errors."""
    html = generator.generate_html(
        ritm_number="RITM1234567",
        created_at=datetime.now(UTC),
        engineer="a-johndoe",
        initials="JD",
        changes_by_domain=[],
        errors=["Service not found", "Rule conflict"]
    )

    assert "Service not found" in html
    assert "Rule conflict" in html
    assert "errors" in html.lower()


def test_generate_yaml_basic(generator):
    """Test basic YAML generation."""
    yaml_str = generator.generate_yaml(
        mgmt_name="mgmt1",
        domain_name="Global",
        created_objects=[
            {
                "object_type": "host",
                "object_name": "Host_10.0.0.1",
                "input": "10.0.0.1"
            }
        ],
        created_rules=[]
    )

    assert "management_servers:" in yaml_str
    assert "mgmt_name: mgmt1" in yaml_str
    assert "operation: add" in yaml_str
    assert "type: host" in yaml_str
