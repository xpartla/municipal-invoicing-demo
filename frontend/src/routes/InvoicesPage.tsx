import { Alert, Button, Checkbox, Group, Loader, Popover, Stack, Text, Title } from '@mantine/core';
import { IconColumns, IconDownload } from '@tabler/icons-react';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Pager } from '../components/Pager';
import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { useInvoices, type ExportScope, type InvoiceRow } from '../features/invoices/api';
import { BulkBar } from '../features/invoices/BulkBar';
import { COLUMNS, useColumnChoice } from '../features/invoices/columns';
import { ExportDialog } from '../features/invoices/ExportDialog';
import { InvoiceFilters } from '../features/invoices/InvoiceFilters';
import { InvoiceTable } from '../features/invoices/InvoiceTable';
import {
  activeFilters,
  apiQuery,
  DEFAULT_SORT,
  exportFilter,
  type InvoiceSearch,
} from '../features/invoices/search';

const SIZE = 50;

/** Drops the keys a change unset, so the URL keeps only what is chosen. */
function cleaned(search: InvoiceSearch): InvoiceSearch {
  return Object.fromEntries(Object.entries(search).filter(([, value]) => value !== undefined));
}

/**
 * Faktúry (plan §10.3): the customer's invoices with every filter, kept in the URL so a
 * filtered view is a link; sorting and paging on the server; the columns the user chooses;
 * bulk actions and the export for those who process invoices.
 */
export function InvoicesPage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const search = useSearch({ from: '/_app/c/$customerId/invoices' });
  const navigate = useNavigate();
  const { data: me } = useMe();
  const canProcess = me ? inCustomer(me, customerId, 'invoices.process') : false;
  const { chosen, choose } = useColumnChoice();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [exporting, setExporting] = useState<ExportScope | null>(null);
  const invoices = useInvoices(customerId, apiQuery(search, me?.user.id, SIZE));
  const rows = invoices.data?.items ?? [];
  const total = invoices.data?.total ?? 0;

  const go = (next: InvoiceSearch, replace: boolean) => {
    setSelected(new Set());
    void navigate({
      to: '/c/$customerId/invoices',
      params: { customerId },
      search: cleaned(next),
      replace,
    });
  };
  const change = (change: Partial<InvoiceSearch>) => {
    go({ ...search, ...change, page: undefined }, true);
  };
  const names = (id: string) => {
    const row = rows.find((r) => r.id === id);
    return row?.document_number ?? row?.invoice_number ?? row?.supplier_name ?? id;
  };
  const renderNumber = (row: InvoiceRow) => (
    <Text size="sm" fw={600} ff="monospace">
      {row.document_number}
    </Text>
  );

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <Title order={1}>{t('invoices.title')}</Title>
        <Group gap="xs">
          <Popover position="bottom-end" shadow="md" withinPortal>
            <Popover.Target>
              <Button variant="default" leftSection={<IconColumns size={16} aria-hidden />}>
                {t('invoices.columnChooser')}
              </Button>
            </Popover.Target>
            <Popover.Dropdown>
              <Checkbox.Group
                label={t('invoices.columnChooser')}
                value={chosen}
                onChange={(keys) => {
                  choose(keys);
                }}
              >
                <Stack gap={6} mt="xs">
                  {COLUMNS.map((c) => (
                    <Checkbox key={c.key} value={c.key} label={t(`invoices.columns.${c.key}`)} />
                  ))}
                </Stack>
              </Checkbox.Group>
            </Popover.Dropdown>
          </Popover>
          {canProcess && (
            <Button
              leftSection={<IconDownload size={16} aria-hidden />}
              disabled={total === 0}
              onClick={() => {
                setExporting({ filter: exportFilter(search, me?.user.id), sort: search.sort });
              }}
            >
              {t('invoices.export.button')}
            </Button>
          )}
        </Group>
      </Group>

      <InvoiceFilters customerId={customerId} search={search} onChange={change} />

      {canProcess && (
        <BulkBar
          customerId={customerId}
          selected={[...selected]}
          names={names}
          onClear={() => {
            setSelected(new Set());
          }}
          onExport={setExporting}
        />
      )}

      <Group justify="space-between">
        <Text size="sm" c="dimmed" aria-live="polite">
          {t('invoices.count', { count: total })}
        </Text>
        {invoices.isFetching && <Loader size="xs" aria-label={t('common.loading')} />}
      </Group>

      {invoices.isError && <Alert color="red">{t('common.error')}</Alert>}
      {invoices.isSuccess && rows.length === 0 ? (
        <Text c="dimmed">
          {activeFilters(search) > 0 ? t('invoices.emptyFiltered') : t('invoices.empty')}
        </Text>
      ) : (
        rows.length > 0 && (
          <InvoiceTable
            rows={rows}
            columns={chosen}
            sort={search.sort ?? DEFAULT_SORT}
            onSort={(sort) => {
              go({ ...search, sort, page: undefined }, false);
            }}
            selected={selected}
            selectable={canProcess}
            onSelect={(ids, on) => {
              setSelected((current) => {
                const next = new Set(current);
                for (const id of ids) {
                  if (on) next.add(id);
                  else next.delete(id);
                }
                return next;
              });
            }}
            renderNumber={renderNumber}
          />
        )
      )}
      <Pager
        page={search.page ?? 1}
        pages={Math.ceil(total / SIZE)}
        onPage={(page) => {
          go({ ...search, page: page > 1 ? page : undefined }, false);
        }}
      />
      <ExportDialog
        customerId={customerId}
        scope={exporting}
        onClose={() => {
          setExporting(null);
        }}
      />
    </Stack>
  );
}
