import { MutationCache, QueryCache, QueryClient, type QueryKey } from '@tanstack/react-query';

import { ApiError } from '../lib/apiError';

/** Set when the session ended under a logged-in caller; the shell then sends them to the
 * login with a notice. A login removes it with the other queries, a logout with `clear()`. */
export const sessionExpiredKey = ['session-expired'] as const;

const ME: QueryKey = ['me'];

/**
 * A 401 while someone is logged in means the session ended: idle for 8 hours, the 7-day
 * limit, a logout elsewhere, or an admin's forced logout (plan §5.3). The caller becomes
 * nobody, so the shell sends them to the login, which brings them back afterwards. The 401s
 * of `/api/me` itself and of a failed login, while nobody is logged in, change nothing.
 */
function endedSession(client: QueryClient, error: unknown, key?: QueryKey): void {
  if (!(error instanceof ApiError) || error.status !== 401) return;
  if (key?.[0] === ME[0] || !client.getQueryData(ME)) return;
  client.setQueryData(sessionExpiredKey, true);
  client.setQueryData(ME, null);
}

/** Server state lives only in TanStack Query (guide §6.7). */
export function createQueryClient() {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        endedSession(client, error, query.queryKey);
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        endedSession(client, error);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // A 401, 403 or 404 does not change by asking again.
        retry: (count, error) =>
          count < 1 && !(error instanceof ApiError && [401, 403, 404].includes(error.status)),
        refetchOnWindowFocus: false,
      },
    },
  });
  return client;
}
