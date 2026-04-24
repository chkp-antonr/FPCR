"""Tests for MockDataSource hostname population in topology."""

from ..mock_source import MockDataSource


def test_topology_with_single_host_in_subnet(tmp_path):
    """Single host IP within subnet gets added to TopologyEntry.hosts"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24

hosts:
  USNY-CORP-WST-1: 10.76.64.10
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert topology[0].firewall == "USNY-CORP-FW-1"
    assert topology[0].hosts == ["USNY-CORP-WST-1"]


def test_topology_with_multiple_hosts_in_subnet(tmp_path):
    """Multiple hosts in same subnet all added to hosts array"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24

hosts:
  USNY-CORP-WST-1: 10.76.64.10
  USNY-CORP-WST-2: 10.76.64.11
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert set(topology[0].hosts) == {"USNY-CORP-WST-1", "USNY-CORP-WST-2"}


def test_topology_host_not_in_any_subnet(tmp_path):
    """Host IP not matching any subnet is not included"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24

hosts:
  DIFFERENT-HOST: 192.168.1.10
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert topology[0].hosts == []


def test_topology_with_no_hosts_section(tmp_path):
    """Missing hosts section returns empty hosts arrays"""
    mock_data = tmp_path / "test.yaml"
    mock_data.write_text("""
domains:
  AME_CORP:
    policies:
      US-NY-CORP:
        firewalls:
          USNY-CORP-FW-1:
            subnets:
              - 10.76.64.0/24
""")

    mock = MockDataSource(str(mock_data))
    topology = mock.get_topology()

    assert len(topology) == 1
    assert topology[0].hosts == []
