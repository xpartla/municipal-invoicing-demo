import createClient, { type ClientOptions, type Middleware } from 'openapi-fetch';

import type { components, paths } from './schema';

/**
 * The typed API client, generated from the backend's OpenAPI document (`pnpm gen:api` after
 * `riso export-openapi`). Server data goes only through TanStack Query hooks in
 * `features/<context>/api.ts`, which call this client; nothing else calls `fetch`.
 */

export const CSRF_COOKIE = 'riso_csrf';
export const CSRF_HEADER = 'X-CSRF-Token';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function readCookie(name: string, cookies: string = document.cookie): string | undefined {
  for (const pair of cookies.split(';')) {
    const [key, ...rest] = pair.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return undefined;
}

/** Sends the CSRF token from its cookie on every unsafe request (plan §5.3, from P2-M1). */
export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (UNSAFE_METHODS.has(request.method)) {
      const token = readCookie(CSRF_COOKIE);
      if (token) request.headers.set(CSRF_HEADER, token);
    }
    return request;
  },
};

export function createApiClient(options: ClientOptions = {}) {
  const client = createClient<paths>({
    baseUrl: globalThis.location.origin,
    credentials: 'same-origin',
    // Looked up on every call, so the component tests can stub the global fetch.
    fetch: (request: Request) => globalThis.fetch(request),
    ...options,
  });
  client.use(csrfMiddleware);
  return client;
}

export const api = createApiClient();

export type Schemas = components['schemas'];
