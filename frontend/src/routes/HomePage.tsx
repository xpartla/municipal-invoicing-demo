import { Alert, Group, Loader, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import {
  AttentionCard,
  BudgetCard,
  ByTypeCard,
  KpiTiles,
  OnboardingChecklist,
  ReviewCard,
  SeriesCard,
  SuppliersCard,
  UnitsCard,
} from '../features/reporting/DashboardParts';
import { useMe } from '../features/identity/api';
import { MonthsChart, PerDayChart } from '../features/reporting/DashboardCharts';
import { MonthPicker } from '../features/reporting/MonthPicker';
import { currentMonth, useDashboard } from '../features/reporting/dashboard';

/**
 * Domov (plan §10.2, decision 67): a customer's month. The tiles open the invoice table
 * filtered like them; the charts have a table view; "Vyžaduje pozornosť", the number series
 * and the onboarding checklist are about now. The month is in the URL.
 */
export function HomePage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId/' });
  const search = useSearch({ from: '/_app/c/$customerId/' });
  const navigate = useNavigate({ from: '/c/$customerId/' });
  const latest = currentMonth();
  const month = search.month ?? latest;
  const found = useDashboard(customerId, month);
  const data = found.data;
  const { data: me } = useMe();
  const name = me?.customers.find((c) => c.id === customerId)?.name ?? '';

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Stack gap={0}>
          <Title order={1}>{t('home.title')}</Title>
          <Text size="sm">{t('home.intro', { name })}</Text>
        </Stack>
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
      {data && (
        <>
          {!data.onboarding.done && (
            <OnboardingChecklist customerId={customerId} onboarding={data.onboarding} />
          )}
          <KpiTiles customerId={customerId} month={data.month} tiles={data.tiles} />
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <AttentionCard customerId={customerId} attention={data.attention} />
            <SeriesCard customerId={customerId} year={data.onboarding.year} />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <PerDayChart days={data.per_day} />
            <MonthsChart months={data.months} />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <ReviewCard review={data.review} />
            <ByTypeCard types={data.by_type} />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <SuppliersCard kind="count" suppliers={data.suppliers_by_count} />
            <SuppliersCard kind="amount" suppliers={data.suppliers_by_amount} />
          </SimpleGrid>
          <UnitsCard units={data.units} />
          {data.budget && <BudgetCard budget={data.budget} />}
        </>
      )}
    </Stack>
  );
}
