import {
  Alert,
  Badge,
  Group,
  Loader,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../components/RouterLinks';
import { ScrollTable } from '../components/ScrollTable';
import { useMe } from '../features/identity/api';
import { onPlatform } from '../features/identity/capabilities';
import { MonthPicker } from '../features/reporting/MonthPicker';
import { currentMonth } from '../features/reporting/dashboard';
import { useProviderOverview, type ProviderOverview } from '../features/reporting/overview';
import { useProviders } from '../features/tenancy/api';
import { formatDateTime } from '../lib/format';

const TOTALS = [
  'customers',
  'uploaded',
  'waiting',
  'review',
  'failed',
  'booked',
  'missing_lists',
  'open_imports',
] as const;

/**
 * Prehľad klientov (plan §10.8, decision 67): the provider's customers with the month's
 * numbers, the totals first; each customer's name opens it. Staff see their provider; admins
 * choose one. The month and the provider are in the URL.
 */
export function ProviderOverviewPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const search = useSearch({ from: '/_app/provider' });
  const navigate = useNavigate({ from: '/provider' });
  const admin = me ? onPlatform(me, 'provider.overview') : false;
  const providers = useProviders(admin);
  const choices = admin
    ? (providers.data ?? [])
        .filter((p) => p.provider.status === 'active')
        .map((p) => ({ value: p.provider.id, label: p.provider.name }))
    : (me?.providers ?? []).map((p) => ({ value: p.id, label: p.name }));
  const providerId = choices.some((c) => c.value === search.provider)
    ? search.provider
    : choices[0]?.value;
  const latest = currentMonth();
  const month = search.month ?? latest;
  const found = useProviderOverview(providerId, month);
  const overview = found.data;

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Title order={1}>{t('overview.title')}</Title>
        <Group align="flex-end" wrap="wrap">
          {(admin || choices.length > 1) && choices.length > 0 && (
            <Select
              label={t('overview.provider')}
              data={choices}
              value={providerId ?? null}
              allowDeselect={false}
              onChange={(value) => {
                if (value) void navigate({ search: (s) => ({ ...s, provider: value }) });
              }}
              w={260}
            />
          )}
          <MonthPicker
            value={month}
            latest={latest}
            onChange={(next) => {
              void navigate({
                search: (s) => ({ ...s, month: next === latest ? undefined : next }),
              });
            }}
          />
        </Group>
      </Group>
      {!admin && choices.length === 1 && overview && (
        <Text size="sm">{overview.provider_name}</Text>
      )}
      {((admin && providers.isPending) || (providerId !== undefined && found.isPending)) && (
        <Loader aria-label={t('common.loading')} />
      )}
      {found.isError && <Alert color="red">{t('common.error')}</Alert>}
      {admin && providers.isSuccess && choices.length === 0 && (
        <Text c="dimmed">{t('overview.noProviders')}</Text>
      )}
      {overview && <Overview overview={overview} />}
    </Stack>
  );
}

function Overview({ overview }: { overview: ProviderOverview }) {
  const { t } = useTranslation();
  const label = t('overview.table');
  return (
    <>
      <SimpleGrid
        cols={{ base: 2, sm: 4, lg: 8 }}
        spacing="sm"
        role="list"
        aria-label={t('overview.totals')}
      >
        {TOTALS.map((key) => (
          <Paper key={key} withBorder p="sm" radius="md" role="listitem">
            <Text size="sm">{t(`overview.columns.${key}`)}</Text>
            <Text fz="xl" fw={650}>
              {overview.totals[key]}
            </Text>
          </Paper>
        ))}
      </SimpleGrid>
      {overview.rows.length === 0 ? (
        <Text c="dimmed">{t('overview.empty')}</Text>
      ) : (
        <ScrollTable label={label} minWidth={960}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('overview.columns.customer')}</Table.Th>
                <Table.Th ta="right">{t('overview.columns.uploaded')}</Table.Th>
                <Table.Th ta="right">{t('overview.columns.waiting')}</Table.Th>
                <Table.Th ta="right">{t('overview.columns.review')}</Table.Th>
                <Table.Th ta="right">{t('overview.columns.failed')}</Table.Th>
                <Table.Th ta="right">{t('overview.columns.booked')}</Table.Th>
                <Table.Th>{t('overview.columns.last_activity')}</Table.Th>
                <Table.Th>{t('overview.columns.codelists')}</Table.Th>
                <Table.Th ta="right">{t('overview.columns.open_imports')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {overview.rows.map((row) => (
                <Table.Tr key={row.customer_id}>
                  <Table.Td>
                    <AnchorLink
                      to="/c/$customerId"
                      params={{ customerId: row.customer_id }}
                      size="sm"
                      fw={600}
                    >
                      {row.name}
                    </AnchorLink>
                    <Text size="xs" c="dimmed">
                      {t('overview.ico', { ico: row.ico })}
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right">{row.uploaded}</Table.Td>
                  <Table.Td ta="right">{row.waiting}</Table.Td>
                  <Table.Td ta="right">{row.review}</Table.Td>
                  <Table.Td ta="right">{row.failed}</Table.Td>
                  <Table.Td ta="right">{row.booked}</Table.Td>
                  <Table.Td>
                    {row.last_activity ? formatDateTime(row.last_activity) : t('overview.never')}
                  </Table.Td>
                  <Table.Td>
                    {row.missing_lists.length === 0 ? (
                      <Badge color="teal">{t('overview.listsReady')}</Badge>
                    ) : (
                      <Stack gap={2}>
                        <Badge color="orange">{t('overview.listsMissing')}</Badge>
                        <Text size="xs">
                          {row.missing_lists
                            .map((kind) =>
                              t(`codelists.kinds.${kind}` as 'codelists.kinds.accounts', {
                                defaultValue: kind,
                              }),
                            )
                            .join(', ')}
                        </Text>
                      </Stack>
                    )}
                  </Table.Td>
                  <Table.Td ta="right">
                    {row.open_imports > 0 ? (
                      <AnchorLink
                        to="/c/$customerId/exchange"
                        params={{ customerId: row.customer_id }}
                        size="sm"
                        aria-label={t('overview.openImports', {
                          count: row.open_imports,
                          name: row.name,
                        })}
                      >
                        {row.open_imports}
                      </AnchorLink>
                    ) : (
                      0
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
    </>
  );
}
