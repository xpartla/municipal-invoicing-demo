import {
  Alert,
  Button,
  Code,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { Pager } from '../../components/Pager';
import { ScrollTable } from '../../components/ScrollTable';
import { AUDIT_PAGE, useAudit, type AuditSearch } from '../../features/admin/audit';
import { useUsers } from '../../features/identity/api';
import { useDirectory } from '../../features/tenancy/api';
import { formatDateTime } from '../../lib/format';

/**
 * Audit (plan §10.9): the log, newest first, filtered by actor (the actor or the real actor
 * behind an impersonation), customer, action (a whole action or a prefix ending in a dot,
 * `invoice.`) and days in Bratislava. The filters are in the URL.
 */
export function AuditPage() {
  const { t } = useTranslation();
  const search = useSearch({ from: '/_app/admin/audit' });
  const navigate = useNavigate({ from: '/admin/audit' });
  const found = useAudit(search);
  const users = useUsers('', true);
  const directory = useDirectory('all');

  const userName = new Map((users.data?.items ?? []).map((u) => [u.id, u.name]));
  const customerName = new Map((directory.data ?? []).map((c) => [c.customer.id, c.customer.name]));
  const set = (change: Partial<AuditSearch>) => {
    void navigate({ search: (s) => ({ ...s, ...change, page: undefined }) });
  };
  const person = (id: string | null) => (id ? (userName.get(id) ?? id) : '—');

  return (
    <Stack gap="md">
      <Title order={1}>{t('audit.title')}</Title>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const typed = new FormData(event.currentTarget).get('action');
          set({ action: (typeof typed === 'string' && typed.trim()) || undefined });
        }}
      >
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} spacing="sm">
          <Select
            label={t('audit.filters.actor')}
            data={(users.data?.items ?? []).map((u) => ({
              value: u.id,
              label: `${u.name} (${u.email})`,
            }))}
            value={search.actor ?? null}
            searchable
            clearable
            onChange={(value) => {
              set({ actor: value ?? undefined });
            }}
          />
          <Select
            label={t('audit.filters.customer')}
            data={(directory.data ?? []).map((c) => ({
              value: c.customer.id,
              label: c.customer.name,
            }))}
            value={search.customer ?? null}
            searchable
            clearable
            onChange={(value) => {
              set({ customer: value ?? undefined });
            }}
          />
          <TextInput
            key={search.action ?? ''}
            name="action"
            label={t('audit.filters.action')}
            description={t('audit.filters.actionHint')}
            defaultValue={search.action ?? ''}
          />
          <TextInput
            type="date"
            label={t('audit.filters.from')}
            value={search.from ?? ''}
            onChange={(event) => {
              set({ from: event.currentTarget.value || undefined });
            }}
          />
          <TextInput
            type="date"
            label={t('audit.filters.to')}
            value={search.to ?? ''}
            onChange={(event) => {
              set({ to: event.currentTarget.value || undefined });
            }}
          />
        </SimpleGrid>
        <Group mt="sm">
          <Button type="submit" variant="default">
            {t('audit.filters.apply')}
          </Button>
          <Button
            variant="subtle"
            onClick={() => {
              void navigate({ search: {} });
            }}
          >
            {t('audit.filters.clear')}
          </Button>
        </Group>
      </form>
      {found.isPending && <Loader aria-label={t('common.loading')} />}
      {found.isError && <Alert color="red">{t('common.error')}</Alert>}
      {found.data && (
        <>
          <Text size="sm">{t('audit.count', { count: found.data.total })}</Text>
          {found.data.items.length === 0 ? (
            <Text c="dimmed">{t('audit.empty')}</Text>
          ) : (
            <ScrollTable label={t('audit.table')} minWidth={960}>
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('audit.columns.at')}</Table.Th>
                    <Table.Th>{t('audit.columns.action')}</Table.Th>
                    <Table.Th>{t('audit.columns.actor')}</Table.Th>
                    <Table.Th>{t('audit.columns.customer')}</Table.Th>
                    <Table.Th>{t('audit.columns.target')}</Table.Th>
                    <Table.Th>{t('audit.columns.details')}</Table.Th>
                    <Table.Th>{t('audit.columns.ip')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {found.data.items.map((event) => (
                    <Table.Tr key={event.id}>
                      <Table.Td>{formatDateTime(event.at)}</Table.Td>
                      <Table.Td>
                        <Code>{event.action}</Code>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{person(event.actor_id)}</Text>
                        {event.real_actor_id && event.real_actor_id !== event.actor_id && (
                          <Text size="xs" c="dimmed">
                            {t('audit.realActor', { name: person(event.real_actor_id) })}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        {event.customer_id
                          ? (customerName.get(event.customer_id) ?? event.customer_id)
                          : '—'}
                      </Table.Td>
                      <Table.Td>
                        {event.target_type ? (
                          <Text size="xs" ff="monospace">
                            {event.target_type}
                            {event.target_id ? ` ${event.target_id}` : ''}
                          </Text>
                        ) : (
                          '—'
                        )}
                      </Table.Td>
                      <Table.Td>
                        {Object.keys(event.details).length > 0 ? (
                          <Text size="xs" ff="monospace" style={{ wordBreak: 'break-all' }}>
                            {JSON.stringify(event.details)}
                          </Text>
                        ) : (
                          '—'
                        )}
                      </Table.Td>
                      <Table.Td>{event.ip ?? '—'}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollTable>
          )}
          <Pager
            page={search.page ?? 1}
            pages={Math.ceil(found.data.total / AUDIT_PAGE)}
            onPage={(page) => {
              void navigate({ search: (s) => ({ ...s, page: page > 1 ? page : undefined }) });
            }}
          />
        </>
      )}
    </Stack>
  );
}
