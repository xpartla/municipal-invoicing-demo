import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';
import {
  READING,
  invoiceKey,
  invoicesKey,
  type Invoice,
  type InvoiceDocument,
} from '../invoices/api';

export { READING };

/** Uploads and their reading (plan §8.2, §10.5): documents, extractions, the check step's
 * page images and the handwritten note's crop. */

export type UploadOutcome = Schemas['UploadItemOut'];
export type Extraction = Schemas['ExtractionOut'];
export type Suggestion = Schemas['SuggestionOut'];

export function useUploadDocuments(customerId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData();
      for (const file of files) form.append('files', file, file.name);
      // The generated body type knows the fields, not FormData; the client sends it as is.
      const body = form as unknown as { files: string[] };
      return unwrap(
        api.POST('/api/customers/{customer_id}/documents', {
          params: { path: { customer_id: customerId } },
          body,
        }),
      );
    },
    onSuccess: () => client.invalidateQueries({ queryKey: invoicesKey(customerId) }),
  });
}

function invoiceQuery(customerId: string, invoiceId: string) {
  return {
    queryKey: invoiceKey(customerId, invoiceId),
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/invoices/{invoice_id}', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
        }),
      ),
    // The UI polls every two seconds while a file is read (plan §4.6).
    refetchInterval: (query: { state: { data?: Invoice } }) =>
      query.state.data && !READING.has(query.state.data.state) ? false : 2000,
  };
}

/** The uploaded invoices, each polled until its file has been read. */
export function useUploadedInvoices(customerId: string, invoiceIds: string[]) {
  return useQueries({ queries: invoiceIds.map((id) => invoiceQuery(customerId, id)) });
}

/** The document's newest reading; none (404) before it was read. */
export function useExtraction(customerId: string, documentId: string | null | undefined) {
  return useQuery({
    queryKey: ['extraction', customerId, documentId],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/documents/{document_id}/extraction', {
          params: { path: { customer_id: customerId, document_id: documentId ?? '' } },
        }),
      ),
    enabled: documentId != null,
    retry: false,
  });
}

/** Where a page image of the reading, or the note's crop, is served (same-origin, so the
 * session cookie goes with it). */
export function pageUrl(customerId: string, documentId: string, page: number): string {
  return `/api/customers/${customerId}/documents/${documentId}/pages/${String(page)}`;
}

export function noteUrl(customerId: string, documentId: string): string {
  return `/api/customers/${customerId}/documents/${documentId}/note`;
}

export function fileUrl(customerId: string, documentId: string): string {
  return `/api/customers/${customerId}/documents/${documentId}/file`;
}

/** Reads a failed invoice's document again. */
export function useRetryExtraction(customerId: string, invoiceId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/customers/{customer_id}/invoices/{invoice_id}/extraction', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: invoiceKey(customerId, invoiceId) }),
  });
}

/** The fields of an invoice whose file could not be read, typed by the user. */
export function useEnterAfterFailure(customerId: string, invoiceId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (fields: InvoiceDocument) =>
      unwrap(
        api.POST('/api/customers/{customer_id}/invoices/{invoice_id}/manual', {
          params: { path: { customer_id: customerId, invoice_id: invoiceId } },
          body: fields,
        }),
      ),
    onSuccess: (invoice) => {
      client.setQueryData(invoiceKey(customerId, invoiceId), invoice);
      return client.invalidateQueries({ queryKey: invoicesKey(customerId) });
    },
  });
}
