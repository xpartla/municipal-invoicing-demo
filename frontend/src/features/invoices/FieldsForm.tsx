import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Fieldset,
  Group,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { IconCode, IconPlus, IconTrash } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { get, useFieldArray, useForm, useWatch, type Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { Dialog } from '../../components/Dialog';
import { applyFieldErrors } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import type { InvoiceDocument } from './api';
import { parseAmount } from './coding';
import { documentOf, emptyValues, valuesOf, type FieldValues } from './fields';

/**
 * The invoice's fields as a form (plan §8.5), in the check step's order: the handwritten
 * booking date and number, the supplier, the invoice header, the totals, the lines. Manual
 * entry uses it now; the check step of P2-M5 reuses it next to the document. "Vložiť JSON"
 * fills it from an InvoiceDocument (the demo's pasted invoice).
 */

const FIELDS: readonly Path<FieldValues>[] = [
  'handwritten.date',
  'handwritten.number',
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
];

export function FieldsForm({
  customer,
  submitLabel,
  initial,
  onSubmit,
}: {
  customer: { name: string; ico: string };
  submitLabel: string;
  initial?: FieldValues;
  onSubmit: (document: InvoiceDocument) => Promise<void>;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const errorText = useErrorText();
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState('');
  const [pasteError, setPasteError] = useState<string | null>(null);
  const schema = useMemo(() => {
    const required = z.string().trim().min(1, t('errors.required'));
    const money = z
      .string()
      .refine((v) => v.trim() === '' || parseAmount(v) !== null, t('fieldsForm.amountShape'));
    const free = z.string();
    return z.object({
      handwritten: z.object({ date: free, number: free }),
      supplier: z.object({
        name: required,
        ico: free,
        dic: free,
        ic_dph: free,
        iban: free,
        address: free,
      }),
      invoice: z.object({
        number: free,
        variable_symbol: free,
        issue_date: required,
        delivery_date: free,
        due_date: free,
        document_type: z.enum(['invoice', 'credit_note']),
      }),
      totals: z.object({ net: money, vat: money, gross: required.and(money) }),
      lines: z.array(z.object({ description: free, gross: money })),
      notes: free,
    });
  }, [t]);
  const form = useForm<FieldValues>({
    resolver: zodResolver(schema),
    defaultValues: initial ?? emptyValues(),
  });
  const lines = useFieldArray({ control: form.control, name: 'lines' });
  const { errors, isSubmitting } = form.formState;
  const errorAt = (name: Path<FieldValues>): string | undefined => {
    const found: unknown = get(errors, name);
    if (typeof found !== 'object' || found === null || !('message' in found)) return undefined;
    return typeof found.message === 'string' ? found.message : undefined;
  };
  const documentType = useWatch({ control: form.control, name: 'invoice.document_type' });

  const submit = form.handleSubmit(async (values) => {
    try {
      await onSubmit(documentOf(values, customer));
    } catch (error) {
      if (!applyFieldErrors(error, form.setError, FIELDS, errorText)) notify.failure(error);
    }
  });

  const input = (name: Path<FieldValues>, label: string, props: object = {}) => (
    <TextInput label={label} {...form.register(name)} error={errorAt(name)} {...props} />
  );

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Stack gap="md">
        <Group justify="flex-end">
          <Button
            variant="default"
            size="xs"
            leftSection={<IconCode size={14} aria-hidden />}
            onClick={() => {
              setPasted('');
              setPasteError(null);
              setPasting(true);
            }}
          >
            {t('fieldsForm.paste')}
          </Button>
        </Group>
        <Fieldset legend={t('fieldsForm.handwritten')}>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {input('handwritten.date', t('fieldsForm.handwrittenDate'), { type: 'date' })}
            {input('handwritten.number', t('fieldsForm.handwrittenNumber'), {
              description: t('fieldsForm.handwrittenNumberHint'),
              inputMode: 'numeric',
            })}
          </SimpleGrid>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.supplier')}>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
            {input('supplier.name', t('fieldsForm.supplierName'), { withAsterisk: true })}
            {input('supplier.ico', t('fieldsForm.ico'), { inputMode: 'numeric' })}
            {input('supplier.dic', t('fieldsForm.dic'))}
            {input('supplier.ic_dph', t('fieldsForm.icDph'))}
            {input('supplier.iban', t('fieldsForm.iban'))}
            {input('supplier.address', t('fieldsForm.address'))}
          </SimpleGrid>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.header')}>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
            {input('invoice.number', t('fieldsForm.number'))}
            {input('invoice.variable_symbol', t('fieldsForm.vs'), { inputMode: 'numeric' })}
            <Stack gap={4}>
              <Text size="sm" fw={500} id="fields-document-type">
                {t('fieldsForm.documentType')}
              </Text>
              <SegmentedControl
                aria-labelledby="fields-document-type"
                value={documentType}
                onChange={(value) => {
                  form.setValue(
                    'invoice.document_type',
                    value === 'credit_note' ? 'credit_note' : 'invoice',
                  );
                }}
                data={[
                  { value: 'invoice', label: t('fieldsForm.invoice') },
                  { value: 'credit_note', label: t('fieldsForm.creditNote') },
                ]}
              />
            </Stack>
            {input('invoice.issue_date', t('fieldsForm.issueDate'), {
              type: 'date',
              withAsterisk: true,
            })}
            {input('invoice.delivery_date', t('fieldsForm.deliveryDate'), {
              type: 'date',
              description: t('fieldsForm.deliveryHint'),
            })}
            {input('invoice.due_date', t('fieldsForm.dueDate'), { type: 'date' })}
          </SimpleGrid>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.totals')}>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
            {input('totals.net', t('fieldsForm.net'), { inputMode: 'decimal' })}
            {input('totals.vat', t('fieldsForm.vat'), { inputMode: 'decimal' })}
            {input('totals.gross', t('fieldsForm.gross'), {
              inputMode: 'decimal',
              withAsterisk: true,
            })}
          </SimpleGrid>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.lines')}>
          <Stack gap="xs">
            {lines.fields.map((field, i) => (
              <Group key={field.id} gap="xs" align="flex-end" wrap="nowrap">
                <TextInput
                  style={{ flex: 1 }}
                  label={t('fieldsForm.lineDescription', { n: i + 1 })}
                  {...form.register(`lines.${i}.description`)}
                />
                <TextInput
                  w={130}
                  inputMode="decimal"
                  label={t('fieldsForm.lineGross', { n: i + 1 })}
                  {...form.register(`lines.${i}.gross`)}
                  error={errors.lines?.[i]?.gross?.message}
                />
                <Button
                  variant="subtle"
                  color="red"
                  aria-label={t('fieldsForm.removeLine', { n: i + 1 })}
                  onClick={() => {
                    lines.remove(i);
                  }}
                >
                  <IconTrash size={16} aria-hidden />
                </Button>
              </Group>
            ))}
            <Group>
              <Button
                size="xs"
                variant="default"
                leftSection={<IconPlus size={14} aria-hidden />}
                onClick={() => {
                  lines.append({ description: '', gross: '' });
                }}
              >
                {t('fieldsForm.addLine')}
              </Button>
            </Group>
          </Stack>
        </Fieldset>
        <Textarea
          label={t('fieldsForm.notes')}
          description={t('fieldsForm.notesHint')}
          autosize
          minRows={2}
          {...form.register('notes')}
        />
        {errors.root && <Alert color="red">{errors.root.message}</Alert>}
        <Group justify="flex-end">
          <Button type="submit" loading={isSubmitting}>
            {submitLabel}
          </Button>
        </Group>
      </Stack>

      <Dialog
        opened={pasting}
        onClose={() => {
          setPasting(false);
        }}
        title={t('fieldsForm.pasteTitle')}
        size="lg"
      >
        <Stack gap="md">
          <Text size="sm">{t('fieldsForm.pasteText')}</Text>
          <Textarea
            label={t('fieldsForm.pasteLabel')}
            autosize
            minRows={8}
            maxRows={18}
            ff="monospace"
            value={pasted}
            error={pasteError}
            onChange={(event) => {
              setPasted(event.currentTarget.value);
            }}
          />
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setPasting(false);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => {
                try {
                  const parsed: unknown = JSON.parse(pasted);
                  if (
                    typeof parsed !== 'object' ||
                    parsed === null ||
                    !('supplier' in parsed) ||
                    !('invoice' in parsed)
                  ) {
                    throw new Error('not an invoice');
                  }
                  form.reset(valuesOf(parsed));
                  setPasting(false);
                } catch {
                  setPasteError(t('fieldsForm.pasteInvalid'));
                }
              }}
            >
              {t('fieldsForm.pasteFill')}
            </Button>
          </Group>
        </Stack>
      </Dialog>
    </form>
  );
}
