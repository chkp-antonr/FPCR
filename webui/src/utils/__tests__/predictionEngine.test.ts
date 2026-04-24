import { generatePredictions, ipMatchesSubnet } from '../predictionEngine';
import type { IpEntry, TopologyEntry } from '../../types';

describe('predictionEngine', () => {
  const mockTopology: TopologyEntry[] = [
    {
      domain: { name: 'AME_CORP', uid: 'domain-1' },
      package: { name: 'US-NY-CORP', uid: 'pkg-1', access_layer: 'network' },
      firewall: 'USNY-CORP-FW-1',
      subnets: ['10.76.64.0/24', '10.76.65.0/24']
    },
    {
      domain: { name: 'APA_CORP', uid: 'domain-2' },
      package: { name: 'JP-TOK-CORP', uid: 'pkg-2', access_layer: 'network' },
      firewall: 'APTOK-CORP-FW-1',
      subnets: ['10.76.192.0/24']
    }
  ];

  describe('ipMatchesSubnet', () => {
    it('should match IP in subnet', () => {
      const ip: IpEntry = {
        original: '10.76.64.11',
        normalized: '10.76.64.11',
        type: 'ipv4'
      };
      const result = ipMatchesSubnet(ip, ['10.76.64.0/24']);
      expect(result).toBe(true);
    });

    it('should not match IP outside subnet', () => {
      const ip: IpEntry = {
        original: '10.76.100.11',
        normalized: '10.76.100.11',
        type: 'ipv4'
      };
      const result = ipMatchesSubnet(ip, ['10.76.64.0/24']);
      expect(result).toBe(false);
    });

    it('should match exact IP', () => {
      const ip: IpEntry = {
        original: '10.76.64.11',
        normalized: '10.76.64.11',
        type: 'ipv4'
      };
      const result = ipMatchesSubnet(ip, ['10.76.64.11']);
      expect(result).toBe(true);
    });
  });

  describe('generatePredictions', () => {
    it('should generate predictions for matching IPs', () => {
      const sourcePool: IpEntry[] = [
        { original: '10.76.64.11', normalized: '10.76.64.11', type: 'ipv4' }
      ];
      const destPool: IpEntry[] = [
        { original: '10.76.192.5', normalized: '10.76.192.5', type: 'ipv4' }
      ];

      const predictions = generatePredictions(sourcePool, destPool, mockTopology);

      expect(predictions).toHaveLength(2);
      expect(predictions[0].ip.normalized).toBe('10.76.64.11');
      expect(predictions[0].candidates).toHaveLength(1);
      expect(predictions[0].candidates[0].domain.name).toBe('AME_CORP');
    });

    it('should handle IPs with no matches', () => {
      const sourcePool: IpEntry[] = [
        { original: '192.168.1.1', normalized: '192.168.1.1', type: 'ipv4' }
      ];
      const destPool: IpEntry[] = [];

      const predictions = generatePredictions(sourcePool, destPool, mockTopology);

      expect(predictions).toHaveLength(0);
    });

    it('should handle multiple candidates for same IP', () => {
      const sourcePool: IpEntry[] = [
        { original: '10.76.65.10', normalized: '10.76.65.10', type: 'ipv4' }
      ];
      const topologyWithOverlap: TopologyEntry[] = [
        ...mockTopology,
        {
          domain: { name: 'AME_DC', uid: 'domain-3' },
          package: { name: 'US-NY-DC', uid: 'pkg-3', access_layer: 'network' },
          firewall: 'USNY-DC-FW-1',
          subnets: ['10.76.65.0/24']
        }
      ];

      const predictions = generatePredictions(sourcePool, [], topologyWithOverlap);

      expect(predictions[0].candidates).toHaveLength(2);
    });
  });

  describe('generatePredictions with hostnames', () => {
    const topologyWithHosts: TopologyEntry[] = [
      {
        domain: { name: 'AME_CORP', uid: '1' },
        package: { name: 'US-NY-CORP', uid: '2', access_layer: 'network' },
        firewall: 'USNY-CORP-FW-1',
        subnets: ['10.76.64.0/24'],
        hosts: ['USNY-CORP-WST-1', 'USNY-CORP-WST-2']
      }
    ];

    it('includes hostname when IP matches topology entry with hosts', () => {
      const sourcePool: IpEntry[] = [
        { original: '10.76.64.10', type: 'ipv4', normalized: '10.76.64.10' }
      ];
      const destPool: IpEntry[] = [];

      const predictions = generatePredictions(sourcePool, destPool, topologyWithHosts);

      expect(predictions).toHaveLength(1);
      expect(predictions[0].hostname).toBe('USNY-CORP-WST-1');
      expect(predictions[0].candidates[0].hostnames).toEqual(['USNY-CORP-WST-1', 'USNY-CORP-WST-2']);
    });

    it('returns null hostname when no hosts match', () => {
      const topologyWithoutHosts: TopologyEntry[] = [
        {
          domain: { name: 'AME_CORP', uid: '1' },
          package: { name: 'US-NY-CORP', uid: '2', access_layer: 'network' },
          firewall: 'USNY-CORP-FW-1',
          subnets: ['10.76.64.0/24'],
          hosts: []
        }
      ];

      const sourcePool: IpEntry[] = [
        { original: '10.76.64.10', type: 'ipv4', normalized: '10.76.64.10' }
      ];
      const destPool: IpEntry[] = [];

      const predictions = generatePredictions(sourcePool, destPool, topologyWithoutHosts);

      expect(predictions).toHaveLength(1);
      expect(predictions[0].hostname).toBeNull();
    });

    it('handles empty hosts array', () => {
      const predictions = generatePredictions([], [], topologyWithHosts);
      expect(predictions).toHaveLength(0);
    });
  });
});
