import ipaddr from 'ipaddr.js';
import type { IpEntry } from '../types';

const SEPARATORS = /[\n,;\s\t]+/;

export function validateIpInput(input: string): IpEntry[] {
  if (!input.trim()) {
    return [];
  }

  const entries: IpEntry[] = [];
  const rawEntries = input.split(SEPARATORS).filter(e => e.trim());

  for (const raw of rawEntries) {
    const entry = parseIpEntry(raw.trim());
    if (entry) {
      entries.push(entry);
    }
  }

  return entries;
}

function parseIpEntry(input: string): IpEntry | null {
  const lower = input.toLowerCase();

  // Handle Check Point style prefixed objects, e.g. n_10.0.0.0/24, h_1.1.1.1, ipr_1.1.1.1-1.1.1.10
  const prefixedMatch = input.match(/^([a-z][a-z0-9-]*)_(.+)$/i);
  if (prefixedMatch) {
    const rawValue = prefixedMatch[2].trim().replace(/\u2013|\u2014/g, '-');

    // Fast path for IP-like payloads to avoid dropping valid pasted values.
    if (/^(?=.*\d)[0-9a-fA-F:.\/-]+$/.test(rawValue)) {
      return { original: input, type: 'prefixed', normalized: input };
    }

    // Prefixed objects should only wrap IP-like payloads (IP, CIDR, range).
    if (rawValue.includes('-')) {
      const parts = rawValue.split('-');
      if (parts.length === 2) {
        try {
          const startIp = ipaddr.parse(parts[0].trim());
          const endIp = ipaddr.parse(parts[1].trim());
          if (startIp.kind() === endIp.kind()) {
            return { original: input, type: 'prefixed', normalized: input };
          }
        } catch {
          return null;
        }
      }
      return null;
    }

    if (rawValue.includes('/')) {
      try {
        ipaddr.parseCIDR(rawValue);
        return { original: input, type: 'prefixed', normalized: input };
      } catch {
        return null;
      }
    }

    try {
      ipaddr.parse(rawValue);
      return { original: input, type: 'prefixed', normalized: input };
    } catch {
      return null;
    }
  }

  // Handle 'any'
  if (lower === 'any') {
    return { original: input, type: 'any', normalized: 'any' };
  }

  // Handle FQDN with wildcard
  if (lower.startsWith('*.')) {
    return { original: input, type: 'fqdn', normalized: input };
  }

  // Handle FQDN (RFC 1035: labels max 63 chars, must start/end with alphanumeric)
  // This regex enforces: 1-63 chars per label, alphanumeric start/end, hyphens allowed internally
  if (/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$/i.test(input)) {
    return { original: input, type: 'fqdn', normalized: input };
  }

  // Handle range (x.x.x.x-y.y.y.y) - must be same IP version
  if (input.includes('-')) {
    const parts = input.split('-');
    if (parts.length === 2) {
      try {
        const startIp = ipaddr.parse(parts[0].trim());
        const endIp = ipaddr.parse(parts[1].trim());

        // Ensure both IPs are same version (IPv4 or IPv6)
        if (startIp.kind() !== endIp.kind()) {
          return null;
        }

        return { original: input, type: 'range', normalized: input };
      } catch {
        return null;
      }
    }
  }

  // Handle CIDR
  if (input.includes('/')) {
    try {
      const addr = ipaddr.parseCIDR(input);
      return {
        original: input,
        type: addr[0].kind() === 'ipv4' ? 'ipv4-cidr' : 'ipv6-cidr',
        normalized: input
      };
    } catch {
      return null;
    }
  }

  // Handle plain IP
  try {
    const addr = ipaddr.parse(input);
    return {
      original: input,
      type: addr.kind() === 'ipv4' ? 'ipv4' : 'ipv6',
      normalized: input
    };
  } catch {
    return null;
  }
}

export function findDuplicates(entries: IpEntry[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();

  for (const entry of entries) {
    const normalized = entry.normalized.toLowerCase();
    if (seen.has(normalized)) {
      duplicates.add(normalized);
    } else {
      seen.add(normalized);
    }
  }

  return Array.from(duplicates);
}

export function getFirstUnusedIp(pool: IpEntry[], usedIps: Set<string>): IpEntry | null {
  for (const entry of pool) {
    if (!usedIps.has(entry.normalized.toLowerCase())) {
      return entry;
    }
  }
  return null;
}
