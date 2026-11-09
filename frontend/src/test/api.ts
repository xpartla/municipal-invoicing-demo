import { vi } from 'vitest';

/**
 * A stand-in for the backend in component tests: routes like `GET /api/me` answer with a
 * status and a body; anything else is a 404. The calls are recorded, a JSON body parsed and a
 * multipart one as its fields.
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
    const type = input.headers.get('Content-Type') ?? '';
    const text = input.method === 'GET' ? '' : await input.text();
    const body: unknown = type.startsWith('multipart/form-data')
      ? multipartFields(text, type)
      : text
        ? (JSON.parse(text) as unknown)
        : undefined;
    const call: Call = { method: input.method, path: url.pathname + url.search, body };
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

/** A multipart body's fields: text values as they are, a file as its name. */
function multipartFields(text: string, type: string): Record<string, string> {
  const boundary = /boundary=(.+)$/.exec(type)?.[1] ?? '';
  const fields: Record<string, string> = {};
  for (const part of text.split(`--${boundary}`)) {
    const name = /name="([^"]+)"/.exec(part)?.[1];
    if (!name) continue;
    const filename = /filename="([^"]*)"/.exec(part)?.[1];
    const value = part.split('\r\n\r\n').slice(1).join('\r\n\r\n').replace(/\r\n$/, '');
    fields[name] = filename ?? value;
  }
  return fields;
}
