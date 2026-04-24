import type { RuleRow, IpEntry } from '../types';

export interface ValidationError {
  ruleId: string;
  field: string;
  message: string;
}

export function validateRules(rules: RuleRow[]): ValidationError[] {
  const errors: ValidationError[] = [];

  for (let i = 0; i < rules.length; i++) {
    const rule = rules[i];

    if (!rule.domain) {
      errors.push({
        ruleId: rule.id,
        field: 'domain',
        message: `Row ${i + 1}: Domain is required`,
      });
    }

    if (!rule.package) {
      errors.push({
        ruleId: rule.id,
        field: 'package',
        message: `Row ${i + 1}: Package is required`,
      });
    }

    if (rule.sourceIps.length === 0) {
      errors.push({
        ruleId: rule.id,
        field: 'sourceIps',
        message: `Row ${i + 1}: At least one source IP is required`,
      });
    }

    if (rule.destIps.length === 0) {
      errors.push({
        ruleId: rule.id,
        field: 'destIps',
        message: `Row ${i + 1}: At least one destination IP is required`,
      });
    }

    if (rule.position.type === 'custom' && !rule.position.custom_number) {
      errors.push({
        ruleId: rule.id,
        field: 'position',
        message: `Row ${i + 1}: Custom position number is required`,
      });
    }
  }

  return errors;
}

export function hasUnusedIps(
  rules: RuleRow[],
  sourcePool: IpEntry[],
  destPool: IpEntry[]
): { source: IpEntry[]; dest: IpEntry[] } {
  const usedSourceIps = new Set(
    rules.flatMap(r => r.sourceIps.map(ip => ip.normalized.toLowerCase()))
  );
  const usedDestIps = new Set(
    rules.flatMap(r => r.destIps.map(ip => ip.normalized.toLowerCase()))
  );

  const unusedSource = sourcePool.filter(ip => !usedSourceIps.has(ip.normalized.toLowerCase()));
  const unusedDest = destPool.filter(ip => !usedDestIps.has(ip.normalized.toLowerCase()));

  return { source: unusedSource, dest: unusedDest };
}
