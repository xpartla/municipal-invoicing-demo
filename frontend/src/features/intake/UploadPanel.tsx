import { Badge, Button, Group, Loader, Paper, Stack, Table, Text } from '@mantine/core';
import { IconCamera, IconFileUpload, IconUpload } from '@tabler/icons-react';
import { useNavigate } from '@tanstack/react-router';
import { useRef, useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../../components/RouterLinks';
import { ScrollTable } from '../../components/ScrollTable';
import { useNotify } from '../../lib/notify';
import type { Invoice } from '../invoices/api';
import { READING, useUploadDocuments, useUploadedInvoices, type UploadOutcome } from './api';

const ACCEPT =
  '.pdf,.jpg,.jpeg,.png,.tif,.tiff,.xml,.isdoc,application/pdf,image/jpeg,image/png,image/tiff,application/xml,text/xml';

interface Item {
  key: number;
  name: string;
  outcome?: UploadOutcome;
}

type Status = 'uploading' | 'rejected' | 'reading' | 'ready' | 'failed' | 'done';

function statusOf(item: Item, invoice: Invoice | undefined): Status {
  if (!item.outcome) return 'uploading';
  if (item.outcome.status === 'rejected') return 'rejected';
  if (!invoice || READING.has(invoice.state)) return 'reading';
  if (invoice.state === 'extracted') return 'ready';
  if (invoice.state === 'extraction_failed') return 'failed';
  return 'done';
}

const COLOURS: Record<Status, string> = {
  uploading: 'gray',
  rejected: 'red',
  reading: 'blue',
  ready: 'green',
  failed: 'orange',
  done: 'gray',
};

/**
 * Nová faktúra's upload (plan §10.5): files dropped, chosen or photographed, several at
 * once, each with its progress: uploading, reading, ready to check, or failed with the
 * reason; a duplicate links the invoice the same file became. "Pokračovať na kontrolu" walks
 * through the ready ones in order.
 */
export function UploadPanel({ customerId }: { customerId: string }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const navigate = useNavigate();
  const upload = useUploadDocuments(customerId);
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const counter = useRef(0);
  const chooser = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);

  const invoiceIds = items.flatMap((i) =>
    i.outcome?.status === 'accepted' && i.outcome.invoice_id ? [i.outcome.invoice_id] : [],
  );
  const invoices = useUploadedInvoices(customerId, invoiceIds);
  const byId = new Map(invoices.flatMap((q) => (q.data ? [[q.data.id, q.data] as const] : [])));
  const statuses = items.map((item) =>
    statusOf(item, item.outcome?.invoice_id ? byId.get(item.outcome.invoice_id) : undefined),
  );
  const ready = items.flatMap((item, i) =>
    statuses[i] === 'ready' && item.outcome?.invoice_id ? [item.outcome.invoice_id] : [],
  );

  const send = async (files: File[]) => {
    if (files.length === 0) return;
    const added = files.map((file) => ({ key: counter.current++, name: file.name }));
    setItems((current) => [...added, ...current]);
    try {
      const result = await upload.mutateAsync(files);
      setItems((current) =>
        current.map((item) => {
          const at = added.findIndex((a) => a.key === item.key);
          return at < 0 ? item : { ...item, outcome: result.items[at] };
        }),
      );
    } catch (error) {
      setItems((current) => current.filter((item) => !added.some((a) => a.key === item.key)));
      notify.failure(error);
    }
  };

  const picked = (input: HTMLInputElement | null) => {
    const files = input?.files ? [...input.files] : [];
    if (input) input.value = '';
    void send(files);
  };

  const dropped = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    void send([...event.dataTransfer.files]);
  };

  const reason = (item: Item, status: Status, invoice: Invoice | undefined): string => {
    if (status === 'rejected') {
      const code = item.outcome?.reason ?? 'unknown';
      return t(`intake.rejected.${code}` as 'intake.rejected.unknown', {
        defaultValue: t('intake.rejected.unknown'),
      });
    }
    if (status === 'failed') {
      const code = invoice?.extraction_error ?? 'unknown';
      return t(`intake.failed.${code}` as 'intake.failed.unknown', {
        defaultValue: t('intake.failed.unknown'),
      });
    }
    return '';
  };

  return (
    <Stack gap="md">
      <Paper
        withBorder
        p="xl"
        radius="md"
        role="region"
        aria-label={t('intake.zone.label')}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={dropped}
        style={{
          borderStyle: 'dashed',
          borderWidth: 2,
          borderColor: dragging ? 'var(--mantine-primary-color-filled)' : undefined,
          background: dragging ? 'var(--mantine-primary-color-light)' : undefined,
        }}
      >
        <Stack align="center" gap="sm">
          <IconUpload size={36} aria-hidden />
          <Text ta="center" fw={500}>
            {t('intake.zone.drop')}
          </Text>
          <Text ta="center" size="sm" c="dimmed">
            {t('intake.zone.limits')}
          </Text>
          <Group justify="center">
            <Button
              leftSection={<IconFileUpload size={16} aria-hidden />}
              onClick={() => chooser.current?.click()}
              loading={upload.isPending}
            >
              {t('intake.zone.choose')}
            </Button>
            <Button
              variant="default"
              leftSection={<IconCamera size={16} aria-hidden />}
              onClick={() => camera.current?.click()}
            >
              {t('intake.zone.photo')}
            </Button>
          </Group>
          <input
            ref={chooser}
            type="file"
            multiple
            accept={ACCEPT}
            hidden
            data-testid="upload-files"
            aria-label={t('intake.zone.choose')}
            onChange={(event) => {
              picked(event.currentTarget);
            }}
          />
          <input
            ref={camera}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            aria-label={t('intake.zone.photo')}
            onChange={(event) => {
              picked(event.currentTarget);
            }}
          />
        </Stack>
      </Paper>

      {items.length > 0 && (
        <Stack gap="sm">
          <ScrollTable label={t('intake.list.label')} minWidth={560}>
            <Table aria-label={t('intake.list.label')} verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('intake.list.file')}</Table.Th>
                  <Table.Th>{t('intake.list.status')}</Table.Th>
                  <Table.Th>{t('intake.list.detail')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody aria-live="polite">
                {items.map((item, i) => {
                  const status = statuses[i] ?? 'uploading';
                  const invoiceId = item.outcome?.invoice_id ?? undefined;
                  const invoice = invoiceId ? byId.get(invoiceId) : undefined;
                  const duplicate = item.outcome?.duplicate_of ?? undefined;
                  return (
                    <Table.Tr key={item.key}>
                      <Table.Td>{item.name}</Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap">
                          {(status === 'uploading' || status === 'reading') && (
                            <Loader size="xs" aria-hidden />
                          )}
                          <Badge color={COLOURS[status]} variant="light">
                            {t(`intake.status.${status}`)}
                          </Badge>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="sm">
                          {reason(item, status, invoice) && (
                            <Text size="sm">{reason(item, status, invoice)}</Text>
                          )}
                          {duplicate && (
                            <AnchorLink
                              to="/c/$customerId/invoices/$invoiceId"
                              params={{ customerId, invoiceId: duplicate }}
                              size="sm"
                            >
                              {t('intake.list.duplicate')}
                            </AnchorLink>
                          )}
                          {invoiceId &&
                            (status === 'ready' || status === 'failed' || status === 'done') && (
                              <AnchorLink
                                to="/c/$customerId/invoices/$invoiceId"
                                params={{ customerId, invoiceId }}
                                search={{ tab: 'check' }}
                                size="sm"
                              >
                                {status === 'failed'
                                  ? t('intake.list.open')
                                  : t('intake.list.check')}
                              </AnchorLink>
                            )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollTable>
          <Group justify="flex-end">
            <Button
              disabled={ready.length === 0}
              onClick={() => {
                const [first, ...rest] = ready;
                if (!first) return;
                void navigate({
                  to: '/c/$customerId/invoices/$invoiceId',
                  params: { customerId, invoiceId: first },
                  search: { tab: 'check', queue: rest.length ? rest.join(',') : undefined },
                });
              }}
            >
              {t('intake.continue', { count: ready.length })}
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
