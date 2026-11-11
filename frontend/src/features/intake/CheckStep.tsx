import { Alert, Anchor, Button, Group, List, Loader, Stack, Text } from '@mantine/core';
import { IconDownload, IconRefresh } from '@tabler/icons-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotify } from '../../lib/notify';
import { useCheckInvoice, type Invoice } from '../invoices/api';
import { valuesOf } from '../invoices/fields';
import { FieldsForm, type CheckAids, type FieldPath } from '../invoices/FieldsForm';
import {
  fileUrl,
  noteUrl,
  READING,
  useEnterAfterFailure,
  useRetryExtraction,
  type Extraction,
} from './api';

/** Below this the extractor itself doubts a value (DOUBTFUL in the extractor). */
const DOUBTFUL = 0.6;

const FORM_FIELDS = new Set<string>([
  'supplier.name',
  'supplier.ico',
  'supplier.dic',
  'supplier.ic_dph',
  'supplier.iban',
  'supplier.address',
  'invoice.number',
  'invoice.variable_symbol',
  'invoice.issue_date',
  'invoice.delivery_date',
  'invoice.due_date',
  'totals.net',
  'totals.vat',
  'totals.gross',
]);

/** The fields a failed check of the extractor puts in doubt. */
const WARNED: Record<string, FieldPath[]> = {
  supplier_ico_check_digit: ['supplier.ico'],
  totals_do_not_add_up: ['totals.net', 'totals.vat', 'totals.gross'],
  dates_out_of_order: ['invoice.issue_date', 'invoice.delivery_date', 'invoice.due_date'],
  iban_check_digits: ['supplier.iban'],
  tax_ids_do_not_match: ['supplier.dic', 'supplier.ic_dph'],
  lines_do_not_add_up: ['totals.net', 'totals.gross'],
};

/**
 * Kontrola údajov (plan §8.5): the fields as they were read, the doubtful ones in amber with
 * why, the empty required ones in red, the handwritten date and number under the note's
 * enlarged crop with their suggestions; "Potvrdiť" saves them and codes the invoice. While
 * the file is read it says so; a file that could not be read says why, can be read again,
 * and its fields can be typed instead (manual entry, the invoice keeping its document).
 */
export function CheckStep({
  customerId,
  invoice,
  extraction,
  customer,
  onFieldFocus,
  onDone,
}: {
  customerId: string;
  invoice: Invoice;
  extraction: Extraction | undefined;
  customer: { name: string; ico: string };
  onFieldFocus: (path: FieldPath | null) => void;
  onDone: (invoice: Invoice) => Promise<void>;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const check = useCheckInvoice(customerId, invoice.id);
  const enter = useEnterAfterFailure(customerId, invoice.id);
  const retry = useRetryExtraction(customerId, invoice.id);
  const fresh = invoice.state === 'extracted';

  const aids: CheckAids = useMemo(() => {
    const doubtful: CheckAids['doubtful'] = {};
    if (fresh && extraction) {
      for (const [path, score] of Object.entries(extraction.confidence)) {
        if (score < DOUBTFUL && FORM_FIELDS.has(path)) {
          doubtful[path as FieldPath] = t('check.marks.low');
        }
      }
      for (const warning of extraction.warnings) {
        for (const path of WARNED[warning] ?? []) {
          doubtful[path] = t(`check.marks.${warning}` as 'check.marks.totals_do_not_add_up');
        }
      }
    }
    const note = extraction?.note;
    return {
      doubtful,
      handwrittenToConfirm: fresh,
      onFieldFocus,
      suggestions: note ? { date: note.date, number: note.number } : undefined,
      einvoice:
        extraction?.source === 'einvoice'
          ? { numberPreview: extraction.number_preview }
          : undefined,
      note:
        note && extraction.note_image && invoice.document_id ? (
          <figure style={{ margin: 0 }}>
            <img
              src={noteUrl(customerId, invoice.document_id)}
              alt={t('check.noteAlt')}
              style={{
                display: 'block',
                width: '100%',
                maxHeight: 220,
                objectFit: 'contain',
                background: 'white',
                border: '1px solid var(--mantine-color-default-border)',
                borderRadius: 4,
              }}
            />
            <Text component="figcaption" size="xs" c="dimmed" mt={4}>
              {note.found ? t('check.noteFound') : t('check.noteBand')}
            </Text>
          </figure>
        ) : undefined,
    };
  }, [fresh, extraction, onFieldFocus, customerId, invoice.document_id, t]);

  if (READING.has(invoice.state)) {
    return (
      <Group gap="sm" role="status">
        <Loader size="sm" aria-hidden />
        <Text>{t('check.reading')}</Text>
      </Group>
    );
  }

  const download = invoice.document_id ? (
    <Anchor href={fileUrl(customerId, invoice.document_id)} size="sm">
      <Group gap={4} component="span">
        <IconDownload size={14} aria-hidden />
        {t('check.download')}
      </Group>
    </Anchor>
  ) : null;

  if (invoice.state === 'extraction_failed') {
    const code = invoice.extraction_error ?? 'unknown';
    return (
      <Stack gap="md">
        <Alert color="orange">
          <Stack gap="xs">
            <Text size="sm" fw={600}>
              {t('check.failedTitle')}
            </Text>
            <Text size="sm">
              {t(`intake.failed.${code}` as 'intake.failed.unknown', {
                defaultValue: t('intake.failed.unknown'),
              })}
            </Text>
            <Text size="sm">{t('check.failedText')}</Text>
            <Group gap="md">
              <Button
                size="xs"
                variant="default"
                leftSection={<IconRefresh size={14} aria-hidden />}
                loading={retry.isPending}
                onClick={() => {
                  retry.mutate(undefined, {
                    onError: (error) => {
                      notify.failure(error);
                    },
                  });
                }}
              >
                {t('check.retry')}
              </Button>
              {download}
            </Group>
          </Stack>
        </Alert>
        <FieldsForm
          customer={customer}
          submitLabel={t('invoices.new.save')}
          onSubmit={async (fields) => {
            const done = await enter.mutateAsync(fields);
            notify.success(t('invoices.new.saved'));
            await onDone(done);
          }}
        />
      </Stack>
    );
  }

  const warnings = (extraction?.warnings ?? []).filter((w) => fresh && !(w in WARNED));
  return (
    <Stack gap="md">
      {warnings.length > 0 && (
        <Alert color="orange">
          <Text size="sm" fw={600} mb={4}>
            {t('check.warningsTitle')}
          </Text>
          <List size="sm">
            {warnings.map((w) => (
              <List.Item key={w}>
                {t(`check.warnings.${w}` as 'check.warnings.addressed_to_another_entity', {
                  defaultValue: w,
                })}
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
      {extraction && (
        <Group gap="md">
          <Text size="sm" c="dimmed">
            {extraction.source === 'einvoice'
              ? t('check.fromEinvoice')
              : extraction.source === 'text_layer'
                ? t('check.fromText')
                : t('check.fromOcr')}
          </Text>
          {download}
        </Group>
      )}
      <FieldsForm
        customer={customer}
        submitLabel={t('check.confirm')}
        initial={invoice.fields ? valuesOf(invoice.fields, { deliveryAsIssue: !fresh }) : undefined}
        aids={aids}
        onSubmit={async (fields) => {
          const done = await check.mutateAsync(fields);
          notify.success(t('check.done'));
          await onDone(done);
        }}
      />
    </Stack>
  );
}
