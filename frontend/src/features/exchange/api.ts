import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';
import { codelistsKey } from '../codelists/api';

/** Imports and mapping templates (plan §9.2, §10.7): a customer's, or the global lists'. */

export type ImportRun = Schemas['ImportRunOut'];
export type ImportPreview = Schemas['ImportPreviewOut'];
export type ImportType = Schemas['ImportType'];
export type ReadOptions = Schemas['ReadOptionsIn'];
export type ColumnMapping = Schemas['ColumnMapping'];
export type FieldSource = Schemas['FieldSource'];
export type TargetField = Schemas['TargetFieldOut'];
export type Template = Schemas['TemplateOut'];
export type Report = Schemas['DryRunReport'];
export type Issue = Schemas['Issue'];
export type SavableScope = Schemas['RunTemplateIn']['scope'];

/** Whose imports: a customer's, or the global lists' (admin). */
export type Owner = { customerId: string } | 'global';

const ownerKey = (owner: Owner) => (owner === 'global' ? 'global' : owner.customerId);
export const importsKey = (owner: Owner) => ['imports', ownerKey(owner)] as const;
const templatesKey = (owner: Owner) => ['templates', ownerKey(owner)] as const;

/** A dry run or an apply is running while the run waits for its job. */
export const isWorking = (run: ImportRun | undefined) => run?.job_id != null;

export function useImports(owner: Owner, page: number, size: number) {
  return useQuery({
    queryKey: [...importsKey(owner), 'list', page, size],
    queryFn: () =>
      unwrap(
        owner === 'global'
          ? api.GET('/api/admin/imports', { params: { query: { page, size } } })
          : api.GET('/api/customers/{customer_id}/imports', {
              params: { path: { customer_id: owner.customerId }, query: { page, size } },
            }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** The run; polled every second while its job runs. */
export function useImport(owner: Owner, runId: string | undefined) {
  return useQuery({
    queryKey: [...importsKey(owner), 'run', runId],
    queryFn: () =>
      unwrap(
        owner === 'global'
          ? api.GET('/api/admin/imports/{run_id}', { params: { path: { run_id: runId ?? '' } } })
          : api.GET('/api/customers/{customer_id}/imports/{run_id}', {
              params: { path: { customer_id: owner.customerId, run_id: runId ?? '' } },
            }),
      ),
    enabled: runId !== undefined,
    refetchInterval: (query) => (isWorking(query.state.data) ? 1000 : false),
  });
}

export function usePreview(owner: Owner, runId: string | undefined, options: ReadOptions | null) {
  return useQuery({
    queryKey: [...importsKey(owner), 'preview', runId, options],
    queryFn: () => {
      const query = options ?? {};
      return unwrap(
        owner === 'global'
          ? api.GET('/api/admin/imports/{run_id}/preview', {
              params: { path: { run_id: runId ?? '' }, query },
            })
          : api.GET('/api/customers/{customer_id}/imports/{run_id}/preview', {
              params: { path: { customer_id: owner.customerId, run_id: runId ?? '' }, query },
            }),
      );
    },
    enabled: runId !== undefined,
    placeholderData: keepPreviousData,
  });
}

export interface Upload {
  file: File;
  importType: ImportType;
  year: number;
}

export function useUpload(owner: Owner) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, importType, year }: Upload) => {
      const form = new FormData();
      form.append('file', file, file.name);
      form.append('import_type', importType);
      form.append('year', String(year));
      // The generated body type knows the fields, not FormData; the client sends it as is.
      const body = form as unknown as { file: string; import_type: ImportType; year: number };
      return unwrap(
        owner === 'global'
          ? api.POST('/api/admin/imports', { body })
          : api.POST('/api/customers/{customer_id}/imports', {
              params: { path: { customer_id: owner.customerId } },
              body,
            }),
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: importsKey(owner) }),
  });
}

/** After a step: the run as the server has it, and the history refreshed. */
function useRunStep<TInput>(
  owner: Owner,
  runId: string,
  step: (input: TInput) => Promise<ImportRun>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: step,
    onSuccess: (run) => {
      queryClient.setQueryData([...importsKey(owner), 'run', runId], run);
      return queryClient.invalidateQueries({ queryKey: [...importsKey(owner), 'list'] });
    },
  });
}

export interface MappingInput {
  options: ReadOptions;
  mapping: ColumnMapping;
  templateId: string | null;
}

export function useSetMapping(owner: Owner, runId: string) {
  return useRunStep(owner, runId, ({ options, mapping, templateId }: MappingInput) => {
    const body = { options, mapping, template_id: templateId };
    return unwrap(
      owner === 'global'
        ? api.PUT('/api/admin/imports/{run_id}/mapping', {
            params: { path: { run_id: runId } },
            body,
          })
        : api.PUT('/api/customers/{customer_id}/imports/{run_id}/mapping', {
            params: { path: { customer_id: owner.customerId, run_id: runId } },
            body,
          }),
    );
  });
}

export function useDryRun(owner: Owner, runId: string) {
  return useRunStep(owner, runId, () =>
    unwrap(
      owner === 'global'
        ? api.POST('/api/admin/imports/{run_id}/dry-run', { params: { path: { run_id: runId } } })
        : api.POST('/api/customers/{customer_id}/imports/{run_id}/dry-run', {
            params: { path: { customer_id: owner.customerId, run_id: runId } },
          }),
    ),
  );
}

export function useApply(owner: Owner, runId: string) {
  const queryClient = useQueryClient();
  const step = useRunStep(owner, runId, (confirmErrors: boolean) => {
    const body = { confirm_errors: confirmErrors };
    return unwrap(
      owner === 'global'
        ? api.POST('/api/admin/imports/{run_id}/apply', {
            params: { path: { run_id: runId } },
            body,
          })
        : api.POST('/api/customers/{customer_id}/imports/{run_id}/apply', {
            params: { path: { customer_id: owner.customerId, run_id: runId } },
            body,
          }),
    );
  });
  const customerId = owner === 'global' ? null : owner.customerId;
  /** The new version shows on Číselníky once the apply is done. */
  const refreshLists = useCallback(
    () =>
      queryClient.invalidateQueries({
        queryKey: codelistsKey(customerId === null ? 'global' : { customerId }),
      }),
    [queryClient, customerId],
  );
  return { ...step, refreshLists };
}

export function useCancel(owner: Owner, runId: string) {
  return useRunStep(owner, runId, () =>
    unwrap(
      owner === 'global'
        ? api.POST('/api/admin/imports/{run_id}/cancel', { params: { path: { run_id: runId } } })
        : api.POST('/api/customers/{customer_id}/imports/{run_id}/cancel', {
            params: { path: { customer_id: owner.customerId, run_id: runId } },
          }),
    ),
  );
}

export function useTemplates(owner: Owner, importType?: ImportType, enabled = true) {
  return useQuery({
    queryKey: [...templatesKey(owner), importType ?? 'all'],
    queryFn: () => {
      const query = { import_type: importType ?? null };
      return unwrap(
        owner === 'global'
          ? api.GET('/api/admin/templates', { params: { query } })
          : api.GET('/api/customers/{customer_id}/templates', {
              params: { path: { customer_id: owner.customerId }, query },
            }),
      );
    },
    enabled,
  });
}

export function useSaveRunTemplate(owner: Owner, runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ scope, name }: { scope: SavableScope; name: string }) => {
      const body = { scope, name };
      return unwrap(
        owner === 'global'
          ? api.POST('/api/admin/imports/{run_id}/template', {
              params: { path: { run_id: runId } },
              body,
            })
          : api.POST('/api/customers/{customer_id}/imports/{run_id}/template', {
              params: { path: { customer_id: owner.customerId, run_id: runId } },
              body,
            }),
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: templatesKey(owner) }),
  });
}

export function useDeleteTemplate(owner: Owner) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      await unwrap(
        owner === 'global'
          ? api.DELETE('/api/admin/templates/{template_id}', {
              params: { path: { template_id: templateId } },
            })
          : api.DELETE('/api/customers/{customer_id}/templates/{template_id}', {
              params: { path: { customer_id: owner.customerId, template_id: templateId } },
            }),
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: templatesKey(owner) }),
  });
}

/** Where the run's file downloads from (a plain link: the browser saves it). */
export function fileUrl(owner: Owner, runId: string): string {
  return owner === 'global'
    ? `/api/admin/imports/${runId}/file`
    : `/api/customers/${owner.customerId}/imports/${runId}/file`;
}
