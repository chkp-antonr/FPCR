import ipaddr from 'ipaddr.js';
import type { IpEntry, TopologyEntry, Prediction } from '../types';

export function ipMatchesSubnet(ip: IpEntry, subnets: string[]): boolean {
  for (const subnet of subnets) {
    try {
      // Handle CIDR entries (e.g., 10.76.192.0/24)
      if (ip.type === 'ipv4-cidr' || ip.type === 'ipv6-cidr') {
        const [ipAddr, ipMask] = ip.normalized.split('/');
        const ipPrefixLength = parseInt(ipMask, 10);

        if (subnet.includes('/')) {
          // Both are CIDR - check if they overlap
          const [subnetAddr, subnetMask] = subnet.split('/');
          const subnetPrefixLength = parseInt(subnetMask, 10);

          const parsedIpAddr = ipaddr.parse(ipAddr);
          const parsedSubnetAddr = ipaddr.parse(subnetAddr);

          if (parsedIpAddr.kind() === parsedSubnetAddr.kind()) {
            // Check if the IP entry's CIDR range overlaps with the subnet
            // For a match, the IP entry should be within or equal to the subnet
            if (ipPrefixLength >= subnetPrefixLength) {
              if (parsedSubnetAddr.match(parsedIpAddr, ipPrefixLength)) {
                return true;
              }
            } else {
              // IP entry has broader range - check if subnet is within IP entry
              if (parsedIpAddr.match(parsedSubnetAddr, subnetPrefixLength)) {
                return true;
              }
            }
          }
        } else {
          // Subnet is a single IP - check if it's within the CIDR range
          const parsedIpAddr = ipaddr.parse(ipAddr);
          const parsedSubnetAddr = ipaddr.parse(subnet);

          if (parsedIpAddr.kind() === parsedSubnetAddr.kind()) {
            if (parsedIpAddr.match(parsedSubnetAddr, ipPrefixLength)) {
              return true;
            }
          }
        }
      } else {
        // Handle plain IP entries
        const parsedIp = ipaddr.parse(ip.normalized);

        if (subnet.includes('/')) {
          // Use parseCIDR for CIDR notation
          const [addr, mask] = subnet.split('/');
          const subnetAddr = ipaddr.parse(addr);
          const prefixLength = parseInt(mask, 10);

          if (parsedIp.kind() === subnetAddr.kind()) {
            // match() checks if IP is within the subnet
            if (subnetAddr.match(parsedIp, prefixLength)) {
              return true;
            }
          }
        } else {
          // Exact match
          if (ip.normalized === subnet) {
            return true;
          }
        }
      }
    } catch (e) {
      // Invalid IP/subnet format, skip
      continue;
    }
  }
  return false;
}

export function generatePredictions(
  sourcePool: IpEntry[],
  destPool: IpEntry[],
  topology: TopologyEntry[]
): Prediction[] {
  const predictions: Prediction[] = [];

  // Process source pool
  for (const ip of sourcePool) {
    const candidates: Prediction['candidates'] = [];

    for (const entry of topology) {
      if (ipMatchesSubnet(ip, entry.subnets)) {
        candidates.push({
          domain: entry.domain,
          package: entry.package,
          firewall: entry.firewall,
          subnet: entry.subnets.find(s => ipMatchesSubnet(ip, [s])) || '',
          hostnames: entry.hosts || [],
          ip_hostnames: entry.ip_hostnames || {},
        });
      }
    }

    if (candidates.length > 0) {
      // Look up exact IP in ipHostnames map for precise matching
      let hostname: string | null = null;
      for (const c of candidates) {
        if (c.ip_hostnames[ip.normalized]) {
          hostname = c.ip_hostnames[ip.normalized];
          break;
        }
      }
      predictions.push({ ip, candidates, source: 'source', hostname });
    }
  }

  // Process dest pool
  for (const ip of destPool) {
    const candidates: Prediction['candidates'] = [];

    for (const entry of topology) {
      if (ipMatchesSubnet(ip, entry.subnets)) {
        candidates.push({
          domain: entry.domain,
          package: entry.package,
          firewall: entry.firewall,
          subnet: entry.subnets.find(s => ipMatchesSubnet(ip, [s])) || '',
          hostnames: entry.hosts || [],
          ip_hostnames: entry.ip_hostnames || {},
        });
      }
    }

    if (candidates.length > 0) {
      // Look up exact IP in ipHostnames map for precise matching
      let hostname: string | null = null;
      for (const c of candidates) {
        if (c.ip_hostnames[ip.normalized]) {
          hostname = c.ip_hostnames[ip.normalized];
          break;
        }
      }
      predictions.push({ ip, candidates, source: 'dest', hostname });
    }
  }

  return predictions;
}
