"""Tests for SessionChangesPDFGenerator."""

import pytest

from fa.services.session_changes_pdf import SessionChangesPDFGenerator


def test_generator_initialization() -> None:
    """Test that generator initializes correctly."""
    generator = SessionChangesPDFGenerator()
    assert generator is not None
    assert generator.env is not None


def test_generate_pdf_with_invalid_evidence_number() -> None:
    """Test that generate_pdf raises ValueError for invalid evidence_number."""
    generator = SessionChangesPDFGenerator()

    sample_changes = {
        "domain_changes": {
            "General": {
                "tasks": [
                    {
                        "task-details": [
                            {
                                "changes": [
                                    {
                                        "operations": {
                                            "added-objects": [],
                                            "modified-objects": [],
                                            "deleted-objects": [],
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }

    # Test invalid evidence numbers
    for invalid_num in [0, 3, -1, 99]:
        with pytest.raises(ValueError, match="evidence_number must be 1 or 2"):
            generator.generate_pdf(
                ritm_number="RITM1234567",
                evidence_number=invalid_num,
                username="testuser",
                session_changes=sample_changes,
            )


def test_parse_session_changes_with_sample_data() -> None:
    """Test parsing with sample session_changes data."""
    generator = SessionChangesPDFGenerator()

    sample_changes = {
        "domain_changes": {
            "General": {
                "tasks": [
                    {
                        "task-details": [
                            {
                                "changes": [
                                    {
                                        "operations": {
                                            "added-objects": [
                                                {
                                                    "uid": "test-uid-1",
                                                    "name": "Host_1.1.1.1",
                                                    "type": "host",
                                                    "ipv4-address": "1.1.1.1",
                                                    "domain": {"name": "General"},
                                                },
                                                {
                                                    "uid": "test-uid-2",
                                                    "name": "TestRule",
                                                    "type": "access-rule",
                                                    "position": 1,
                                                    "source": [{"name": "Host_1.1.1.1"}],
                                                    "destination": [{"name": "Any"}],
                                                    "service": [{"name": "https"}],
                                                    "install-on": [
                                                        {
                                                            "uid": "6c488338-8eec-4103-ad21-cd461ac2c476",
                                                            "name": "Policy Targets",
                                                        }
                                                    ],
                                                    "action": {"name": "Accept"},
                                                    "track": {"type": {"name": "Log"}},
                                                    "layer": "test-layer",
                                                },
                                            ],
                                            "modified-objects": [],
                                            "deleted-objects": [],
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }

    domains = generator._parse_session_changes(sample_changes)

    assert len(domains) == 1
    assert domains[0]["name"] == "General"
    assert domains[0]["package"] == "Standard"
    assert len(domains[0]["rules"]) == 1
    assert domains[0]["rules"][0]["name"] == "TestRule"
    assert domains[0]["rules"][0]["targets"] == ["Policy Targets"]
    assert len(domains[0]["objects"]["added"]["hosts"]) == 1
    assert domains[0]["objects"]["added"]["hosts"][0]["name"] == "Host_1.1.1.1"
    assert domains[0]["objects"]["added"]["hosts"][0]["ip"] == "1.1.1.1"


def test_generate_html_includes_targets_column_and_values() -> None:
    """HTML evidence should render Targets column populated from install-on names."""
    generator = SessionChangesPDFGenerator()

    sample_changes = {
        "domain_changes": {
            "General": {
                "tasks": [
                    {
                        "task-details": [
                            {
                                "changes": [
                                    {
                                        "operations": {
                                            "added-objects": [
                                                {
                                                    "uid": "test-uid-2",
                                                    "name": "TestRule",
                                                    "type": "access-rule",
                                                    "position": 1,
                                                    "source": [{"name": "Host_1.1.1.1"}],
                                                    "destination": [{"name": "Any"}],
                                                    "service": [{"name": "https"}],
                                                    "install-on": [
                                                        {
                                                            "uid": "6c488338-8eec-4103-ad21-cd461ac2c476",
                                                            "name": "Policy Targets",
                                                        }
                                                    ],
                                                    "action": {"name": "Accept"},
                                                    "track": {"type": {"name": "Log"}},
                                                    "layer": "test-layer",
                                                }
                                            ],
                                            "modified-objects": [],
                                            "deleted-objects": [],
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }

    html = generator.generate_html(
        ritm_number="RITM1234567",
        evidence_number=1,
        username="testuser",
        session_changes=sample_changes,
    )

    assert "<th>Targets</th>" in html
    assert "Policy Targets" in html


def test_generate_pdf_creates_pdf_bytes() -> None:
    """Test that generate_pdf returns PDF bytes."""
    generator = SessionChangesPDFGenerator()

    sample_changes = {
        "domain_changes": {
            "General": {
                "tasks": [
                    {
                        "task-details": [
                            {
                                "changes": [
                                    {
                                        "operations": {
                                            "added-objects": [
                                                {
                                                    "uid": "test-uid",
                                                    "name": "Host_1.1.1.1",
                                                    "type": "host",
                                                    "ipv4-address": "1.1.1.1",
                                                    "domain": {"name": "General"},
                                                }
                                            ],
                                            "modified-objects": [],
                                            "deleted-objects": [],
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }

    pdf_bytes = generator.generate_pdf(
        ritm_number="RITM1234567",
        evidence_number=1,
        username="testuser",
        session_changes=sample_changes,
    )

    # Verify we got bytes back
    assert isinstance(pdf_bytes, bytes)
    # Verify PDF header magic bytes
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_html_resolves_layer_uid_with_mapping() -> None:
    """Layer UID should render mapped section name instead of fallback."""
    generator = SessionChangesPDFGenerator()

    layer_uid = "5d4be65f-bbe8-491e-93ec-5a4a0cea4965"
    sample_changes = {
        "domain_changes": {
            "General": {
                "tasks": [
                    {
                        "task-details": [
                            {
                                "changes": [
                                    {
                                        "operations": {
                                            "added-objects": [
                                                {
                                                    "uid": "test-uid-2",
                                                    "name": "TestRule",
                                                    "type": "access-rule",
                                                    "position": 1,
                                                    "source": [{"name": "Host_1.1.1.1"}],
                                                    "destination": [{"name": "Any"}],
                                                    "service": [{"name": "https"}],
                                                    "install-on": [
                                                        {
                                                            "uid": "6c488338-8eec-4103-ad21-cd461ac2c476",
                                                            "name": "Policy Targets",
                                                        }
                                                    ],
                                                    "action": {"name": "Accept"},
                                                    "track": {"type": {"name": "Log"}},
                                                    "layer": layer_uid,
                                                }
                                            ],
                                            "modified-objects": [],
                                            "deleted-objects": [],
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }

    html = generator.generate_html(
        ritm_number="RITM1234567",
        evidence_number=1,
        username="testuser",
        session_changes=sample_changes,
        section_uid_to_name={layer_uid: "My Real Layer"},
    )

    assert "Section: My Real Layer" in html


def test_generate_empty_pdf_returns_valid_pdf() -> None:
    """Test that empty session_changes generates valid PDF."""
    generator = SessionChangesPDFGenerator()

    pdf_bytes = generator._generate_empty_pdf(
        ritm_number="RITM1234567",
        evidence_number=1,
        username="testuser",
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"



