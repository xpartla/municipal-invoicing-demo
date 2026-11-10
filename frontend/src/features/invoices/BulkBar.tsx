import { Button, Group, List, Paper, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { useNotify } from '../../lib/notify';
import { useBulk, type BulkAction, type BulkOutcome, type ExportScope } from './api';

function today(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${String(now.getFullYear())}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * The bulk actions on the selected invoices (plan §10.3): mark paid with a date, re-code,
 * discard, export. Each invoice succeeds or fails on its own; the failures are listed. It stays
 * mounted without a selection, so the list of failures outlives the selection it clears.
 */
export function BulkBar({
  customerId,
  selected,
  names,
  onClear,
  onExport,
}: {
  customerId: string;
  selected: string[];
  /** What to call an invoice in the list of failures (its document or invoice number). */
  names: (id: string) => string;
  onClear: () => void;
  onExport: (scope: ExportScope) => void;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const bulk = useBulk(customerId);
  const [dialog, setDialog] = useState<'pay' | 'discard' | null>(null);
  const [paidOn, setPaidOn] = useState(today);
  const [reason, setReason] = useState('');
  const [failures, setFailures] = useState<BulkOutcome['results']>([]);

  const run = async (action: BulkAction) => {
    try {
      const outcome = await bulk.mutateAsync(action);
      setDialog(null);
      notify.success(t('invoices.bulk.result', { done: outcome.done, failed: outcome.failed }));
      setFailures(outcome.results.filter((r) => !r.ok));
      onClear();
    } catch (error) {
      notify.failure(error);
    }
  };

  return (
    <>
      {selected.length > 0 && (
        <Paper withBorder p="xs" radius="md">
          <Group justify="space-between" gap="xs">
            <Text fw={600} aria-live="polite">
              {t('invoices.bulk.selected', { count: selected.length })}
            </Text>
            <Group gap="xs">
              <Button
                size="xs"
                onClick={() => {
                  onExport({ invoiceIds: selected });
                }}
              >
                {t('invoices.bulk.export')}
              </Button>
              <Button
                size="xs"
                variant="default"
                onClick={() => {
                  setPaidOn(today());
                  setDialog('pay');
                }}
              >
                {t('invoices.bulk.pay')}
              </Button>
              <Button
                size="xs"
                variant="default"
                loading={bulk.isPending && dialog === null}
                onClick={() => void run({ action: 'recode', invoiceIds: selected })}
              >
                {t('invoices.bulk.recode')}
              </Button>
              <Button
                size="xs"
                variant="default"
                color="red"
                onClick={() => {
                  setReason('');
                  setDialog('discard');
                }}
              >
                {t('invoices.bulk.discard')}
              </Button>
              <Button size="xs" variant="subtle" onClick={onClear}>
                {t('invoices.bulk.clear')}
              </Button>
            </Group>
          </Group>
        </Paper>
      )}

      <Dialog
        opened={dialog === 'pay'}
        onClose={() => {
          setDialog(null);
        }}
        title={t('invoices.bulk.pay')}
      >
        <Stack gap="md">
          <Text size="sm">{t('invoices.bulk.payText')}</Text>
          <TextInput
            type="date"
            label={t('invoices.bulk.paidOn')}
            value={paidOn}
            required
            onChange={(event) => {
              setPaidOn(event.currentTarget.value);
            }}
          />
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setDialog(null);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!paidOn}
              loading={bulk.isPending}
              onClick={() => void run({ action: 'pay', invoiceIds: selected, paidOn })}
            >
              {t('invoices.bulk.pay')}
            </Button>
          </Group>
        </Stack>
      </Dialog>

      <Dialog
        opened={dialog === 'discard'}
        onClose={() => {
          setDialog(null);
        }}
        title={t('invoices.bulk.discard')}
      >
        <Stack gap="md">
          <Text size="sm">{t('invoices.bulk.discardText')}</Text>
          <TextInput
            label={t('invoices.bulk.reason')}
            value={reason}
            maxLength={500}
            onChange={(event) => {
              setReason(event.currentTarget.value);
            }}
          />
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setDialog(null);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              color="red"
              loading={bulk.isPending}
              onClick={() =>
                void run({
                  action: 'discard',
                  invoiceIds: selected,
                  reason: reason.trim() || undefined,
                })
              }
            >
              {t('invoices.bulk.discard')}
            </Button>
          </Group>
        </Stack>
      </Dialog>

      <Dialog
        opened={failures.length > 0}
        onClose={() => {
          setFailures([]);
        }}
        title={t('invoices.bulk.failedTitle')}
      >
        <List spacing="xs">
          {failures.map((f) => (
            <List.Item key={f.invoice_id}>
              <Text span fw={600}>
                {names(f.invoice_id)}
              </Text>
              {': '}
              {t(`invoices.bulk.codes.${(f.code ?? 'error') as 'error'}`, {
                defaultValue: t('invoices.bulk.codes.error'),
              })}
            </List.Item>
          ))}
        </List>
      </Dialog>
    </>
  );
}
