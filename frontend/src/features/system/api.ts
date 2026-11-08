import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { ApiError, unwrap } from '../../lib/apiError';

/** Systém (plan §6.4–6.5, §10.7): the customer's parameters and conventions per year, and
 * the knowledge health report. */

export type Parameters = Schemas['ParametersOut'];
export type Conventions = Schemas['ConventionsOut'];
export type HealthReport = Schemas['HealthReportOut'];
export type HealthFinding = Schemas['HealthFindingOut'];

const key = (customerId: string, what: string, year: number) =>
  ['system', customerId, what, year] as const;

/** The parameters of the year; null while the customer has none (404). */
export function useParameters(customerId: string, year: number) {
  return useQuery({
    queryKey: key(customerId, 'parameters', year),
    queryFn: async () => {
      try {
        return await unwrap(
          api.GET('/api/customers/{customer_id}/parameters', {
            params: { path: { customer_id: customerId }, query: { year } },
          }),
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
}

export function useSaveParameters(customerId: string, year: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      unwrap(
        api.PUT('/api/customers/{customer_id}/parameters', {
          params: { path: { customer_id: customerId }, query: { year } },
          body: { values },
        }),
      ),
    onSuccess: async (saved) => {
      client.setQueryData(key(customerId, 'parameters', year), saved);
      await client.invalidateQueries({ queryKey: key(customerId, 'health', year) });
    },
  });
}

export function useConventions(customerId: string, year: number) {
  return useQuery({
    queryKey: key(customerId, 'conventions', year),
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/conventions', {
          params: { path: { customer_id: customerId }, query: { year } },
        }),
      ),
  });
}

export function useSaveConventions(customerId: string, year: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revision, document }: { revision: number; document: Record<string, unknown> }) =>
      unwrap(
        api.PUT('/api/customers/{customer_id}/conventions', {
          params: { path: { customer_id: customerId }, query: { year } },
          body: { revision, document },
        }),
      ),
    onSuccess: async (saved) => {
      client.setQueryData(key(customerId, 'conventions', year), saved);
      await client.invalidateQueries({ queryKey: key(customerId, 'health', year) });
    },
  });
}

export function useHealth(customerId: string, year: number) {
  return useQuery({
    queryKey: key(customerId, 'health', year),
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/health', {
          params: { path: { customer_id: customerId }, query: { year } },
        }),
      ),
  });
}
