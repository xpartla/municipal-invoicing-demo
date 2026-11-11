import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import {
  CASE_FILTERS,
  GROUP_COLUMNS,
  SPLITS,
  casesOf,
  useEvaluation,
  type CaseFilter,
  type EvalReport,
  type Split,
} from '../../features/admin/evaluation';
import { formatDateTime, formatPercent } from '../../lib/format';

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : formatPercent(value);
}

/**
 * Vyhodnotenie (plan §10.9, decision 39), ported from the M3 page: the engine's proposals for
 * the made-up dataset compared with the expected coding: the targets, every metric, the
 * results by supplier and by kind of purchase, and the cases, wrong ones first. The report is
 * the latest `riso eval` run; "Prepočítať" runs it again.
 */
export function EvalPage() {
  const { t } = useTranslation();
  const [split, setSplit] = useState<Split>('heldout');
  const [filter, setFilter] = useState<CaseFilter>('wrong');
  const [refresh, setRefresh] = useState(0);
  const found = useEvaluation(split, refresh);
  const report = found.data;
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Stack gap={0}>
          <Title order={1}>{t('evaluation.title')}</Title>
          <Text size="sm">{t('evaluation.intro')}</Text>
        </Stack>
        <Group align="flex-end">
          <Select
            label={t('evaluation.split')}
            data={SPLITS.map((s) => ({ value: s, label: t(`evaluation.splits.${s}`) }))}
            value={split}
            allowDeselect={false}
            onChange={(value) => {
              const chosen = SPLITS.find((s) => s === value);
              if (chosen) setSplit(chosen);
            }}
            w={200}
          />
          <Button
            variant="default"
            loading={found.isFetching}
            onClick={() => {
              setRefresh((n) => n + 1);
            }}
          >
            {t('evaluation.refresh')}
          </Button>
        </Group>
      </Group>
      {found.isPending && <Loader aria-label={t('evaluation.computing')} />}
      {found.isError && <Alert color="red">{t('common.error')}</Alert>}
      {report && <Report report={report} filter={filter} onFilter={setFilter} />}
    </Stack>
  );
}

function Report({
  report,
  filter,
  onFilter,
}: {
  report: EvalReport;
  filter: CaseFilter;
  onFilter: (filter: CaseFilter) => void;
}) {
  const { t } = useTranslation();
  const metric = (name: string) =>
    t(`evaluation.metrics.${name}` as 'evaluation.metrics.correct', { defaultValue: name });
  const tag = (name: string) =>
    t(`evaluation.tags.${name}` as 'evaluation.tags.energy', { defaultValue: name });
  const groups: [string, Record<string, { value: number | null; n: number }>][] = [
    ...Object.entries(report.by_supplier).map(
      ([name, group]) =>
        [name === 'known' ? t('evaluation.known') : t('evaluation.new'), group] as [
          string,
          Record<string, { value: number | null; n: number }>,
        ],
    ),
    ...Object.entries(report.by_tag).map(
      ([name, group]) =>
        [tag(name), group] as [string, Record<string, { value: number | null; n: number }>],
    ),
  ];
  const cases = casesOf(report, filter);
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        {t('evaluation.about', {
          count: report.cases.length,
          memory:
            report.memory === 'frozen'
              ? t('evaluation.memory.frozen', { count: report.precedent_cases })
              : t('evaluation.memory.online'),
          at: formatDateTime(report.generated_at),
          digest: report.dataset_sha256.slice(0, 12),
        })}
      </Text>
      <SimpleGrid
        cols={{ base: 1, sm: 2, lg: 4 }}
        spacing="sm"
        role="list"
        aria-label={t('evaluation.targets')}
      >
        {report.targets.map((target) => (
          <Paper key={target.metric} withBorder p="sm" radius="md" role="listitem">
            <Text size="sm">{metric(target.metric)}</Text>
            <Text fz="xl" fw={650}>
              {percent(target.value)}
            </Text>
            <Group gap={6}>
              <Badge color={target.met ? 'teal' : 'orange'}>
                {target.met ? t('evaluation.met') : t('evaluation.notMet')}
              </Badge>
              <Text size="xs">{t('evaluation.target', { value: percent(target.target) })}</Text>
            </Group>
          </Paper>
        ))}
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Paper withBorder p="md" radius="md">
          <Title order={2} size="h4" mb="sm">
            {t('evaluation.metricsTitle')}
          </Title>
          <ScrollTable label={t('evaluation.metricsTitle')} minWidth={360}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('evaluation.metric')}</Table.Th>
                  <Table.Th ta="right">{t('evaluation.value')}</Table.Th>
                  <Table.Th ta="right">{t('evaluation.count')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {Object.entries(report.metrics).map(([name, rate]) => (
                  <Table.Tr key={name}>
                    <Table.Td>{metric(name)}</Table.Td>
                    <Table.Td ta="right">{percent(rate.value)}</Table.Td>
                    <Table.Td ta="right">
                      {t('evaluation.of', { hits: rate.hits, n: rate.n })}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        </Paper>
        <Paper withBorder p="md" radius="md">
          <Title order={2} size="h4" mb="sm">
            {t('evaluation.groupsTitle')}
          </Title>
          <ScrollTable label={t('evaluation.groupsTitle')} minWidth={560}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('evaluation.group')}</Table.Th>
                  <Table.Th ta="right">{t('evaluation.count')}</Table.Th>
                  {GROUP_COLUMNS.map((key) => (
                    <Table.Th key={key} ta="right">
                      {t(`evaluation.columns.${key}`)}
                    </Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {groups.map(([label, group]) => (
                  <Table.Tr key={label}>
                    <Table.Td>{label}</Table.Td>
                    <Table.Td ta="right">{group.correct?.n ?? 0}</Table.Td>
                    {GROUP_COLUMNS.map((key) => (
                      <Table.Td key={key} ta="right">
                        {percent(group[key]?.value)}
                      </Table.Td>
                    ))}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        </Paper>
      </SimpleGrid>

      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm" wrap="wrap">
          <Title order={2} size="h4">
            {t('evaluation.casesTitle')}
          </Title>
          <SegmentedControl
            size="xs"
            aria-label={t('evaluation.filter')}
            value={filter}
            onChange={(value) => {
              const chosen = CASE_FILTERS.find((f) => f === value);
              if (chosen) onFilter(chosen);
            }}
            data={CASE_FILTERS.map((f) => ({ value: f, label: t(`evaluation.filters.${f}`) }))}
          />
        </Group>
        {cases.length === 0 ? (
          <Text c="dimmed">{t('evaluation.noCases')}</Text>
        ) : (
          <ScrollTable label={t('evaluation.casesTitle')} minWidth={760}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('evaluation.case')}</Table.Th>
                  <Table.Th>{t('evaluation.expected')}</Table.Th>
                  <Table.Th>{t('evaluation.proposed')}</Table.Th>
                  <Table.Th>{t('evaluation.result')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {cases.map((item) => (
                  <Table.Tr key={item.case_id}>
                    <Table.Td>
                      <Text size="sm">{item.supplier ?? item.case_id}</Text>
                      <Text size="xs" c="dimmed" ff="monospace">
                        {item.case_id}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Lines
                        lines={item.expected}
                        empty={
                          item.expected_outcome === 'manual_entry'
                            ? t('evaluation.manual')
                            : t('evaluation.noProposal')
                        }
                      />
                    </Table.Td>
                    <Table.Td>
                      <Lines lines={item.proposed} empty={t('evaluation.noProposal')} />
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        <Badge color={item.correct ? 'teal' : 'red'}>
                          {item.correct ? t('evaluation.correct') : t('evaluation.wrong')}
                        </Badge>
                        <Badge color={item.needs_review ? 'yellow' : 'gray'}>
                          {item.needs_review ? t('evaluation.review') : t('evaluation.noReview')}
                        </Badge>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        )}
      </Paper>
    </Stack>
  );
}

function Lines({
  lines,
  empty,
}: {
  lines: EvalReport['cases'][number]['expected'];
  empty: string;
}) {
  if (!lines?.length) return <Text size="sm">{empty}</Text>;
  return (
    <Stack gap={2}>
      {lines.map((line, n) => (
        <Text key={n} size="xs" ff="monospace">
          {line.key} · {line.md} / {line.dal}
        </Text>
      ))}
    </Stack>
  );
}
