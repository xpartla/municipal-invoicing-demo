import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';

/** Code lists (plan §6, §10.6, §10.9): a customer's lists and the admin's global ones. */

export type ListKind = Schemas['ListKind'];
export type Version = Schemas['VersionOut'];
export type Entry = Schemas['EntryOut'];
export type EntryPage = Schemas['EntryPageOut'];
export type ListsOverview = Schemas['ListsOverviewOut'];
export type Diff = Schemas['DiffOut'];
export type ChecklistYear = Schemas['ChecklistYearOut'];

/** Whose lists: a customer's, or the global ones (admin). */
export type Owner = { customerId: string } | 'global';

export interface EntryQuery {
  year: number;
  version?: string;
  q?: string;
  page: number;
  size: number;
}

const ownerKey = (owner: Owner) => (owner === 'global' ? 'global' : owner.customerId);

export const codelistsKey = (owner: Owner) => ['codelists', ownerKey(owner)] as const;

export function useListsOverview(customerId: string, year: number) {
  return useQuery({
    queryKey: [...codelistsKey({ customerId }), 'overview', year],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/codelists', {
          params: { path: { customer_id: customerId }, query: { year } },
        }),
      ),
  });
}

export function useEntries(owner: Owner, kind: ListKind, query: EntryQuery, enabled = true) {
  return useQuery({
    queryKey: [...codelistsKey(owner), 'entries', kind, query],
    queryFn: () => {
      const params = {
        year: query.year,
        version: query.version,
        q: query.q === '' ? undefined : query.q,
        page: query.page,
        size: query.size,
      };
      return unwrap(
        owner === 'global'
          ? api.GET('/api/admin/codelists/{kind}/entries', {
              params: { path: { kind }, query: params },
            })
          : api.GET('/api/customers/{customer_id}/codelists/{kind}/entries', {
              params: { path: { customer_id: owner.customerId, kind }, query: params },
            }),
      );
    },
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useVersions(owner: Owner, kind: ListKind, year: number, enabled = true) {
  return useQuery({
    queryKey: [...codelistsKey(owner), 'versions', kind, year],
    queryFn: () =>
      unwrap(
        owner === 'global'
          ? api.GET('/api/admin/codelists/{kind}/versions', {
              params: { path: { kind }, query: { year } },
            })
          : api.GET('/api/customers/{customer_id}/codelists/{kind}/versions', {
              params: { path: { customer_id: owner.customerId, kind }, query: { year } },
            }),
      ),
    enabled,
  });
}

export function useDiff(customerId: string, kind: ListKind, old?: string, current?: string) {
  return useQuery({
    queryKey: [...codelistsKey({ customerId }), 'diff', kind, old, current],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/codelists/{kind}/diff', {
          params: {
            path: { customer_id: customerId, kind },
            query: { old: old ?? '', new: current ?? '' },
          },
        }),
      ),
    enabled: old !== undefined && current !== undefined && old !== current,
  });
}

export function useGlobalChecklist() {
  return useQuery({
    queryKey: [...codelistsKey('global'), 'checklist'],
    queryFn: () => unwrap(api.GET('/api/admin/codelists')),
  });
}

/** One row edit. Each makes a new version of the list (plan §6.2). */
export type RowEdit =
  | { action: 'add'; values: Record<string, unknown> }
  | { action: 'edit'; key: string; values: Record<string, unknown> }
  | { action: 'deactivate' | 'reactivate'; key: string };

export function useEditRow(customerId: string, kind: ListKind, year: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ edit, versionId }: { edit: RowEdit; versionId: string | null }) => {
      const query = { year };
      const base = { customer_id: customerId, kind };
      switch (edit.action) {
        case 'add':
          return unwrap(
            api.POST('/api/customers/{customer_id}/codelists/{kind}/entries', {
              params: { path: base, query },
              body: { version_id: versionId, values: edit.values },
            }),
          );
        case 'edit':
          return unwrap(
            api.PUT('/api/customers/{customer_id}/codelists/{kind}/entries/{key}', {
              params: { path: { ...base, key: edit.key }, query },
              body: { version_id: versionId, values: edit.values },
            }),
          );
        case 'deactivate':
          return unwrap(
            api.POST('/api/customers/{customer_id}/codelists/{kind}/entries/{key}/deactivate', {
              params: { path: { ...base, key: edit.key }, query },
              body: { version_id: versionId ?? '' },
            }),
          );
        case 'reactivate':
          return unwrap(
            api.POST('/api/customers/{customer_id}/codelists/{kind}/entries/{key}/reactivate', {
              params: { path: { ...base, key: edit.key }, query },
              body: { version_id: versionId ?? '' },
            }),
          );
      }
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: codelistsKey({ customerId }) });
    },
  });
}
