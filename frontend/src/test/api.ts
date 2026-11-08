import { vi } from 'vitest';

/**
 * A stand-in for the backend in component tests: routes like `GET /api/me` answer with a
 * status and a body; anything else is a 404. The calls are recorded.
 */

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

interface Answer {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}
type Handler = Answer | ((call: Call) => Answer);

export function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const fetch = vi.fn(async (input: Request) => {
    const url = new URL(input.url);
    const text = input.method === 'GET' ? '' : await input.text();
    const call: Call = {
      method: input.method,
      path: url.pathname + url.search,
      body: text ? (JSON.parse(text) as unknown) : undefined,
    };
    calls.push(call);
    const handler = routes[`${call.method} ${url.pathname}`];
    const answer = typeof handler === 'function' ? handler(call) : (handler ?? { status: 404 });
    const status = answer.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(answer.body ?? {}), {
      status,
      headers: { 'Content-Type': 'application/json', ...answer.headers },
    });
  });
  vi.stubGlobal('fetch', fetch);
  return { calls, fetch };
}
