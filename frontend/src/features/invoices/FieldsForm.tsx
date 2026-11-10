import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Checkbox,
  Fieldset,
  Group,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  type TextInputProps,
} from '@mantine/core';
import { IconCode, IconPlus, IconTrash } from '@tabler/icons-react';
import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { get, useFieldArray, useForm, useWatch, type Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { Dialog } from '../../components/Dialog';
import { applyFieldErrors } from '../../lib/apiError';
import { formatDate } from '../../lib/format';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import type { InvoiceDocument } from './api';
import { parseAmount } from './coding';
import { documentOf, emptyValues, valuesOf, type FieldValues } from './fields';

/**
 * The invoice's fields as a form (plan §8.5), in the check step's order: the handwritten
 * booking date and number, the supplier, the invoice header, the totals, the lines. Manual
 * entry uses it as it is, with "Vložiť JSON" to fill it from an InvoiceDocument (the demo's
 * pasted invoice). The check step adds its aids: the note's enlarged crop above the
 * handwritten fields and the suggestions under them, the doubtful fields in amber and the
 * empty required ones in red, and the keyboard path: Enter confirms a field (an empty
 * handwritten one takes its first suggestion) and goes on to the next doubtful one, Tab
 * skips to the next doubtful one.
 */

export type FieldPath = Path<FieldValues>;

const FIELDS: readonly FieldPath[] = [
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

const REQUIRED: readonly FieldPath[] = ['supplier.name', 'invoice.issue_date', 'totals.gross'];
const HANDWRITTEN = { 'handwritten.date': 'date', 'handwritten.number': 'number' } as const;

export interface Suggestion {
  value: string;
  source: 'ocr' | 'counter';
  plausible: boolean;
  reasons: string[];
}

/** What the check step adds to the form. */
export interface CheckAids {
  /** The fields to check and why (a low confidence or a failed check), shown in amber. */
  doubtful: Partial<Record<FieldPath, string>>;
  /** The handwritten date and number were never confirmed (amber until they are). */
  handwrittenToConfirm?: boolean;
  /** The handwritten note's enlarged crop, above the two fields. */
  note?: ReactNode;
  suggestions?: { date: Suggestion[]; number: Suggestion[] };
  /** A field got the focus (its box is shown on the document), or none has it. */
  onFieldFocus?: (path: FieldPath | null) => void;
}

export function FieldsForm({
  customer,
  submitLabel,
  initial,
  aids,
  onSubmit,
}: {
  customer: { name: string; ico: string };
  submitLabel: string;
  initial?: FieldValues;
  aids?: CheckAids;
  onSubmit: (document: InvoiceDocument) => Promise<void>;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const errorText = useErrorText();
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState('');
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<ReadonlySet<FieldPath>>(new Set());
  const submitButton = useRef<HTMLButtonElement>(null);
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
      invoice: z
        .object({
          number: free,
          variable_symbol: free,
          issue_date: required,
          delivery_date: free,
          delivery_as_issue: z.boolean(),
          due_date: free,
          document_type: z.enum(['invoice', 'credit_note']),
        })
        .superRefine((invoice, ctx) => {
          // Decision 61: every invoice has a date of supply; the issue date stands in only
          // when the invoice does not print one.
          if (!invoice.delivery_as_issue && invoice.delivery_date.trim() === '') {
            ctx.addIssue({
              code: 'custom',
              path: ['delivery_date'],
              message: t('fieldsForm.deliveryRequired'),
            });
          }
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
  const values = useWatch({ control: form.control }) as FieldValues;
  const errorAt = (name: FieldPath): string | undefined => {
    const found: unknown = get(errors, name);
    if (typeof found !== 'object' || found === null || !('message' in found)) return undefined;
    return typeof found.message === 'string' ? found.message : undefined;
  };
  const documentType = values.invoice.document_type;
  const asIssue = values.invoice.delivery_as_issue;

  const valueOf = (name: FieldPath): string => {
    const found: unknown = get(values, name);
    return typeof found === 'string' ? found : '';
  };
  const emptyRequired = (name: FieldPath): boolean =>
    (REQUIRED.includes(name) || (name === 'invoice.delivery_date' && !asIssue)) &&
    valueOf(name).trim() === '';
  /** Amber: read with doubt, or handwritten (always the user's to confirm), not yet confirmed. */
  const amber = (name: FieldPath): string | undefined => {
    if (!aids || confirmed.has(name)) return undefined;
    if (name in HANDWRITTEN && aids.handwrittenToConfirm && !aids.doubtful[name]) {
      return t('fieldsForm.marks.handwritten');
    }
    return aids.doubtful[name];
  };
  const toCheck = (name: FieldPath): boolean =>
    amber(name) !== undefined || (aids !== undefined && emptyRequired(name));

  const confirm = (name: FieldPath) => {
    setConfirmed((current) => (current.has(name) ? current : new Set([...current, name])));
  };

  const suggestionsOf = (name: FieldPath): Suggestion[] => {
    const kind = (HANDWRITTEN as Record<string, 'date' | 'number' | undefined>)[name];
    return kind && aids?.suggestions ? aids.suggestions[kind] : [];
  };

  /** The next field to check after `name`, in the form's order, that can take the focus. */
  const nextToCheck = (name: FieldPath, skipping: FieldPath | null): FieldPath | undefined => {
    const from = FIELDS.indexOf(name);
    return FIELDS.slice(from + 1).find(
      (path) =>
        path !== skipping && toCheck(path) && !(path === 'invoice.delivery_date' && asIssue),
    );
  };

  const keyDown = (event: KeyboardEvent<HTMLInputElement>, name: FieldPath) => {
    if (!aids || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      const first = suggestionsOf(name)[0];
      if (valueOf(name).trim() === '' && first) {
        form.setValue(name, first.value, { shouldDirty: true });
      }
      confirm(name);
      const next = nextToCheck(name, name);
      if (next) form.setFocus(next);
      else submitButton.current?.focus();
    } else if (event.key === 'Tab' && !event.shiftKey) {
      const next = nextToCheck(name, null);
      if (next) {
        event.preventDefault();
        form.setFocus(next);
      }
    }
  };

  const submit = form.handleSubmit(async (filled) => {
    try {
      await onSubmit(documentOf(filled, customer));
    } catch (error) {
      if (!applyFieldErrors(error, form.setError, FIELDS, errorText)) notify.failure(error);
    }
  });

  const input = (name: FieldPath, label: string, props: Partial<TextInputProps> = {}) => {
    const registered = form.register(name);
    const warn = amber(name);
    const missing = aids !== undefined && emptyRequired(name) ? t('errors.required') : undefined;
    return (
      <TextInput
        label={label}
        {...props}
        {...registered}
        onChange={(event) => {
          confirm(name);
          void registered.onChange(event);
        }}
        onFocus={() => aids?.onFieldFocus?.(name)}
        onKeyDown={(event) => {
          keyDown(event, name);
        }}
        description={warn ?? props.description}
        error={errorAt(name) ?? missing}
        data-check={warn ? 'doubtful' : undefined}
        styles={
          warn && !errorAt(name) && !missing
            ? {
                input: {
                  borderColor: 'var(--mantine-color-orange-8)',
                  borderWidth: 2,
                  background: 'var(--mantine-color-orange-light)',
                },
              }
            : undefined
        }
      />
    );
  };

  const suggestions = (name: FieldPath, label: string) => {
    const list = suggestionsOf(name);
    if (list.length === 0) return null;
    return (
      <Group gap={6} role="group" aria-label={t('fieldsForm.suggestionsFor', { field: label })}>
        {list.map((s) => {
          const shown = name === 'handwritten.date' ? formatDate(s.value) : s.value;
          const notes = [
            ...(s.source === 'counter' ? [t('fieldsForm.fromCounter')] : []),
            ...s.reasons.map((r) =>
              t(`fieldsForm.reasons.${r}` as 'fieldsForm.reasons.below_counter', {
                defaultValue: r,
              }),
            ),
          ];
          return (
            <Button
              key={`${s.source}-${s.value}`}
              size="compact-sm"
              variant={s.plausible ? 'light' : 'default'}
              onClick={() => {
                form.setValue(name, s.value, { shouldDirty: true, shouldValidate: true });
                confirm(name);
              }}
            >
              {notes.length ? `${shown} · ${notes.join(', ')}` : shown}
            </Button>
          );
        })}
      </Group>
    );
  };

  const delivery = form.register('invoice.delivery_as_issue');

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Stack gap="md">
        {!aids && (
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
        )}
        {aids && (
          <Text size="sm" c="dimmed">
            {t('fieldsForm.keyboard')}
          </Text>
        )}
        <Fieldset legend={t('fieldsForm.handwritten')}>
          <Stack gap="sm">
            {aids?.note}
            <SimpleGrid type="container" cols={{ base: 1, '420px': 2 }} spacing="sm">
              <Stack gap={6}>
                {input('handwritten.date', t('fieldsForm.handwrittenDate'), { type: 'date' })}
                {suggestions('handwritten.date', t('fieldsForm.handwrittenDate'))}
              </Stack>
              <Stack gap={6}>
                {input('handwritten.number', t('fieldsForm.handwrittenNumber'), {
                  description: t('fieldsForm.handwrittenNumberHint'),
                  inputMode: 'numeric',
                })}
                {suggestions('handwritten.number', t('fieldsForm.handwrittenNumber'))}
              </Stack>
            </SimpleGrid>
          </Stack>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.supplier')}>
          <SimpleGrid type="container" cols={{ base: 1, '420px': 2, '680px': 3 }} spacing="sm">
            {input('supplier.name', t('fieldsForm.supplierName'), { withAsterisk: true })}
            {input('supplier.ico', t('fieldsForm.ico'), { inputMode: 'numeric' })}
            {input('supplier.dic', t('fieldsForm.dic'))}
            {input('supplier.ic_dph', t('fieldsForm.icDph'))}
            {input('supplier.iban', t('fieldsForm.iban'))}
            {input('supplier.address', t('fieldsForm.address'))}
          </SimpleGrid>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.header')}>
          <SimpleGrid type="container" cols={{ base: 1, '420px': 2, '680px': 3 }} spacing="sm">
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
            <Stack gap={6}>
              {input('invoice.delivery_date', t('fieldsForm.deliveryDate'), {
                type: 'date',
                withAsterisk: !asIssue,
                disabled: asIssue,
                description: t('fieldsForm.deliveryHint'),
              })}
              <Checkbox
                size="xs"
                label={t('fieldsForm.deliveryAsIssue')}
                {...delivery}
                onChange={(event) => {
                  confirm('invoice.delivery_date');
                  void delivery.onChange(event);
                  if (errors.invoice?.delivery_date) {
                    void form.trigger('invoice.delivery_date');
                  }
                }}
              />
            </Stack>
            {input('invoice.due_date', t('fieldsForm.dueDate'), { type: 'date' })}
          </SimpleGrid>
        </Fieldset>
        <Fieldset legend={t('fieldsForm.totals')}>
          <SimpleGrid type="container" cols={{ base: 1, '420px': 3 }} spacing="sm">
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
          <Button ref={submitButton} type="submit" loading={isSubmitting}>
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
