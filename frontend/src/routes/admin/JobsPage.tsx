import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Group,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
  VisuallyHidden,
} from '@mantine/core';
import { IconDownload, IconPlayerStop, IconRefresh } from '@tabler/icons-react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Pager } from '../../components/Pager';
import { ScrollTable } from '../../components/ScrollTable';
import {
  JOBS_PAGE,
  JOB_STATUSES,
  dataExportUrl,
  useJobAction,
  useJobs,
  useStartDataExport,
  type AdminJob,
  type JobStatus,
} from '../../features/admin/jobs';
import { useUsers } from '../../features/identity/api';
import { useDirectory } from '../../features/tenancy/api';
import { formatDateTime, formatSize } from '../../lib/format';
import { useNotify } from '../../lib/notify';
import { Loading, LoadFailed } from '../../components/QueryStates';

const STATUS_COLORS: Record<JobStatus, string> = {
  queued: 'gray',
  running: 'blue',
  succeeded: 'teal',
  failed: 'red',
  cancelled: 'gray',
};

/**
 * Úlohy (plan §10.9, decision 67): every background job, newest first, with its state,
 * attempts and last error; a failed job is retried, a queued one cancelled. The customer data
 * export starts here and its ZIP downloads from its row. Running jobs are followed every two
 * seconds.
 */
export function JobsPage() {
  const { t } = useTranslation();
  const search = useSearch({ from: '/_app/admin/jobs' });
  const navigate = useNavigate({ from: '/admin/jobs' });
  const found = useJobs(search);
  const users = useUsers('', true);
  const directory = useDirectory('all');
  const action = useJobAction();
  const notify = useNotify();
  const userName = new Map((users.data?.items ?? []).map((u) => [u.id, u.name]));
  const customerName = new Map((directory.data ?? []).map((c) => [c.customer.id, c.customer.name]));
  const kindLabel = (kind: string) =>
    t(`jobs.kinds.${kind}` as 'jobs.kinds.data_export', { defaultValue: kind });

  const run = (job: AdminJob, which: 'retry' | 'cancel') => {
    action.mutate(
      { jobId: job.id, action: which },
      {
        onSuccess: () => {
          notify.success(t(`jobs.done.${which}`, { kind: kindLabel(job.kind) }));
        },
        onError: (error) => {
          notify.failure(error);
        },
      },
    );
  };

  return (
    <Stack gap="md">
      <Title order={1}>{t('jobs.title')}</Title>
      <DataExport />
      <Group align="flex-end" wrap="wrap">
        <Select
          label={t('jobs.filters.status')}
          data={JOB_STATUSES.map((s) => ({ value: s, label: t(`jobs.statuses.${s}`) }))}
          value={search.status ?? null}
          clearable
          onChange={(value) => {
            void navigate({
              search: (s) => ({
                ...s,
                status: JOB_STATUSES.find((x) => x === value),
                page: undefined,
              }),
            });
          }}
          w={200}
        />
        <Select
          label={t('jobs.filters.kind')}
          data={(found.data?.kinds ?? []).map((k) => ({ value: k, label: kindLabel(k) }))}
          value={search.kind ?? null}
          clearable
          onChange={(value) => {
            void navigate({ search: (s) => ({ ...s, kind: value ?? undefined, page: undefined }) });
          }}
          w={240}
        />
      </Group>
      {found.isPending && <Loading />}
      {found.isError && <LoadFailed error={found.error} onRetry={found.refetch} />}
      {found.data && (
        <>
          <Text size="sm">{t('jobs.count', { count: found.data.total })}</Text>
          {found.data.items.length === 0 ? (
            <Text c="dimmed">{t('jobs.empty')}</Text>
          ) : (
            <ScrollTable label={t('jobs.table')} minWidth={900}>
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('jobs.columns.created')}</Table.Th>
                    <Table.Th>{t('jobs.columns.kind')}</Table.Th>
                    <Table.Th>{t('jobs.columns.customer')}</Table.Th>
                    <Table.Th>{t('jobs.columns.by')}</Table.Th>
                    <Table.Th>{t('jobs.columns.status')}</Table.Th>
                    <Table.Th ta="right">{t('jobs.columns.attempts')}</Table.Th>
                    <Table.Th>{t('jobs.columns.error')}</Table.Th>
                    <Table.Th>
                      <VisuallyHidden>{t('jobs.columns.actions')}</VisuallyHidden>
                    </Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {found.data.items.map((job) => (
                    <Table.Tr key={job.id}>
                      <Table.Td>{formatDateTime(job.created_at)}</Table.Td>
                      <Table.Td>{kindLabel(job.kind)}</Table.Td>
                      <Table.Td>
                        {job.customer_id
                          ? (customerName.get(job.customer_id) ?? job.customer_id)
                          : '—'}
                      </Table.Td>
                      <Table.Td>
                        {job.created_by ? (userName.get(job.created_by) ?? job.created_by) : '—'}
                      </Table.Td>
                      <Table.Td>
                        <Badge color={STATUS_COLORS[job.status]}>
                          {t(`jobs.statuses.${job.status}`)}
                        </Badge>
                      </Table.Td>
                      <Table.Td ta="right">
                        {t('jobs.attempts', { attempts: job.attempts, max: job.max_attempts })}
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" style={{ wordBreak: 'break-word' }}>
                          {job.last_error ?? '—'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4} wrap="nowrap" justify="flex-end">
                          {job.status === 'failed' && (
                            <Tooltip label={t('jobs.retry')}>
                              <ActionIcon
                                variant="subtle"
                                aria-label={t('jobs.retryJob', { kind: kindLabel(job.kind) })}
                                onClick={() => {
                                  run(job, 'retry');
                                }}
                              >
                                <IconRefresh size={18} aria-hidden />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {job.status === 'queued' && (
                            <Tooltip label={t('jobs.cancel')}>
                              <ActionIcon
                                variant="subtle"
                                color="red"
                                aria-label={t('jobs.cancelJob', { kind: kindLabel(job.kind) })}
                                onClick={() => {
                                  run(job, 'cancel');
                                }}
                              >
                                <IconPlayerStop size={18} aria-hidden />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {job.kind === 'data_export' && job.status === 'succeeded' && (
                            <Anchor
                              href={dataExportUrl(job.id)}
                              size="sm"
                              aria-label={t('jobs.download', {
                                name: customerName.get(job.customer_id ?? '') ?? '',
                              })}
                            >
                              <Group gap={4} wrap="nowrap">
                                <IconDownload size={16} aria-hidden />
                                {typeof job.result?.size === 'number'
                                  ? formatSize(job.result.size)
                                  : t('jobs.zip')}
                              </Group>
                            </Anchor>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollTable>
          )}
          <Pager
            page={search.page ?? 1}
            pages={Math.ceil(found.data.total / JOBS_PAGE)}
            onPage={(page) => {
              void navigate({ search: (s) => ({ ...s, page: page > 1 ? page : undefined }) });
            }}
          />
        </>
      )}
    </Stack>
  );
}

/** Export údajov klienta (plan §10.9): every row and file of one customer as a ZIP. */
function DataExport() {
  const { t } = useTranslation();
  const directory = useDirectory('all');
  const start = useStartDataExport();
  const notify = useNotify();
  const [customerId, setCustomerId] = useState<string | null>(null);
  return (
    <Paper withBorder p="md" radius="md" component="section" aria-labelledby="data-export-title">
      <Stack gap="sm">
        <Title order={2} size="h4" id="data-export-title">
          {t('jobs.export.title')}
        </Title>
        <Text size="sm">{t('jobs.export.intro')}</Text>
        <Group align="flex-end" wrap="wrap">
          <Select
            label={t('jobs.export.customer')}
            data={(directory.data ?? []).map((c) => ({
              value: c.customer.id,
              label: c.customer.name,
            }))}
            value={customerId}
            searchable
            onChange={setCustomerId}
            w={300}
          />
          <Button
            disabled={!customerId}
            loading={start.isPending}
            onClick={() => {
              if (!customerId) return;
              start.mutate(customerId, {
                onSuccess: () => {
                  notify.success(t('jobs.export.started'));
                },
                onError: (error) => {
                  notify.failure(error);
                },
              });
            }}
          >
            {t('jobs.export.start')}
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}
