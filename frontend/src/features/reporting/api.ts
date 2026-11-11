import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';

/** Úložisko (plan §10.7): the customer's stored files. */

export type StoredFile = Schemas['FileOut'];
export type FileKind = StoredFile['kind'];

export const KINDS: readonly FileKind[] = ['document', 'import', 'export'];
export const FILES_PAGE = 50;

export function useFiles(customerId: string, kind: FileKind | undefined, page: number) {
  return useQuery({
    queryKey: ['files', customerId, kind, page],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/files', {
          params: {
            path: { customer_id: customerId },
            query: { kind: kind ?? null, page, size: FILES_PAGE },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Where a file downloads: through what owns it (the document, the import or the export). */
export function downloadUrl(customerId: string, file: StoredFile): string {
  const base = `/api/customers/${customerId}`;
  if (file.kind === 'document') return `${base}/documents/${file.id}/file`;
  if (file.kind === 'import') return `${base}/imports/${file.id}/file`;
  return `${base}/exports/${file.id}/file`;
}

export interface FilesSearch {
  kind?: FileKind;
  page?: number;
}

export function filesSearch(raw: Record<string, unknown>): FilesSearch {
  const kind = KINDS.find((k) => k === raw.kind);
  const page = Number(raw.page);
  return { kind, page: Number.isInteger(page) && page > 1 ? page : undefined };
}
