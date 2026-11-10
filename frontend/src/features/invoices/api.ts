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

export type History = Schemas['HistoryOut'];
export type Placement = Schemas['PlacementOut'];
export type BookingInput = Schemas['BookingIn'];
export type Entry = Schemas['EntryOut'];

export const invoiceKey = (customerId: string, invoiceId: string) =>
  [...invoicesKey(customerId), 'one', invoiceId] as const;

export function useInvoice(customerId: string, invoiceId: string) {
  return useQuery({
    queryKey: invoiceKey(customerId, invoiceId),
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/invoices/{invoice_id}', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
        }),
      ),
  });
}

export function useHistory(customerId: string, invoiceId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...invoiceKey(customerId, invoiceId), 'history'],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/invoices/{invoice_id}/history', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
        }),
      ),
    enabled,
  });
}

export type InvoiceAction =
  | { action: 'recode' }
  | { action: 'unbook'; reason?: string }
  | { action: 'discard'; reason?: string }
  | { action: 'pay'; paidOn: string }
  | { action: 'book'; booking: BookingInput };

/**
 * One step of the invoice's lifecycle. The invoice comes back from each; booking also gives
 * its placement (decision 61). The list, the history and the number series are refreshed.
 */
export function useInvoiceAction(customerId: string, invoiceId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (
      step: InvoiceAction,
    ): Promise<{ invoice: Invoice; placement?: Placement }> => {
      const path = { customer_id: customerId, invoice_id: invoiceId };
      const base = '/api/customers/{customer_id}/invoices/{invoice_id}' as const;
      switch (step.action) {
        case 'recode':
          return { invoice: await unwrap(api.POST(`${base}/recode`, { params: { path } })) };
        case 'unbook':
          return {
            invoice: await unwrap(
              api.POST(`${base}/unbook`, {
                params: { path },
                body: { reason: step.reason ?? null },
              }),
            ),
          };
        case 'discard':
          return {
            invoice: await unwrap(
              api.POST(`${base}/discard`, {
                params: { path },
                body: { reason: step.reason ?? null },
              }),
            ),
          };
        case 'pay':
          return {
            invoice: await unwrap(
              api.POST(`${base}/pay`, { params: { path }, body: { paid_on: step.paidOn } }),
            ),
          };
        case 'book':
          return unwrap(api.POST(`${base}/book`, { params: { path }, body: step.booking }));
      }
    },
    onSuccess: ({ invoice }) => {
      client.setQueryData(invoiceKey(customerId, invoiceId), invoice);
    },
    onSettled: async () => {
      await client.invalidateQueries({ queryKey: invoicesKey(customerId) });
      await client.invalidateQueries({ queryKey: numberSeriesKey(customerId) });
    },
  });
}

/** Where booking would put the number, and what it would move (for the confirmation). */
export function useBookingPreview(customerId: string, invoiceId: string) {
  return useMutation({
    mutationFn: (booking: BookingInput) =>
      unwrap(
        api.POST('/api/customers/{customer_id}/invoices/{invoice_id}/booking-preview', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
          body: booking,
        }),
      ),
  });
}

/** The whole line a budget position the user picked brings (MD, DAL, transfer, texts). */
export function usePickedLine(customerId: string, invoiceId: string) {
  return useMutation({
    mutationFn: (budgetKey: string) =>
      unwrap(
        api.POST('/api/customers/{customer_id}/invoices/{invoice_id}/line', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
          body: { budget_key: budgetKey },
        }),
      ),
  });
}

export type WholeListKind = 'budget_expense' | 'accounts' | 'transfers' | 'document_series';

/** Every entry of a list's active version for the year, read page by page once. */
export function useWholeList(
  customerId: string,
  kind: WholeListKind,
  year: number | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['codelists', customerId, 'whole', kind, year],
    queryFn: async () => {
      const found: Entry[] = [];
      for (let page = 1; ; page++) {
        const part = await unwrap(
          api.GET('/api/customers/{customer_id}/codelists/{kind}/entries', {
            params: {
              path: { customer_id: customerId, kind },
              query: { year: year ?? undefined, page, size: 200 },
            },
          }),
        );
        found.push(...part.items);
        if (found.length >= part.total || part.items.length === 0) return found;
      }
    },
    enabled: enabled && year !== undefined,
    staleTime: 5 * 60_000,
  });
}

/** The next invoice that waits for a booking (needs review or ready), the oldest first. */
export function useNextInvoice(customerId: string, currentId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...invoicesKey(customerId), 'next', currentId],
    queryFn: async () => {
      const page = await unwrap(
        api.GET('/api/customers/{customer_id}/invoices', {
          params: {
            path: { customer_id: customerId },
            query: { state: ['needs_review', 'ready'], sort: 'uploaded_at', size: 2 },
          },
        }),
      );
      return page.items.find((row) => row.id !== currentId)?.id ?? null;
    },
    enabled,
  });
}

export type NumberSeries = Schemas['NumberSeriesOut'];
export type InvoiceDocument = Schemas['InvoiceDocument'];

/** The year's invoice series with their counters, used numbers and gaps (Systém). */
export function useNumberSeries(customerId: string, year: number) {
  return useQuery({
    queryKey: [...numberSeriesKey(customerId), year, 'list'],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/number-series', {
          params: { path: { customer_id: customerId }, query: { year } },
        }),
      ),
  });
}

/** The audited edit of a series' counter (plan §7.2). */
export function useSetLastUsed(customerId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ series, year, lastUsed }: { series: string; year: number; lastUsed: number }) =>
      unwrap(
        api.PUT('/api/customers/{customer_id}/number-series/{series}/{year}', {
          params: { path: { customer_id: customerId, series, year } },
          body: { last_used: lastUsed },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: numberSeriesKey(customerId) }),
  });
}

/** Manual entry (plan §8.5): an invoice from typed fields, checked and coded at once. */
export function useEnterInvoice(customerId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (fields: InvoiceDocument) =>
      unwrap(
        api.POST('/api/customers/{customer_id}/invoices', {
          params: { path: { customer_id: customerId } },
          body: fields,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: invoicesKey(customerId) }),
  });
}
