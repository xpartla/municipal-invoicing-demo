import { formatAmountForCopy } from '../../lib/format';
import type { InvoiceDocument } from './api';
import { parseAmount } from './coding';

/** The field form's values (`FieldsForm`) and their way to and from an InvoiceDocument. */

export interface FieldValues {
  handwritten: { date: string; number: string };
  supplier: {
    name: string;
    ico: string;
    dic: string;
    ic_dph: string;
    iban: string;
    address: string;
  };
  invoice: {
    number: string;
    variable_symbol: string;
    issue_date: string;
    delivery_date: string;
    /** The invoice prints no date of supply: the issue date stands in (decision 61). */
    delivery_as_issue: boolean;
    due_date: string;
    document_type: 'invoice' | 'credit_note';
  };
  totals: { net: string; vat: string; gross: string };
  lines: { description: string; gross: string }[];
  notes: string;
}

export function emptyValues(): FieldValues {
  return {
    handwritten: { date: '', number: '' },
    supplier: { name: '', ico: '', dic: '', ic_dph: '', iban: '', address: '' },
    invoice: {
      number: '',
      variable_symbol: '',
      issue_date: '',
      delivery_date: '',
      delivery_as_issue: false,
      due_date: '',
      document_type: 'invoice',
    },
    totals: { net: '', vat: '', gross: '' },
    lines: [],
    notes: '',
  };
}

const text = (value: unknown): string =>
  typeof value === 'string' ? value : typeof value === 'number' ? String(value) : '';
const amount = (value: unknown): string =>
  typeof value === 'number' || typeof value === 'string'
    ? formatAmountForCopy(parseAmount(String(value)))
    : '';

/**
 * An InvoiceDocument (or anything shaped like one) as the form's values. Without a date of
 * supply the issue date stands in for it, unless `deliveryAsIssue` is off (a fresh reading:
 * the user says whether the invoice prints one).
 */
export function valuesOf(source: object, { deliveryAsIssue = true } = {}): FieldValues {
  const document = source as Record<string, unknown>;
  const part = (name: string) => (document[name] ?? {}) as Record<string, unknown>;
  const supplier = part('supplier');
  const invoice = part('invoice');
  const handwritten = part('handwritten');
  const totals = part('totals');
  const lines = Array.isArray(document.lines) ? (document.lines as Record<string, unknown>[]) : [];
  const notes = Array.isArray(document.free_text) ? document.free_text.map(text) : [];
  return {
    handwritten: { date: text(handwritten.date), number: text(handwritten.number) },
    supplier: {
      name: text(supplier.name),
      ico: text(supplier.ico),
      dic: text(supplier.dic),
      ic_dph: text(supplier.ic_dph),
      iban: text(supplier.iban),
      address: text(supplier.address),
    },
    invoice: {
      number: text(invoice.number),
      variable_symbol: text(invoice.variable_symbol),
      issue_date: text(invoice.issue_date),
      delivery_date: text(invoice.delivery_date),
      delivery_as_issue: deliveryAsIssue && !text(invoice.delivery_date),
      due_date: text(invoice.due_date),
      document_type: invoice.document_type === 'credit_note' ? 'credit_note' : 'invoice',
    },
    totals: { net: amount(totals.net), vat: amount(totals.vat), gross: amount(totals.gross) },
    lines: lines.map((line) => ({
      description: text(line.description),
      gross: amount(line.gross),
    })),
    notes: notes.join('\n'),
  };
}

const orNull = (value: string) => (value.trim() === '' ? null : value.trim());
const amountOrNull = (value: string) => (value.trim() === '' ? null : parseAmount(value));

/** The form's values as the InvoiceDocument the API takes. */
export function documentOf(
  values: FieldValues,
  customer: { name: string; ico: string },
): InvoiceDocument {
  return {
    id: 'new',
    supplier: {
      name: orNull(values.supplier.name),
      ico: orNull(values.supplier.ico),
      dic: orNull(values.supplier.dic),
      ic_dph: orNull(values.supplier.ic_dph),
      iban: orNull(values.supplier.iban),
      address: orNull(values.supplier.address),
    },
    customer: { name: customer.name, ico: customer.ico },
    invoice: {
      number: orNull(values.invoice.number),
      variable_symbol: orNull(values.invoice.variable_symbol),
      issue_date: orNull(values.invoice.issue_date),
      delivery_date: values.invoice.delivery_as_issue ? null : orNull(values.invoice.delivery_date),
      due_date: orNull(values.invoice.due_date),
      currency: 'EUR',
      document_type: values.invoice.document_type,
    },
    handwritten: {
      date: orNull(values.handwritten.date),
      number: orNull(values.handwritten.number),
    },
    totals: {
      net: amountOrNull(values.totals.net),
      vat: amountOrNull(values.totals.vat),
      gross: amountOrNull(values.totals.gross),
      vat_rates: [],
    },
    lines: values.lines
      .filter((line) => line.description.trim() !== '')
      .map((line) => ({ description: line.description.trim(), gross: amountOrNull(line.gross) })),
    free_text: values.notes
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean),
    ocr_meta: { synthetic: false, confidence: {} },
  };
}
