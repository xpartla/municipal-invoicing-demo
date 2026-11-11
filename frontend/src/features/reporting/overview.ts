import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';
import { isMonth } from './dashboard';

/** Prehľad klientov and Platforma (plan §10.8, §10.9, decision 67). */

export type ProviderOverview = Schemas['OverviewOut'];
export type OverviewRow = Schemas['OverviewRowOut'];
export type PlatformCounts = Schemas['PlatformCountsOut'];

export function useProviderOverview(providerId: string | undefined, month: string) {
  return useQuery({
    queryKey: ['provider-overview', providerId, month],
    queryFn: () =>
      unwrap(
        api.GET('/api/providers/{provider_id}/overview', {
          params: { path: { provider_id: providerId ?? '' }, query: { month } },
        }),
      ),
    enabled: providerId !== undefined,
    placeholderData: keepPreviousData,
  });
}

export function usePlatformCounts(month: string) {
  return useQuery({
    queryKey: ['platform-counts', month],
    queryFn: () => unwrap(api.GET('/api/admin/overview', { params: { query: { month } } })),
    placeholderData: keepPreviousData,
  });
}

export interface OverviewSearch {
  month?: string;
  provider?: string;
}

export function overviewSearch(raw: Record<string, unknown>): OverviewSearch {
  return {
    month: isMonth(raw.month) ? raw.month : undefined,
    provider:
      typeof raw.provider === 'string' && /^[\w-]{1,36}$/.test(raw.provider)
        ? raw.provider
        : undefined,
  };
}

export interface PlatformSearch {
  month?: string;
}

export function platformSearch(raw: Record<string, unknown>): PlatformSearch {
  return { month: isMonth(raw.month) ? raw.month : undefined };
}
