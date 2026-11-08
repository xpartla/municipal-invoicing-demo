import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';

/**
 * Errors from the API (guide §6.5): 401, 403, 404, 409 and 429 carry `{detail, code}`; 422
 * carries `detail` as a list of `{loc, msg, type}`, like FastAPI's own validation errors.
 */

export interface FieldProblem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    readonly retryAfter?: number,
  ) {
    super(`API ${String(status)}`);
  }

  get code(): string | undefined {
    const body = this.body as { code?: unknown } | null;
    return typeof body?.code === 'string' ? body.code : undefined;
  }

  /** The 422 problems, field by field. */
  get problems(): FieldProblem[] {
    const detail = (this.body as { detail?: unknown } | null)?.detail;
    return Array.isArray(detail) ? (detail as FieldProblem[]) : [];
  }
}

/** The result of an openapi-fetch call, or an `ApiError`. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const retry = Number(response.headers.get('Retry-After'));
    throw new ApiError(response.status, error ?? null, Number.isFinite(retry) ? retry : undefined);
  }
  return data as T;
}

/** The field a 422 problem is about: `loc` without the leading `body`, dotted. */
export function fieldOf(problem: FieldProblem): string {
  const parts = problem.loc[0] === 'body' ? problem.loc.slice(1) : problem.loc;
  return parts.join('.');
}

/**
 * Puts a 422's problems on the form's fields, with the message `translate` gives for each
 * `type` (an i18n key under `errors.`). Problems about fields the form does not have go to
 * `root`. Returns whether anything was set.
 */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
  translate: (type: string, fallback: string) => string,
): boolean {
  if (!(error instanceof ApiError) || error.status !== 422) return false;
  for (const problem of error.problems) {
    const field = fieldOf(problem);
    const message = translate(problem.type, problem.msg);
    if ((fields as readonly string[]).includes(field)) {
      setError(field as Path<T>, { type: problem.type, message });
    } else {
      setError('root', { type: problem.type, message });
    }
  }
  return error.problems.length > 0;
}
