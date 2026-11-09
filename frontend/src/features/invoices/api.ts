import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';
import type { ExportFilter, InvoiceQuery } from './search';

/** Invoices (plan §10.3, §10.4) and their exports (§7.4). */

export type InvoiceRow = Schemas['InvoiceRowOut'];
export type InvoicePage = Schemas['InvoicePageOut'];
export type Invoice = Schemas['InvoiceOut'];
export type Supplier = Schemas['SupplierOut'];
export type BulkOutcome = Schemas['BulkOut'];
export type ExportRun = Schemas['ExportRunOut'];
export type ExportPreview = Schemas['ExportPreviewOut'];
export type ExportFormat = ExportRun['format'];

export const invoicesKey = (customerId: string) => ['invoices', customerId] as const;
export const exportsKey = (customerId: string) => ['exports', customerId] as const;

export function useInvoices(customerId: string, query: InvoiceQuery) {
  return useQuery({
    queryKey: [...invoicesKey(customerId), 'list', query],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/invoices', {
          params: { path: { customer_id: customerId }, query },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Suppliers whose name or IČO matches, for the supplier filter. */
export function useSuppliers(customerId: string, q: string, enabled: boolean) {
  return useQuery({
    queryKey: [...invoicesKey(customerId), 'suppliers', q],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/invoices/suppliers', {
          params: { path: { customer_id: customerId }, query: { q } },
        }),
      ),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export type BulkAction =
  | { action: 'pay'; invoiceIds: string[]; paidOn: string }
  | { action: 'recode'; invoiceIds: string[] }
  | { action: 'discard'; invoiceIds: string[]; reason?: string };

/** Mark paid, re-code or discard several invoices; the outcome lists each one. */
export function useBulk(customerId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (bulk: BulkAction) => {
      const path = { customer_id: customerId };
      if (bulk.action === 'pay') {
        return unwrap(
          api.POST('/api/customers/{customer_id}/invoices/bulk/pay', {
            params: { path },
            body: { invoice_ids: bulk.invoiceIds, paid_on: bulk.paidOn },
          }),
        );
      }
      if (bulk.action === 'recode') {
        return unwrap(
          api.POST('/api/customers/{customer_id}/invoices/bulk/recode', {
            params: { path },
            body: { invoice_ids: bulk.invoiceIds },
          }),
        );
      }
      return unwrap(
        api.POST('/api/customers/{customer_id}/invoices/bulk/discard', {
          params: { path },
          body: { invoice_ids: bulk.invoiceIds, reason: bulk.reason ?? null },
        }),
      );
    },
    onSettled: () => client.invalidateQueries({ queryKey: invoicesKey(customerId) }),
  });
}

/** What to export: a selection, or the view's filters and sort. */
export type ExportScope =
  { invoiceIds: string[] } | { filter: ExportFilter; sort: string | undefined };

function exportBody(format: ExportFormat, scope: ExportScope): Schemas['ExportIn'] {
  if ('invoiceIds' in scope) return { format, invoice_ids: scope.invoiceIds };
  return { format, filter: scope.filter, sort: scope.sort ?? null };
}

export function useExportPreview(customerId: string, scope: ExportScope, enabled: boolean) {
  return useQuery({
    queryKey: [...exportsKey(customerId), 'preview', scope],
    queryFn: () =>
      unwrap(
        api.POST('/api/customers/{customer_id}/exports/preview', {
          params: { path: { customer_id: customerId } },
          body: exportBody('csv', scope),
        }),
      ),
    enabled,
    staleTime: 0,
  });
}

export function useStartExport(customerId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ format, scope }: { format: ExportFormat; scope: ExportScope }) =>
      unwrap(
        api.POST('/api/customers/{customer_id}/exports', {
          params: { path: { customer_id: customerId } },
          body: exportBody(format, scope),
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: exportsKey(customerId) }),
  });
}

/** One export; polled every second while its job runs, the invoices refreshed when done. */
export function useExportRun(customerId: string, runId: string | undefined) {
  const client = useQueryClient();
  return useQuery({
    queryKey: [...exportsKey(customerId), 'run', runId],
    queryFn: async () => {
      const run = await unwrap(
        api.GET('/api/customers/{customer_id}/exports/{run_id}', {
          params: { path: { customer_id: customerId, run_id: runId ?? '' } },
        }),
      );
      if (run.state !== 'queued') {
        await client.invalidateQueries({ queryKey: invoicesKey(customerId) });
        await client.invalidateQueries({ queryKey: [...exportsKey(customerId), 'list'] });
      }
      return run;
    },
    enabled: runId !== undefined,
    refetchInterval: (query) => (query.state.data?.state === 'queued' ? 1000 : false),
  });
}

export function useExports(customerId: string, page: number, size: number) {
  return useQuery({
    queryKey: [...exportsKey(customerId), 'list', page, size],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/exports', {
          params: { path: { customer_id: customerId }, query: { page, size } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Where the browser downloads an export's file (a plain link, sent with the session cookie). */
export function exportFileUrl(customerId: string, runId: string): string {
  return `/api/customers/${encodeURIComponent(customerId)}/exports/${encodeURIComponent(runId)}/file`;
}

export const numberSeriesKey = (customerId: string) => ['number-series', customerId] as const;

/** The codes of the customer's invoice series in a year (FD, FDŠJ …), for the series filter. */
export function useSeriesCodes(customerId: string, year: number) {
  return useQuery({
    queryKey: [...numberSeriesKey(customerId), year, 'codes'],
    queryFn: async () => {
      const found = await unwrap(
        api.GET('/api/customers/{customer_id}/number-series', {
          params: { path: { customer_id: customerId }, query: { year } },
        }),
      );
      return found.items.map((s) => s.series);
    },
  });
}
