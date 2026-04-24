import { describe, it, expect } from 'vitest';
import { validateIpInput } from '../ipValidator';

describe('ipValidator', () => {
  it('accepts Check Point prefixed network entries', () => {
    const entries = validateIpInput('n_10.76.192.0/24');

    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({
      original: 'n_10.76.192.0/24',
      normalized: 'n_10.76.192.0/24',
      type: 'prefixed',
    });
  });

  it('accepts Check Point prefixed host entries', () => {
    const entries = validateIpInput('h_2.2.2.2');

    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({
      original: 'h_2.2.2.2',
      normalized: 'h_2.2.2.2',
      type: 'prefixed',
    });
  });

  it('accepts Check Point prefixed range entries', () => {
    const entries = validateIpInput('ipr_192.168.1.0-192.168.1.7');

    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({
      original: 'ipr_192.168.1.0-192.168.1.7',
      normalized: 'ipr_192.168.1.0-192.168.1.7',
      type: 'prefixed',
    });
  });

  it('accepts mixed standard and prefixed entries', () => {
    const entries = validateIpInput('10.76.64.10, 10.76.64.11, n_10.76.192.0/24, h_2.2.2.2, ipr_192.168.1.0-192.168.1.7');

    expect(entries).toHaveLength(5);
    expect(entries.map(e => e.normalized)).toEqual([
      '10.76.64.10',
      '10.76.64.11',
      'n_10.76.192.0/24',
      'h_2.2.2.2',
      'ipr_192.168.1.0-192.168.1.7',
    ]);
  });

  it('rejects prefixed entries when suffix is not IP-like', () => {
    const entries = validateIpInput('h_not-an-ip');

    expect(entries).toHaveLength(0);
  });
});
