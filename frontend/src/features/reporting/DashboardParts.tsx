import {
  Group,
  List,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconCircle, IconCircleCheck } from '@tabler/icons-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../../components/RouterLinks';
import { ScrollTable } from '../../components/ScrollTable';
import { formatAmount, formatDateTime, formatPercent } from '../../lib/format';
import { useNumberSeries } from '../invoices/api';
import { OPEN_STATES } from '../invoices/search';
import {
  durationParts,
  tileSearch,
  type AttentionItem,
  type Dashboard,
  type TileKey,
} from './dashboard';

const TILES: readonly TileKey[] = [
  'uploaded',
  'waiting',
  'review',
  'failed',
  'booked',
  'booked_total',
];

/** A titled card; its heading names the region. */
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <Paper withBorder p="md" radius="md" component="section" aria-labelledby={id}>
      <Stack gap="sm">
        <Title order={2} size="h4" id={id}>
          {title}
        </Title>
        {children}
      </Stack>
    </Paper>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <Text size="sm" c="dimmed">
      {children}
    </Text>
  );
}

/** The KPI tiles; each opens the invoice table filtered like it (plan §10.2). */
export function KpiTiles({
  customerId,
  month,
  tiles,
}: {
  customerId: string;
  month: string;
  tiles: Dashboard['tiles'];
}) {
  const { t } = useTranslation();
  return (
    <SimpleGrid
      cols={{ base: 2, sm: 3, lg: 6 }}
      spacing="sm"
      role="list"
      aria-label={t('home.tiles.label')}
    >
      {TILES.map((key) => (
        <Paper key={key} withBorder p="sm" radius="md" role="listitem">
          <AnchorLink
            to="/c/$customerId/invoices"
            params={{ customerId }}
            search={tileSearch(key, month)}
            underline="hover"
            c="inherit"
            display="block"
          >
            <Text size="sm">{t(`home.tiles.${key}`)}</Text>
            <Text fz="xl" fw={650}>
              {key === 'booked_total' ? formatAmount(tiles[key]) : tiles[key]}
            </Text>
          </AnchorLink>
        </Paper>
      ))}
    </SimpleGrid>
  );
}

function itemName(item: AttentionItem): string {
  return item.supplier_name ?? item.source_ref ?? item.id;
}

function AttentionItems({
  customerId,
  items,
  title,
}: {
  customerId: string;
  items: AttentionItem[];
  title: string;
}) {
  const { t } = useTranslation();
  return (
    <Stack gap={4}>
      <Text size="sm" fw={600}>
        {title}
      </Text>
      <List size="sm" spacing={2} listStyleType="none" aria-label={title}>
        {items.map((item) => (
          <List.Item key={item.id}>
            <AnchorLink
              to="/c/$customerId/invoices/$invoiceId"
              params={{ customerId, invoiceId: item.id }}
              size="sm"
              underline="always"
            >
              {itemName(item)}
            </AnchorLink>{' '}
            <Text span size="sm" c="dimmed">
              {t('home.attention.uploaded', { at: formatDateTime(item.uploaded_at) })}
            </Text>
          </List.Item>
        ))}
      </List>
    </Stack>
  );
}

/** "Vyžaduje pozornosť": failed extractions, the invoices waiting longest and the warnings,
 * whatever the month. */
export function AttentionCard({
  customerId,
  attention,
}: {
  customerId: string;
  attention: Dashboard['attention'];
}) {
  const { t } = useTranslation();
  const nothing =
    attention.failed_total === 0 &&
    attention.waiting_total === 0 &&
    attention.warnings.length === 0;
  return (
    <Card title={t('home.attention.title')}>
      {nothing && <Empty>{t('home.attention.nothing')}</Empty>}
      {attention.warnings.length > 0 && (
        <List size="sm" spacing={4} aria-label={t('home.attention.warnings')}>
          {attention.warnings.map((w) => (
            <List.Item key={`${w.code}-${w.subject}`}>
              {w.code === 'list_missing' ? (
                <AnchorLink to="/c/$customerId/codelists" params={{ customerId }} size="sm">
                  {t('home.attention.listMissing', {
                    list: t(`codelists.kinds.${w.subject}` as 'codelists.kinds.accounts', {
                      defaultValue: w.subject,
                    }),
                  })}
                </AnchorLink>
              ) : (
                <AnchorLink
                  to="/c/$customerId/system"
                  params={{ customerId }}
                  search={{ tab: 'health' }}
                  size="sm"
                >
                  {t(`home.attention.codes.${w.code}` as 'home.attention.codes.knowledge_missing', {
                    defaultValue: t('home.attention.otherWarning', { subject: w.subject }),
                  })}
                </AnchorLink>
              )}
            </List.Item>
          ))}
        </List>
      )}
      {attention.failed_total > 0 && (
        <>
          <AttentionItems
            customerId={customerId}
            items={attention.failed}
            title={t('home.attention.failed', { count: attention.failed_total })}
          />
          <AnchorLink
            to="/c/$customerId/invoices"
            params={{ customerId }}
            search={{ state: ['extraction_failed'] }}
            size="sm"
          >
            {t('home.attention.allFailed')}
          </AnchorLink>
        </>
      )}
      {attention.waiting_total > 0 && (
        <>
          <AttentionItems
            customerId={customerId}
            items={attention.waiting}
            title={t('home.attention.waiting', { count: attention.waiting_total })}
          />
          <AnchorLink
            to="/c/$customerId/invoices"
            params={{ customerId }}
            search={{ state: [...OPEN_STATES], sort: 'uploaded_at' }}
            size="sm"
          >
            {t('home.attention.allWaiting')}
          </AnchorLink>
        </>
      )}
    </Card>
  );
}

/** The number series of the year: last used, next and gaps (plan §10.2). */
export function SeriesCard({ customerId, year }: { customerId: string; year: number }) {
  const { t } = useTranslation();
  const found = useNumberSeries(customerId, year);
  const series = found.data?.items ?? [];
  const title = t('home.series.title', { year });
  return (
    <Card title={title}>
      {found.isSuccess && series.length === 0 && <Empty>{t('home.series.none')}</Empty>}
      {series.length > 0 && (
        <ScrollTable label={t('home.tableOf', { title })} minWidth={360}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.series.series')}</Table.Th>
                <Table.Th>{t('home.series.last')}</Table.Th>
                <Table.Th>{t('home.series.next')}</Table.Th>
                <Table.Th ta="right">{t('home.series.gaps')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {series.map((s) => (
                <Table.Tr key={s.series}>
                  <Table.Td>{s.series}</Table.Td>
                  <Table.Td>{s.last_used_number ?? '—'}</Table.Td>
                  <Table.Td>{s.next_number}</Table.Td>
                  <Table.Td ta="right">{s.gaps.length}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
      <AnchorLink
        to="/c/$customerId/system"
        params={{ customerId }}
        search={{ tab: 'series' }}
        size="sm"
      >
        {t('home.series.open')}
      </AnchorLink>
    </Card>
  );
}

const STEPS = ['profile', 'codelists', 'health', 'first_booked'] as const;

/** The onboarding checklist, shown until every step is done (plan §10.2). */
export function OnboardingChecklist({
  customerId,
  onboarding,
}: {
  customerId: string;
  onboarding: Dashboard['onboarding'];
}) {
  const { t } = useTranslation();
  const done = STEPS.filter((s) => onboarding[s]).length;
  const link = (step: (typeof STEPS)[number]) => {
    const label = t(`home.onboarding.steps.${step}`, { year: onboarding.year });
    switch (step) {
      case 'profile':
        return (
          <AnchorLink to="/profile" size="sm" underline="always">
            {label}
          </AnchorLink>
        );
      case 'codelists':
        return (
          <AnchorLink
            to="/c/$customerId/codelists"
            params={{ customerId }}
            size="sm"
            underline="always"
          >
            {label}
          </AnchorLink>
        );
      case 'health':
        return (
          <AnchorLink
            to="/c/$customerId/system"
            params={{ customerId }}
            search={{ tab: 'health' }}
            size="sm"
            underline="always"
          >
            {label}
          </AnchorLink>
        );
      case 'first_booked':
        return (
          <AnchorLink
            to="/c/$customerId/invoices"
            params={{ customerId }}
            size="sm"
            underline="always"
          >
            {label}
          </AnchorLink>
        );
    }
  };
  return (
    <Card title={t('home.onboarding.title')}>
      <Text size="sm">{t('home.onboarding.progress', { done, all: STEPS.length })}</Text>
      <List size="sm" spacing={6} listStyleType="none" aria-label={t('home.onboarding.title')}>
        {STEPS.map((step) => (
          <List.Item
            key={step}
            icon={
              <ThemeIcon
                size={20}
                radius="xl"
                variant={onboarding[step] ? 'filled' : 'light'}
                color={onboarding[step] ? 'teal' : 'gray'}
              >
                {onboarding[step] ? (
                  <IconCircleCheck size={14} aria-hidden />
                ) : (
                  <IconCircle size={14} aria-hidden />
                )}
              </ThemeIcon>
            }
          >
            <Group gap={6} wrap="nowrap">
              {link(step)}
              <Text span size="sm" c="dimmed">
                {onboarding[step] ? t('home.onboarding.done') : t('home.onboarding.todo')}
              </Text>
            </Group>
          </List.Item>
        ))}
      </List>
    </Card>
  );
}

/** Review rate and the median time from upload to booking. */
export function ReviewCard({ review }: { review: Dashboard['review'] }) {
  const { t } = useTranslation();
  const durationText = (seconds: number) => {
    const { unit, ...parts } = durationParts(seconds);
    return t(`home.duration.${unit}`, parts);
  };
  return (
    <Card title={t('home.review.title')}>
      <SimpleGrid cols={2} spacing="sm">
        <Stack gap={0}>
          <Text size="sm">{t('home.review.rate')}</Text>
          <Text fz="xl" fw={650}>
            {review.rate === null ? '—' : formatPercent(review.rate)}
          </Text>
          <Text size="xs" c="dimmed">
            {t('home.review.of', { reviewed: review.reviewed, count: review.booked })}
          </Text>
        </Stack>
        <Stack gap={0}>
          <Text size="sm">{t('home.review.median')}</Text>
          <Text fz="xl" fw={650}>
            {review.median_seconds === null ? '—' : durationText(review.median_seconds)}
          </Text>
          <Text size="xs" c="dimmed">
            {t('home.review.medianHint')}
          </Text>
        </Stack>
      </SimpleGrid>
    </Card>
  );
}

/** Booked by type: series × invoice or credit note. */
export function ByTypeCard({ types }: { types: Dashboard['by_type'] }) {
  const { t } = useTranslation();
  const title = t('home.byType.title');
  return (
    <Card title={title}>
      {types.length === 0 ? (
        <Empty>{t('home.noneBooked')}</Empty>
      ) : (
        <ScrollTable label={t('home.tableOf', { title })} minWidth={320}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.byType.series')}</Table.Th>
                <Table.Th>{t('home.byType.kind')}</Table.Th>
                <Table.Th ta="right">{t('home.count')}</Table.Th>
                <Table.Th ta="right">{t('home.total')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {types.map((row) => (
                <Table.Tr key={`${row.series ?? ''}-${String(row.credit_note)}`}>
                  <Table.Td>{row.series ?? '—'}</Table.Td>
                  <Table.Td>
                    {row.credit_note ? t('home.byType.creditNote') : t('home.byType.invoice')}
                  </Table.Td>
                  <Table.Td ta="right">{row.count}</Table.Td>
                  <Table.Td ta="right">{formatAmount(row.total)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
    </Card>
  );
}

/** The top 10 suppliers by count or by amount. */
export function SuppliersCard({
  kind,
  suppliers,
}: {
  kind: 'count' | 'amount';
  suppliers: Dashboard['suppliers_by_count'];
}) {
  const { t } = useTranslation();
  const title = t(`home.suppliers.${kind}`);
  return (
    <Card title={title}>
      {suppliers.length === 0 ? (
        <Empty>{t('home.noneBooked')}</Empty>
      ) : (
        <ScrollTable label={t('home.tableOf', { title })} minWidth={360}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.suppliers.supplier')}</Table.Th>
                <Table.Th ta="right">{t('home.count')}</Table.Th>
                <Table.Th ta="right">{t('home.total')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {suppliers.map((s) => (
                <Table.Tr key={s.ico ?? s.name ?? ''}>
                  <Table.Td>
                    <Text size="sm">{s.name ?? '—'}</Text>
                    {s.ico && (
                      <Text size="xs" c="dimmed">
                        {t('home.suppliers.ico', { ico: s.ico })}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td ta="right">{s.count}</Table.Td>
                  <Table.Td ta="right">{formatAmount(s.total)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
    </Card>
  );
}

/** Booked lines by unit: the function (oddiel and trieda) with the COFOG name. */
export function UnitsCard({ units }: { units: Dashboard['units'] }) {
  const { t } = useTranslation();
  const title = t('home.units.title');
  return (
    <Card title={title}>
      {units.length === 0 ? (
        <Empty>{t('home.noneBooked')}</Empty>
      ) : (
        <ScrollTable label={t('home.tableOf', { title })} minWidth={480}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.units.function')}</Table.Th>
                <Table.Th>{t('home.units.name')}</Table.Th>
                <Table.Th ta="right">{t('home.units.invoices')}</Table.Th>
                <Table.Th ta="right">{t('home.total')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {units.map((u) => (
                <Table.Tr key={u.function}>
                  <Table.Td>{u.code ?? u.function}</Table.Td>
                  <Table.Td>{u.name ?? '—'}</Table.Td>
                  <Table.Td ta="right">{u.invoices}</Table.Td>
                  <Table.Td ta="right">{formatAmount(u.total)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
    </Card>
  );
}

/** The budget drawdown per position, when the budget import carried amounts. */
export function BudgetCard({ budget }: { budget: NonNullable<Dashboard['budget']> }) {
  const { t } = useTranslation();
  const title = t('home.budget.title', { year: budget.year });
  return (
    <Card title={title}>
      <Text size="sm">
        {t('home.budget.summary', {
          drawn: formatAmount(budget.drawn),
          budgeted: formatAmount(budget.budgeted),
        })}
        {budget.elsewhere !== 0 &&
          ` ${t('home.budget.elsewhere', { amount: formatAmount(budget.elsewhere) })}`}
      </Text>
      <ScrollTable label={t('home.tableOf', { title })} minWidth={560}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('home.budget.position')}</Table.Th>
              <Table.Th ta="right">{t('home.budget.budgeted')}</Table.Th>
              <Table.Th ta="right">{t('home.budget.drawn')}</Table.Th>
              <Table.Th w={160}>{t('home.budget.share')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {budget.rows.map((row) => (
              <Table.Tr key={row.key}>
                <Table.Td>
                  <Text size="sm" ff="monospace">
                    {row.key}
                  </Text>
                  {row.description && (
                    <Text size="xs" c="dimmed">
                      {row.description}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td ta="right">{formatAmount(row.budgeted)}</Table.Td>
                <Table.Td ta="right">{formatAmount(row.drawn)}</Table.Td>
                <Table.Td>
                  {row.share === null ? (
                    '—'
                  ) : (
                    <Group gap={6} wrap="nowrap">
                      <Progress
                        value={Math.min(row.share * 100, 100)}
                        color={row.share > 1 ? 'red' : 'riso'}
                        w={80}
                        aria-label={t('home.budget.shareOf', { key: row.key })}
                      />
                      <Text size="sm">{formatPercent(row.share)}</Text>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollTable>
    </Card>
  );
}
