import { afterEach, describe, expect, it, vi } from 'vitest';

import { CSRF_COOKIE, CSRF_HEADER, createApiClient, readCookie } from './client';

function recordingFetch() {
  const requests: Request[] = [];
  const fetch = vi.fn((input: Request) => {
    requests.push(input);
    return Promise.resolve(
      new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } }),
    );
  });
  return { fetch, requests };
}

afterEach(() => {
  document.cookie = `${CSRF_COOKIE}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
});

describe('readCookie', () => {
  it('finds a cookie among others and decodes it', () => {
    expect(readCookie('b', 'a=1; b=x%3Dy; c=3')).toBe('x=y');
    expect(readCookie('d', 'a=1')).toBeUndefined();
  });
});

describe('the API client', () => {
  it('calls the typed routes of the generated schema', async () => {
    const { fetch, requests } = recordingFetch();
    const client = createApiClient({ baseUrl: 'http://riso.test', fetch });
    const { data } = await client.GET('/api/entities');
    expect(data).toEqual([]);
    expect(requests[0]?.url).toBe('http://riso.test/api/entities');
  });

  it('sends the CSRF token on unsafe methods only', async () => {
    document.cookie = `${CSRF_COOKIE}=token-123`;
    const { fetch, requests } = recordingFetch();
    const client = createApiClient({ baseUrl: 'http://riso.test', fetch });
    await client.GET('/api/entities');
    await client.POST('/api/feedback', { body: {} as never });
    expect(requests[0]?.headers.get(CSRF_HEADER)).toBeNull();
    expect(requests[1]?.headers.get(CSRF_HEADER)).toBe('token-123');
  });

  it('sends no CSRF header without the cookie', async () => {
    const { fetch, requests } = recordingFetch();
    const client = createApiClient({ baseUrl: 'http://riso.test', fetch });
    await client.POST('/api/feedback', { body: {} as never });
    expect(requests[0]?.headers.get(CSRF_HEADER)).toBeNull();
  });
});
