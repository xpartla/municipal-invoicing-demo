import type { Schemas } from '../../api/client';
import { formatAmountForCopy } from '../../lib/format';

/**
 * A coding as the detail page edits it (plan §10.4): the document header and lines that pair
 * a posting line with its budget line, as the demo's proposal page did. Amounts stay as typed
 * (`93,71`) until the coding is sent.
 */

export type Coding = Schemas['Coding'];
export type Proposal = Schemas['CodingProposal'];
export type Alternative = Schemas['Alternative'];

export interface Line {
  key: string;
  md: string;
  dal: string;
  amount: string;
  budgetText: string;
  postingText: string;
  transfer: string;
  /** '' for the proposed line, else the index of the alternative swapped in. */
  choice: string;
}

export interface DocumentFields {
  series: string;
  number: string;
  booking_date: string;
}

export const KEY_PARTS = ['ek', 'zdroj', 'oddiel', 'trieda', 'analytika'] as const;
export type KeyPart = (typeof KEY_PARTS)[number];
export const KEY_PATTERN = /^\d{6} \d[0-9A-Za-z]{1,3} \d{2} \d{3} \d{3}$/;

export function keyParts(key: string): Record<KeyPart, string> {
  const [ek = '', zdroj = '', oddiel = '', trieda = '', analytika = ''] = key.split(' ');
  return { ek, zdroj, oddiel, trieda, analytika };
}

/** `93,71`, `93.71` or `1 234,5` → 93.71; null when it is not a number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[\s\u00a0]/g, '').replace(',', '.');
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
  return Math.round(Number(cleaned) * 100) / 100;
}

export function linesOf(coding: Pick<Coding, 'posting' | 'budget'>): Line[] {
  return coding.budget.map((budget, i) => {
    const post = coding.posting[i];
    return {
      key: budget.key,
      md: post?.md ?? '',
      dal: post?.dal ?? '',
      amount: formatAmountForCopy(budget.amount),
      budgetText: budget.text,
      postingText: post?.text ?? '',
      transfer: budget.transfer ?? post?.transfer ?? '',
      choice: '',
    };
  });
}

export function documentOf(coding: Pick<Coding, 'document'>): DocumentFields {
  return {
    series: coding.document.series,
    number: coding.document.number ?? '',
    booking_date: coding.document.booking_date ?? '',
  };
}

/** The coding to send: amounts as numbers, the transfer on both lines, as the engine does. */
export function codingOf(doc: DocumentFields, lines: Line[]): Coding {
  return {
    document: {
      series: doc.series,
      number: doc.number || null,
      booking_date: doc.booking_date || null,
    },
    posting: lines.map((line) => ({
      md: line.md,
      dal: line.dal,
      amount: parseAmount(line.amount) ?? 0,
      text: line.postingText,
      stredisko: null,
      transfer: line.transfer || null,
    })),
    budget: lines.map((line) => ({
      key: line.key,
      ...keyParts(line.key),
      amount: parseAmount(line.amount) ?? 0,
      text: line.budgetText,
      stredisko: null,
      transfer: line.transfer || null,
    })),
  };
}

function shape(coding: Coding): string {
  return JSON.stringify({
    document: [
      coding.document.series,
      coding.document.number ?? null,
      coding.document.booking_date ?? null,
    ],
    lines: coding.budget.map((b, i) => [
      b.key,
      coding.posting[i]?.md,
      coding.posting[i]?.dal,
      b.amount,
      b.text,
      coding.posting[i]?.text,
      b.transfer ?? coding.posting[i]?.transfer ?? null,
    ]),
  });
}

/** Whether two codings book the same (the accepted-or-corrected decision). */
export function sameCoding(a: Coding, b: Coding): boolean {
  return shape(a) === shape(b);
}

/** The line swapped for an alternative (or back to the proposed line, `null`). */
export function swapped(
  line: Line,
  alternative: Alternative | null,
  proposed: Line,
  choice: string,
): Line {
  if (alternative === null) return { ...proposed, choice: '' };
  return {
    ...line,
    key: alternative.budget_key,
    md: alternative.md ?? line.md,
    dal: alternative.dal ?? line.dal,
    transfer: alternative.transfer ?? '',
    budgetText: alternative.budget_text ?? line.budgetText,
    postingText: alternative.posting_text ?? line.postingText,
    choice,
  };
}

/** The posting line as one tab-separated row, in the order of TOPSET's columns. */
export function postingRow(line: Line): string {
  return [line.md, line.dal, formatAmountForCopy(parseAmount(line.amount)), line.postingText].join(
    '\t',
  );
}

export function budgetRow(line: Line): string {
  return [line.key, formatAmountForCopy(parseAmount(line.amount)), line.budgetText].join('\t');
}

export interface Problem {
  /** An i18n key under `invoice.problems`. */
  key: string;
  values?: Record<string, string | number>;
}

export interface Lists {
  positions: ReadonlySet<string>;
  accounts: ReadonlySet<string>;
}

/** What keeps a correction from being saved (errors) or deserves a look (warnings). */
export function problems(
  doc: DocumentFields,
  lines: Line[],
  gross: number | null,
  lists: Lists | null,
): { errors: Problem[]; warnings: Problem[] } {
  const errors: Problem[] = [];
  const warnings: Problem[] = [];
  if (lines.length === 0) errors.push({ key: 'noLines' });
  lines.forEach((line, i) => {
    const n = i + 1;
    if (!KEY_PATTERN.test(line.key) || (lists && !lists.positions.has(line.key))) {
      errors.push({ key: 'position', values: { n, value: line.key || '—' } });
    }
    for (const side of ['md', 'dal'] as const) {
      if (!line[side] || (lists && !lists.accounts.has(line[side]))) {
        errors.push({ key: side, values: { n, value: line[side] || '—' } });
      }
    }
    if (parseAmount(line.amount) === null) errors.push({ key: 'amount', values: { n } });
    if (!line.budgetText.trim() || !line.postingText.trim()) {
      warnings.push({ key: 'text', values: { n } });
    }
  });
  const total = lines.reduce((sum, line) => sum + (parseAmount(line.amount) ?? 0), 0);
  if (gross !== null && Math.abs(total - gross) > 0.004) {
    warnings.push({ key: 'total', values: { total: total.toFixed(2), gross: gross.toFixed(2) } });
  }
  if (!doc.booking_date) warnings.push({ key: 'date' });
  return { errors, warnings };
}
