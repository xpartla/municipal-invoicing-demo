import {
  Alert,
  Badge,
  Box,
  Code,
  Group,
  List,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { formatAmount, formatDate } from '../../lib/format';
import type { FieldPath } from '../invoices/FieldsForm';
import { useEInvoice, type EInvoice } from './api';
import { DocumentViewer } from './DocumentViewer';

const NBSP = ' ';

/** A quantity, a rate or a unit price as written: `0,1389`, `1${NBSP}240`. */
function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '';
  const [whole = '0', fraction] = String(Math.abs(value)).split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return `${value < 0 ? '-' : ''}${grouped}${fraction ? `,${fraction}` : ''}`;
}

/**
 * The viewer of an e-invoice (plan §8.4, §8.5, §10.4): the invoice rendered from its XML, the
 * PDF's pages when it came inside one, and the raw XML, shown as text (never as markup). The
 * field focused in the check step is marked in the rendered view.
 */
export function EInvoiceViewer({
  customerId,
  documentId,
  pages,
  focused,
}: {
  customerId: string;
  documentId: string;
  pages: number;
  focused: FieldPath | null;
}) {
  const { t } = useTranslation();
  const query = useEInvoice(customerId, documentId);
  const [tab, setTab] = useState<string | null>('invoice');
  const data = query.data;

  return (
    <Paper withBorder radius="md" p="xs" role="region" aria-label={t('einvoice.label')}>
      {query.isPending ? (
        <Group gap="sm" role="status">
          <Loader size="sm" aria-hidden />
          <Text size="sm">{t('einvoice.loading')}</Text>
        </Group>
      ) : !data ? (
        <Text size="sm" c="dimmed">
          {t('einvoice.unavailable')}
        </Text>
      ) : (
        <Tabs value={data.document ? tab : tab === 'invoice' ? 'xml' : tab} onChange={setTab}>
          <Tabs.List>
            {data.document && <Tabs.Tab value="invoice">{t('einvoice.tabs.invoice')}</Tabs.Tab>}
            {pages > 0 && <Tabs.Tab value="pdf">{t('einvoice.tabs.pdf')}</Tabs.Tab>}
            <Tabs.Tab value="xml">{t('einvoice.tabs.xml')}</Tabs.Tab>
          </Tabs.List>
          {data.document && (
            <Tabs.Panel value="invoice" pt="sm">
              <Rendered einvoice={data} focused={focused} />
            </Tabs.Panel>
          )}
          {pages > 0 && (
            <Tabs.Panel value="pdf" pt="sm">
              <DocumentViewer
                customerId={customerId}
                documentId={documentId}
                pages={pages}
                highlight={null}
              />
            </Tabs.Panel>
          )}
          <Tabs.Panel value="xml" pt="sm">
            <Stack gap="xs">
              {data.failure && (
                <Alert color="orange">
                  {t(`intake.failed.${data.failure}` as 'intake.failed.unknown', {
                    defaultValue: t('intake.failed.unknown'),
                  })}
                </Alert>
              )}
              {data.truncated && (
                <Text size="xs" c="dimmed">
                  {t('einvoice.truncated')}
                </Text>
              )}
              {/* The scrolling box itself takes the focus, so it scrolls from the keyboard. */}
              <Box
                tabIndex={0}
                role="region"
                aria-label={t('einvoice.raw')}
                style={{ overflow: 'auto', maxHeight: 'min(75vh, 1100px)' }}
              >
                <Code block style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {data.xml}
                </Code>
              </Box>
            </Stack>
          </Tabs.Panel>
        </Tabs>
      )}
    </Paper>
  );
}

function Rendered({ einvoice, focused }: { einvoice: EInvoice; focused: FieldPath | null }) {
  const { t } = useTranslation();
  const document = einvoice.document;
  if (!document) return null;
  const { supplier, customer, invoice, totals } = document;
  const lines = document.lines ?? [];
  const notes = document.free_text ?? [];
  const credit = invoice.document_type === 'credit_note';

  /** A value of the invoice, marked while its field has the focus in the check step. */
  const value = (path: FieldPath, shown: ReactNode) => {
    const on = focused === path;
    return (
      <Box
        component="span"
        data-field={path}
        data-focused={on || undefined}
        style={
          on
            ? {
                // An outline only: the text keeps its colours, so its contrast, in both themes.
                outline: '2px solid var(--mantine-color-orange-6)',
                outlineOffset: 2,
                borderRadius: 2,
              }
            : undefined
        }
      >
        {shown === '' || shown === null || shown === undefined ? '—' : shown}
      </Box>
    );
  };
  const row = (label: string, path: FieldPath, shown: ReactNode) => (
    <Group gap={6} wrap="nowrap" align="baseline">
      <Text size="xs" c="dimmed" miw={110}>
        {label}
      </Text>
      <Text size="sm">{value(path, shown)}</Text>
    </Group>
  );
  const format =
    einvoice.family === 'isdoc'
      ? t('einvoice.formats.isdoc', { version: einvoice.version })
      : t('einvoice.formats.ubl', { version: einvoice.version });

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-start" gap="xs">
        <Stack gap={0}>
          <Title order={2} size="h4">
            {credit ? t('einvoice.creditNote') : t('einvoice.invoice')}{' '}
            {value('invoice.number', invoice.number)}
          </Title>
          {einvoice.attachment && (
            <Text size="xs" c="dimmed">
              {t('einvoice.attachment', { name: einvoice.attachment })}
            </Text>
          )}
        </Stack>
        <Badge variant="light">{format}</Badge>
      </Group>

      {einvoice.schema_errors.length > 0 && (
        <Alert color="orange" title={t('einvoice.schemaTitle', { format })}>
          <List size="xs">
            {einvoice.schema_errors.map((error) => (
              <List.Item key={error}>
                <Text size="xs" style={{ wordBreak: 'break-word' }}>
                  {error}
                </Text>
              </List.Item>
            ))}
          </List>
        </Alert>
      )}

      <SimpleGrid type="container" cols={{ base: 1, '480px': 2 }} spacing="sm">
        <Stack gap={4}>
          <Text size="sm" fw={600}>
            {t('einvoice.supplier')}
          </Text>
          <Text size="sm">{value('supplier.name', supplier.name)}</Text>
          <Text size="sm">{value('supplier.address', supplier.address)}</Text>
          {row(t('einvoice.ico'), 'supplier.ico', supplier.ico)}
          {row(t('einvoice.dic'), 'supplier.dic', supplier.dic)}
          {row(t('einvoice.icDph'), 'supplier.ic_dph', supplier.ic_dph)}
          {supplier.vat_payer === false && (
            <Text size="xs" c="dimmed">
              {t('einvoice.notVatPayer')}
            </Text>
          )}
        </Stack>
        <Stack gap={4}>
          <Text size="sm" fw={600}>
            {t('einvoice.customer')}
          </Text>
          <Text size="sm">{customer.name ?? '—'}</Text>
          {einvoice.customer_address && <Text size="sm">{einvoice.customer_address}</Text>}
          <Group gap={6} wrap="nowrap" align="baseline">
            <Text size="xs" c="dimmed" miw={110}>
              {t('einvoice.ico')}
            </Text>
            <Text size="sm">{customer.ico ?? '—'}</Text>
          </Group>
        </Stack>
      </SimpleGrid>

      <SimpleGrid type="container" cols={{ base: 1, '480px': 2 }} spacing="sm">
        <Stack gap={4}>
          {row(t('einvoice.issueDate'), 'invoice.issue_date', formatDate(invoice.issue_date))}
          {row(
            t('einvoice.deliveryDate'),
            'invoice.delivery_date',
            formatDate(invoice.delivery_date),
          )}
          {row(t('einvoice.dueDate'), 'invoice.due_date', formatDate(invoice.due_date))}
        </Stack>
        <Stack gap={4}>
          {row(t('einvoice.iban'), 'supplier.iban', supplier.iban)}
          {row(t('einvoice.vs'), 'invoice.variable_symbol', invoice.variable_symbol)}
        </Stack>
      </SimpleGrid>

      {lines.length > 0 && (
        <ScrollTable label={t('einvoice.lines')} minWidth={620}>
          <Table striped withTableBorder fz="xs" verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('einvoice.columns.description')}</Table.Th>
                <Table.Th ta="right">{t('einvoice.columns.quantity')}</Table.Th>
                <Table.Th>{t('einvoice.columns.unit')}</Table.Th>
                <Table.Th ta="right">{t('einvoice.columns.unitPrice')}</Table.Th>
                <Table.Th ta="right">{t('einvoice.columns.net')}</Table.Th>
                <Table.Th ta="right">{t('einvoice.columns.rate')}</Table.Th>
                <Table.Th ta="right">{t('einvoice.columns.vat')}</Table.Th>
                <Table.Th ta="right">{t('einvoice.columns.gross')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {lines.map((line, i) => (
                <Table.Tr key={i}>
                  <Table.Td>{line.description}</Table.Td>
                  <Table.Td ta="right">{formatNumber(line.quantity)}</Table.Td>
                  <Table.Td>{line.unit ?? ''}</Table.Td>
                  <Table.Td ta="right">{formatNumber(line.unit_price)}</Table.Td>
                  <Table.Td ta="right">{formatAmount(line.net, { currency: false })}</Table.Td>
                  <Table.Td ta="right">
                    {line.vat_rate === null || line.vat_rate === undefined
                      ? ''
                      : `${formatNumber(line.vat_rate)}${NBSP}%`}
                  </Table.Td>
                  <Table.Td ta="right">{formatAmount(line.vat, { currency: false })}</Table.Td>
                  <Table.Td ta="right">{formatAmount(line.gross, { currency: false })}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}

      <SimpleGrid type="container" cols={{ base: 1, '480px': 2 }} spacing="sm">
        <Stack gap={4}>
          {einvoice.taxes.length > 0 && (
            <>
              <Text size="sm" fw={600}>
                {t('einvoice.taxes')}
              </Text>
              {einvoice.taxes.map((tax, i) => (
                <Text size="xs" key={i}>
                  {t(`einvoice.categories.${tax.category}` as 'einvoice.categories.S', {
                    defaultValue: tax.category,
                  })}
                  {tax.rate ? ` ${formatNumber(tax.rate)}${NBSP}%` : ''}:{' '}
                  {formatAmount(tax.taxable)} + {formatAmount(tax.tax)}
                </Text>
              ))}
            </>
          )}
        </Stack>
        <Stack gap={4}>
          {row(t('einvoice.net'), 'totals.net', formatAmount(totals.net))}
          {row(t('einvoice.vat'), 'totals.vat', formatAmount(totals.vat))}
          {row(t('einvoice.gross'), 'totals.gross', formatAmount(totals.gross))}
          <Group gap={6} wrap="nowrap" align="baseline">
            <Text size="xs" c="dimmed" miw={110}>
              {t('einvoice.payable')}
            </Text>
            <Text size="sm" fw={600}>
              {formatAmount(einvoice.payable) || '—'}
            </Text>
          </Group>
        </Stack>
      </SimpleGrid>

      {notes.length > 0 && (
        <Stack gap={2}>
          <Text size="sm" fw={600}>
            {t('einvoice.notes')}
          </Text>
          {notes.map((line, i) => (
            <Text size="xs" key={i}>
              {line}
            </Text>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
