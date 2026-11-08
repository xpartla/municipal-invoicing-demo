import { QueryClient } from '@tanstack/react-query';

/** Server state lives only in TanStack Query (guide §6.7). */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
    },
  });
}
