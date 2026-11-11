import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';

/** Úlohy (plan §10.9): every job with its state and error; retry, cancel, data exports. */

export type AdminJob = Schemas['AdminJobOut'];
export type JobStatus = AdminJob['status'];

export const JOB_STATUSES = [
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled',
] as const satisfies readonly JobStatus[];
export const JOBS_PAGE = 50;

export interface JobsSearch {
  status?: JobStatus;
  kind?: string;
  page?: number;
}

export function jobsSearch(raw: Record<string, unknown>): JobsSearch {
  const page = Number(raw.page);
  return {
    status: JOB_STATUSES.find((s) => s === raw.status),
    kind: typeof raw.kind === 'string' && /^[a-z_]{1,40}$/.test(raw.kind) ? raw.kind : undefined,
    page: Number.isInteger(page) && page > 1 ? page : undefined,
  };
}

const jobsKey = ['admin-jobs'] as const;

export function useJobs(search: JobsSearch) {
  return useQuery({
    queryKey: [...jobsKey, search],
    queryFn: () =>
      unwrap(
        api.GET('/api/admin/jobs', {
          params: {
            query: {
              status: search.status,
              kind: search.kind,
              page: search.page ?? 1,
              size: JOBS_PAGE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
    // The UI follows running jobs every two seconds (plan §4.6).
    refetchInterval: (query) =>
      query.state.data?.items.some((j) => j.status === 'queued' || j.status === 'running')
        ? 2000
        : false,
  });
}

export function useJobAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, action }: { jobId: string; action: 'retry' | 'cancel' }) =>
      action === 'retry'
        ? unwrap(
            api.POST('/api/admin/jobs/{job_id}/retry', { params: { path: { job_id: jobId } } }),
          )
        : unwrap(
            api.POST('/api/admin/jobs/{job_id}/cancel', { params: { path: { job_id: jobId } } }),
          ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: jobsKey });
    },
  });
}

export function useStartDataExport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) =>
      unwrap(
        api.POST('/api/admin/customers/{customer_id}/data-export', {
          params: { path: { customer_id: customerId } },
        }),
      ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: jobsKey });
    },
  });
}

/** Where the browser downloads a finished data export (a plain link with the cookie). */
export function dataExportUrl(jobId: string): string {
  return `/api/admin/jobs/${encodeURIComponent(jobId)}/file`;
}
