import type { ServiceEntry } from '../types';

export function validateServiceInput(input: string): ServiceEntry[] {
  const entries: ServiceEntry[] = [];
  const raw = input.split(/[\n,;\s\t]+/).filter(e => e.trim());

  for (const item of raw) {
    const normalized = item.toLowerCase().trim();

    let type: ServiceEntry['type'];
    if (normalized === 'any') {
      type = 'any';
    } else if (/^https?$/i.test(item)) {
      type = 'protocol';
    } else if (/^(tcp|udp)$/i.test(item)) {
      type = 'protocol';
    } else if (/^(tcp|udp)-\d+$/.test(normalized)) {
      type = 'port';
    } else if (/^\d+$/.test(item)) {
      type = 'port';
    } else {
      type = 'named';
    }

    entries.push({
      original: item,
      normalized,
      type,
    });
  }

  return entries;
}

export function findDuplicateServices(entries: ServiceEntry[]): ServiceEntry[] {
  const seen = new Set<string>();
  const duplicates: ServiceEntry[] = [];

  for (const entry of entries) {
    if (seen.has(entry.normalized)) {
      duplicates.push(entry);
    }
    seen.add(entry.normalized);
  }

  return duplicates;
}
