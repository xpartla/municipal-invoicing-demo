import { BarChart } from '@mantine/charts';
import { Group, Paper, SegmentedControl, Stack, Table, Text, Title } from '@mantine/core';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { formatAmount, formatDate } from '../../lib/format';
import { monthLabel, type Dashboard } from './dashboard';

type View = 'chart' | 'table';

/**
 * A chart with its text alternatives: a one-line summary under it, and the same numbers as
 * a table one click away (plan §10.2; WCAG 1.1.1). Without anything to draw, the summary
 * alone.
 */
function ChartCard({
  title,
  summary,
  empty,
  chart,
  table,
}: {
  title: string;
  summary: string;
  empty: boolean;
  chart: React.ReactNode;
  table: React.ReactNode;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [view, setView] = useState<View>('chart');
  return (
    <Paper withBorder p="md" radius="md" component="section" aria-labelledby={id}>
      <Stack gap="sm">
        <Group justify="space-between" wrap="wrap" gap="xs">
          <Title order={2} size="h4" id={id}>
            {title}
          </Title>
          {!empty && (
            <SegmentedControl
              size="xs"
              aria-label={t('home.view.label', { title })}
              value={view}
              onChange={(value) => {
                setView(value === 'table' ? 'table' : 'chart');
              }}
              data={[
                { value: 'chart', label: t('home.view.chart') },
                { value: 'table', label: t('home.view.table') },
              ]}
            />
          )}
        </Group>
        {!empty && (view === 'chart' ? chart : table)}
        <Text size="sm" c="dimmed">
          {summary}
        </Text>
      </Stack>
    </Paper>
  );
}

export function PerDayChart({ days }: { days: Dashboard['per_day'] }) {
  const { t } = useTranslation();
  const title = t('home.perDay.title');
  const count = days.reduce((n, d) => n + d.count, 0);
  const busiest = days.reduce<Dashboard['per_day'][number] | null>(
    (best, d) => (d.count > (best?.count ?? 0) ? d : best),
    null,
  );
  const summary = busiest
    ? t('home.perDay.summary', {
        count,
        busiest: formatDate(busiest.day),
        most: busiest.count,
      })
    : t('home.perDay.none');
  return (
    <ChartCard
      title={title}
      summary={summary}
      empty={count === 0}
      chart={
        <BarChart
          h={220}
          data={days.map((d) => ({ day: String(Number(d.day.slice(8))), count: d.count }))}
          dataKey="day"
          series={[{ name: 'count', label: t('home.perDay.count'), color: 'riso.6' }]}
          tickLine="y"
          gridAxis="x"
          yAxisProps={{ allowDecimals: false }}
        />
      }
      table={
        <ScrollTable label={t('home.tableOf', { title })} minWidth={320}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.perDay.day')}</Table.Th>
                <Table.Th ta="right">{t('home.perDay.count')}</Table.Th>
                <Table.Th ta="right">{t('home.perDay.total')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {days
                .filter((d) => d.count > 0)
                .map((d) => (
                  <Table.Tr key={d.day}>
                    <Table.Td>{formatDate(d.day)}</Table.Td>
                    <Table.Td ta="right">{d.count}</Table.Td>
                    <Table.Td ta="right">{formatAmount(d.total)}</Table.Td>
                  </Table.Tr>
                ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      }
    />
  );
}

/** `2026-11` → `11/26`, short enough for twelve bars on a phone. */
function shortMonth(month: string): string {
  return `${month.slice(5)}/${month.slice(2, 4)}`;
}

export function MonthsChart({ months }: { months: Dashboard['months'] }) {
  const { t } = useTranslation();
  const title = t('home.months.title');
  const total = months.reduce((sum, m) => sum + m.total, 0);
  const count = months.reduce((n, m) => n + m.count, 0);
  const first = months[0]?.month ?? '';
  const last = months.at(-1)?.month ?? '';
  return (
    <ChartCard
      title={title}
      summary={t('home.months.summary', {
        from: monthLabel(first),
        to: monthLabel(last),
        count,
        total: formatAmount(total),
      })}
      empty={count === 0}
      chart={
        <BarChart
          h={220}
          data={months.map((m) => ({ month: shortMonth(m.month), total: m.total }))}
          dataKey="month"
          series={[{ name: 'total', label: t('home.months.total'), color: 'riso.6' }]}
          tickLine="y"
          gridAxis="x"
          valueFormatter={(value) => formatAmount(value)}
          yAxisProps={{ width: 90 }}
        />
      }
      table={
        <ScrollTable label={t('home.tableOf', { title })} minWidth={320}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.months.month')}</Table.Th>
                <Table.Th ta="right">{t('home.months.count')}</Table.Th>
                <Table.Th ta="right">{t('home.months.total')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {months.map((m) => (
                <Table.Tr key={m.month}>
                  <Table.Td>{monthLabel(m.month)}</Table.Td>
                  <Table.Td ta="right">{m.count}</Table.Td>
                  <Table.Td ta="right">{formatAmount(m.total)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      }
    />
  );
}
