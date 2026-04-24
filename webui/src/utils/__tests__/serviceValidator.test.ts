import { validateServiceInput, findDuplicateServices } from '../serviceValidator';
import type { ServiceEntry } from '../../types';

describe('serviceValidator', () => {
  describe('validateServiceInput', () => {
    it('should parse https protocol', () => {
      const result = validateServiceInput('https');
      expect(result).toEqual([{
        original: 'https',
        normalized: 'https',
        type: 'protocol'
      }]);
    });

    it('should parse tcp-53 port format', () => {
      const result = validateServiceInput('tcp-53');
      expect(result).toEqual([{
        original: 'tcp-53',
        normalized: 'tcp-53',
        type: 'port'
      }]);
    });

    it('should parse comma separated values', () => {
      const result = validateServiceInput('https, tcp-53, udp-123');
      expect(result).toHaveLength(3);
      expect(result[2].normalized).toBe('udp-123');
    });

    it('should parse newline separated values', () => {
      const result = validateServiceInput('https\ntcp-53');
      expect(result).toHaveLength(2);
    });

    it('should handle "any" keyword', () => {
      const result = validateServiceInput('any');
      expect(result[0].type).toBe('any');
    });

    it('should handle named services', () => {
      const result = validateServiceInput('mysql, ssh');
      expect(result[0].type).toBe('named');
      expect(result[1].type).toBe('named');
    });

    it('should handle port numbers', () => {
      const result = validateServiceInput('443, 22');
      expect(result[0].type).toBe('port');
      expect(result[0].normalized).toBe('443');
    });

    it('should handle empty string', () => {
      const result = validateServiceInput('');
      expect(result).toEqual([]);
    });

    it('should handle whitespace only', () => {
      const result = validateServiceInput('   ');
      expect(result).toEqual([]);
    });

    it('should handle mixed delimiters', () => {
      const result = validateServiceInput('https; tcp-53\nudp');
      expect(result).toHaveLength(3);
    });

    it('should detect tcp-53 as port not protocol', () => {
      const result = validateServiceInput('tcp-53');
      expect(result[0].type).toBe('port');
    });
  });

  describe('findDuplicateServices', () => {
    it('should find duplicate services', () => {
      const entries: ServiceEntry[] = [
        { original: 'https', normalized: 'https', type: 'protocol' },
        { original: 'HTTPS', normalized: 'https', type: 'protocol' },
        { original: 'tcp-53', normalized: 'tcp-53', type: 'port' }
      ];
      const duplicates = findDuplicateServices(entries);
      expect(duplicates).toHaveLength(1);
      expect(duplicates[0].normalized).toBe('https');
    });
  });
});
