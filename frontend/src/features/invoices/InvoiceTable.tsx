import { Badge, Checkbox, Table, Text, UnstyledButton } from '@mantine/core';
import type { TFunction } from 'i18next';
import { IconArrowDown, IconArrowUp, IconArrowsSort } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { formatAmount, formatDate, formatDateTime } from '../../lib/format';
import type { InvoiceRow } from './api';
import { COLUMNS, type ColumnKey } from './columns';
import { nextSort, type SortKey } from './search';

const STATE_COLORS: Record<string, string> = {
  extraction_failed: 'red',
  needs_review: 'orange',
  ready: 'blue',
  booked: 'teal',
  exported: 'grape',
  paid: 'green',
  discarded: 'gray',
  duplicate: 'gray',
};

/** One cell's content. `number` renders through `renderNumber` (a link to the detail). */
function cell(
  row: InvoiceRow,
  key: ColumnKey,
  t: TFunction,
  renderNumber: (row: InvoiceRow) => React.ReactNode,
): React.ReactNode {
  switch (key) {
    case 'state':
      return (
        <Badge color={STATE_COLORS[row.state] ?? 'gray'}>{t(`invoices.states.${row.state}`)}</Badge>
      );
    case 'number':
      return renderNumber(row);
    case 'booking_date':
      return formatDate(row.booking_date);
    case 'supplier':
      return row.supplier_name;
    case 'ico':
      return row.supplier_ico;
    case 'invoice_number':
      return row.invoice_number;
    case 'vs':
      return row.variable_symbol;
    case 'issue_date':
      return formatDate(row.issue_date);
    case 'supply_date':
      return formatDate(row.supply_date);
    case 'due_date':
      return formatDate(row.due_date);
    case 'gross':
      return formatAmount(row.gross);
    case 'budget':
      return row.budget_keys.map((key, i) => (
        <Text key={i} size="sm" ff="monospace">
          {key}
        </Text>
      ));
    case 'md_dal':
      return row.md.map((md, i) => (
        <Text key={i} size="sm" ff="monospace">
          {md} / {row.dal[i] ?? row.dal[0]}
        </Text>
      ));
    case 'uploaded':
      return formatDateTime(row.uploaded_at);
    case 'exported':
      return formatDateTime(row.exported_at);
    case 'paid':
      return formatDate(row.paid_on);
    case 'source':
      return t(`invoices.channels.${row.channel}`);
  }
}

/** The invoice table (plan §10.3): the chosen columns, sorting by a click on a column's
 * header, and a check box per row for the bulk actions. */
export function InvoiceTable({
  rows,
  columns,
  sort,
  onSort,
  selected,
  onSelect,
  selectable,
  renderNumber,
}: {
  rows: InvoiceRow[];
  columns: ColumnKey[];
  sort: string;
  onSort: (sort: string) => void;
  selected: Set<string>;
  onSelect: (ids: string[], on: boolean) => void;
  selectable: boolean;
  renderNumber: (row: InvoiceRow) => React.ReactNode;
}) {
  const { t } = useTranslation();
  const shown = COLUMNS.filter((c) => columns.includes(c.key));
  const onPage = rows.map((r) => r.id);
  const all = onPage.length > 0 && onPage.every((id) => selected.has(id));
  const some = onPage.some((id) => selected.has(id));
  const by = sort.replace(/^-/, '');
  const descending = sort.startsWith('-');

  const header = (key: ColumnKey, sortKey: SortKey | null) => {
    const label = t(`invoices.columns.${key}`);
    if (!sortKey)
      return (
        <Table.Th scope="col" key={key}>
          {label}
        </Table.Th>
      );
    const active = by === sortKey;
    const Icon = !active ? IconArrowsSort : descending ? IconArrowDown : IconArrowUp;
    return (
      <Table.Th
        scope="col"
        key={key}
        aria-sort={active ? (descending ? 'descending' : 'ascending') : 'none'}
      >
        <UnstyledButton
          aria-label={t('invoices.sortBy', { column: label })}
          onClick={() => {
            onSort(nextSort(sort, sortKey));
          }}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 700 }}
        >
          {label}
          <Icon size={14} aria-hidden />
        </UnstyledButton>
      </Table.Th>
    );
  };

  return (
    <ScrollTable label={t('invoices.tableLabel')} minWidth={160 + shown.length * 110}>
      <Table striped highlightOnHover verticalSpacing="xs">
        <Table.Thead>
          <Table.Tr>
            {selectable && (
              <Table.Th scope="col" w={40}>
                <Checkbox
                  aria-label={t('invoices.selectPage')}
                  checked={all}
                  indeterminate={some && !all}
                  onChange={() => {
                    onSelect(onPage, !all);
                  }}
                />
              </Table.Th>
            )}
            {shown.map((c) => header(c.key, c.sort))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.id}>
              {selectable && (
                <Table.Td>
                  <Checkbox
                    aria-label={t('invoices.select', {
                      name:
                        row.document_number ?? row.invoice_number ?? row.supplier_name ?? row.id,
                    })}
                    checked={selected.has(row.id)}
                    onChange={(event) => {
                      onSelect([row.id], event.currentTarget.checked);
                    }}
                  />
                </Table.Td>
              )}
              {shown.map((c) => (
                <Table.Td
                  key={c.key}
                  style={
                    c.key === 'gross' ? { textAlign: 'right', whiteSpace: 'nowrap' } : undefined
                  }
                >
                  {cell(row, c.key, t, renderNumber)}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollTable>
  );
}
