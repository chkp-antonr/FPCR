import { validateRules, hasUnusedIps } from '../ruleValidator';
import type { RuleRow, IpEntry } from '../../types';

describe('ruleValidator', () => {
  const mockIpEntry: IpEntry = {
    original: '10.76.64.11',
    normalized: '10.76.64.11',
    type: 'ipv4'
  };

  const mockDomain = { name: 'AME_CORP', uid: 'domain-1' };
  const mockPackage = { name: 'US-NY-CORP', uid: 'pkg-1', access_layer: 'network' };
  const mockSection = { name: 'ingress', uid: 'sec-1', rulebase_range: [1, 10], rule_count: 5 };

  describe('validateRules', () => {
    it('should pass for valid rule', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [mockIpEntry],
        destIps: [mockIpEntry],
        domain: mockDomain,
        package: mockPackage,
        section: mockSection,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(0);
    });

    it('should fail when domain is missing', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [mockIpEntry],
        destIps: [mockIpEntry],
        domain: null,
        package: mockPackage,
        section: null,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(1);
      expect(errors[0].field).toBe('domain');
    });

    it('should fail when source IPs are empty', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [],
        destIps: [mockIpEntry],
        domain: mockDomain,
        package: mockPackage,
        section: null,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(1);
      expect(errors[0].field).toBe('sourceIps');
    });

    it('should fail when custom position has no number', () => {
      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [mockIpEntry],
        destIps: [mockIpEntry],
        domain: mockDomain,
        package: mockPackage,
        section: null,
        position: { type: 'custom' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const errors = validateRules(rules);
      expect(errors).toHaveLength(1);
      expect(errors[0].field).toBe('position');
    });
  });

  describe('hasUnusedIps', () => {
    it('should identify unused source IPs', () => {
      const sourcePool: IpEntry[] = [
        { ...mockIpEntry, normalized: '10.76.64.11' },
        { ...mockIpEntry, normalized: '10.76.64.12' }
      ];

      const rules: RuleRow[] = [{
        id: '1',
        sourceIps: [{ ...mockIpEntry, normalized: '10.76.64.11' }],
        destIps: [{ ...mockIpEntry, normalized: '10.76.65.5' }],
        domain: mockDomain,
        package: mockPackage,
        section: null,
        position: { type: 'top' },
        action: 'accept',
        track: 'log',
        services: []
      }];

      const unused = hasUnusedIps(rules, sourcePool, []);
      expect(unused.source).toHaveLength(1);
      expect(unused.source[0].normalized).toBe('10.76.64.12');
    });
  });
});
