import { Alert, Group, Loader, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../../components/RouterLinks';
import { MonthPicker } from '../../features/reporting/MonthPicker';
import { currentMonth, monthLabel } from '../../features/reporting/dashboard';
import { usePlatformCounts, type PlatformCounts } from '../../features/reporting/overview';

type Count = Exclude<keyof PlatformCounts, 'month' | 'login_users'>;

/** Where each count leads, when somewhere. */
const TILES: {
  key: Count;
  to?: '/admin/providers' | '/users' | '/admin/jobs' | '/admin/audit' | '/admin/outbox';
}[] = [
  { key: 'providers', to: '/admin/providers' },
  { key: 'customers', to: '/users' },
  { key: 'users', to: '/users' },
  { key: 'invoices' },
  { key: 'ocr_pages' },
  { key: 'failed_jobs', to: '/admin/jobs' },
  { key: 'logins', to: '/admin/audit' },
  { key: 'unsent_mail', to: '/admin/outbox' },
];

/**
 * Platforma (plan §10.9, decision 67): the platform's counts; the invoices and the pages
 * read by OCR are the chosen month's, the logins the last 7 days'. Each count leads to its
 * screen where there is one.
 */
export function PlatformPage() {
  const { t } = useTranslation();
  const search = useSearch({ from: '/_app/admin' });
  const navigate = useNavigate({ from: '/admin' });
  const latest = currentMonth();
  const month = search.month ?? latest;
  const found = usePlatformCounts(month);
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Title order={1}>{t('platform.title')}</Title>
        <MonthPicker
          value={month}
          latest={latest}
          onChange={(next) => {
            void navigate({ search: { month: next === latest ? undefined : next } });
          }}
        />
      </Group>
      {found.isPending && <Loader aria-label={t('common.loading')} />}
      {found.isError && <Alert color="red">{t('common.error')}</Alert>}
      {found.data && <Counts counts={found.data} />}
    </Stack>
  );
}

function Counts({ counts }: { counts: PlatformCounts }) {
  const { t } = useTranslation();
  const hint = (key: Count) => {
    if (key === 'invoices' || key === 'ocr_pages') return monthLabel(counts.month);
    if (key === 'logins') return t('platform.hints.logins', { count: counts.login_users });
    return null;
  };
  return (
    <SimpleGrid
      cols={{ base: 2, sm: 4 }}
      spacing="sm"
      role="list"
      aria-label={t('platform.counts')}
    >
      {TILES.map(({ key, to }) => {
        const body = (
          <>
            <Text size="sm">{t(`platform.tiles.${key}`)}</Text>
            <Text fz="xl" fw={650}>
              {counts[key]}
            </Text>
            {hint(key) && (
              <Text size="xs" c="dimmed">
                {hint(key)}
              </Text>
            )}
          </>
        );
        return (
          <Paper key={key} withBorder p="sm" radius="md" role="listitem">
            {to ? (
              <AnchorLink to={to} underline="hover" c="inherit" display="block">
                {body}
              </AnchorLink>
            ) : (
              body
            )}
          </Paper>
        );
      })}
    </SimpleGrid>
  );
}
