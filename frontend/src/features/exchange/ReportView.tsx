import { Badge, Group, SimpleGrid, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import type { ImportType, Issue, Report } from './api';
import { rowsText } from './mapping';
import { useIssueText } from './texts';

function IssueTable({
  issues,
  label,
  kind,
}: {
  issues: readonly Issue[];
  label: string;
  kind: 'error' | 'warning';
}) {
  const { t } = useTranslation();
  const text = useIssueText();
  return (
    <ScrollTable label={label} minWidth={720}>
      <Table withTableBorder striped fz="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th scope="col">{t('exchange.report.rows')}</Table.Th>
            <Table.Th scope="col">{t('exchange.report.what')}</Table.Th>
            <Table.Th scope="col">{t('exchange.report.issue')}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {issues.map((issue, index) => (
            <Table.Tr key={index}>
              <Table.Td>{rowsText(issue.rows)}</Table.Td>
              <Table.Td>
                <Text size="sm" ff="monospace">
                  {issue.key ??
                    issue.value ??
                    (issue.field
                      ? t(`exchange.fields.${issue.field}`, { defaultValue: issue.field })
                      : '—')}
                </Text>
              </Table.Td>
              <Table.Td>
                <Group gap={6} wrap="nowrap" align="flex-start">
                  {kind === 'error' && (
                    <Badge size="xs" color={issue.confirmable ? 'orange' : 'red'} variant="light">
                      {issue.confirmable
                        ? t('exchange.report.confirmable')
                        : t('exchange.report.hard')}
                    </Badge>
                  )}
                  <Text size="sm">{text(issue)}</Text>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollTable>
  );
}

/** A few entries as a table, their fields as columns. */
function Entries({ rows, label }: { rows: readonly Record<string, unknown>[]; label: string }) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        {t('exchange.report.nothing')}
      </Text>
    );
  }
  const hidden = new Set(['row', 'rows', 'aliases', 'active']);
  const columns = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((c) => !hidden.has(c));
  const cell = (value: unknown): string => {
    if (value === null || value === undefined) return '';
    if (Array.isArray(value)) return t('exchange.report.lines', { count: value.length });
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return JSON.stringify(value);
  };
  return (
    <ScrollTable label={label} minWidth={Math.min(columns.length * 150, 1400)}>
      <Table withTableBorder striped fz="sm">
        <Table.Thead>
          <Table.Tr>
            {columns.map((c) => (
              <Table.Th key={c} scope="col">
                {t(`exchange.fields.${c}` as 'exchange.fields.su', { defaultValue: c })}
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, i) => (
            <Table.Tr key={i}>
              {columns.map((c) => (
                <Table.Td key={c}>{cell(row[c])}</Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollTable>
  );
}

const EMPTY_DIFF: NonNullable<Report['diff']> = {
  base_version_id: null,
  base_number: null,
  added: 0,
  removed: 0,
  changed: 0,
  unchanged: 0,
  added_sample: [],
  removed_sample: [],
  changed_sample: [],
};

function Count({ label, value }: { label: string; value: number }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={600} size="lg">
        {value}
      </Text>
    </Stack>
  );
}

/** Step 4: the dry run's report: what was read, the errors per row, the warnings, the
 * difference from the active version and the first entries. */
export function ReportView({ report, importType }: { report: Report; importType: ImportType }) {
  const { t } = useTranslation();
  const bookings = importType === 'past_bookings';
  const diff = report.diff ?? EMPTY_DIFF;
  const errors = report.errors;
  const warnings = report.warnings;
  const changed = diff.changed_sample.map((c) => ({ key: c.key, ...c.after }));

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 2, sm: bookings ? 5 : 6 }}>
        <Count label={t('exchange.report.rowsRead')} value={report.rows_read} />
        <Count
          label={t(bookings ? 'exchange.report.bookings' : 'exchange.report.entries')}
          value={report.entries}
        />
        <Count
          label={t(bookings ? 'exchange.report.newBookings' : 'exchange.report.added')}
          value={diff.added}
        />
        {!bookings && <Count label={t('exchange.report.changed')} value={diff.changed} />}
        {!bookings && <Count label={t('exchange.report.removed')} value={diff.removed} />}
        <Count
          label={t(bookings ? 'exchange.report.present' : 'exchange.report.unchanged')}
          value={diff.unchanged}
        />
        {bookings && <Count label={t('exchange.report.numbersUsed')} value={report.numbers_used} />}
      </SimpleGrid>
      {!bookings && (
        <Text size="sm">
          {diff.base_number
            ? t('exchange.report.against', { number: diff.base_number })
            : t('exchange.report.first')}
          {report.period ? ` ${t('exchange.report.period', { period: report.period })}` : ''}
        </Text>
      )}
      {bookings && report.counters.length > 0 && (
        <Stack gap={4}>
          <Title order={3} size="h5">
            {t('exchange.report.counters')}
          </Title>
          {report.counters.map((c) => (
            <Text key={c.key} size="sm">
              {t('exchange.report.counterRise', { key: c.key, before: c.before, after: c.after })}
            </Text>
          ))}
        </Stack>
      )}
      <Title order={3} size="h4">
        {t('exchange.report.errors', { count: errors.length })}
      </Title>
      {errors.length > 0 ? (
        <IssueTable issues={errors} label={t('exchange.report.errorsLabel')} kind="error" />
      ) : (
        <Text size="sm">{t('exchange.report.noErrors')}</Text>
      )}
      <Title order={3} size="h4">
        {t('exchange.report.warnings', { count: warnings.length })}
      </Title>
      {warnings.length > 0 ? (
        <IssueTable issues={warnings} label={t('exchange.report.warningsLabel')} kind="warning" />
      ) : (
        <Text size="sm">{t('exchange.report.noWarnings')}</Text>
      )}
      <Tabs defaultValue="preview" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="preview">{t('exchange.report.preview')}</Tabs.Tab>
          <Tabs.Tab value="added">
            {t(bookings ? 'exchange.report.newBookings' : 'exchange.report.added')}
          </Tabs.Tab>
          {!bookings && <Tabs.Tab value="changed">{t('exchange.report.changed')}</Tabs.Tab>}
          {!bookings && <Tabs.Tab value="removed">{t('exchange.report.removed')}</Tabs.Tab>}
        </Tabs.List>
        <Tabs.Panel value="preview" pt="sm">
          <Entries rows={report.preview} label={t('exchange.report.preview')} />
        </Tabs.Panel>
        <Tabs.Panel value="added" pt="sm">
          <Entries rows={diff.added_sample} label={t('exchange.report.added')} />
        </Tabs.Panel>
        <Tabs.Panel value="changed" pt="sm">
          <Entries rows={changed} label={t('exchange.report.changed')} />
        </Tabs.Panel>
        <Tabs.Panel value="removed" pt="sm">
          <Entries rows={diff.removed_sample} label={t('exchange.report.removed')} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
