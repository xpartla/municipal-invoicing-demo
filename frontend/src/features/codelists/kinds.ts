import type { ListKind } from './api';

/**
 * How each list is shown and edited (plan §10.6): its columns in order, and the fields of its
 * row dialog. A budget position's key is its five parts, shown as labelled columns. Labels
 * are i18n keys under `codelists.fields`.
 */

export type CustomerKind = Exclude<ListKind, GlobalKind>;
export type GlobalKind = 'ek' | 'cofog' | 'funding_sources' | 'framework_accounts';

/** The tabs of Číselníky, in the plan's order. */
export const CUSTOMER_TABS: readonly CustomerKind[] = [
  'budget_expense',
  'budget_income',
  'accounts',
  'document_series',
  'transfers',
  'cost_centres',
];

export const GLOBAL_TABS: readonly GlobalKind[] = [
  'ek',
  'cofog',
  'funding_sources',
  'framework_accounts',
];

export type FieldName =
  | 'ek'
  | 'zdroj'
  | 'oddiel'
  | 'trieda'
  | 'analytika'
  | 'description'
  | 'approved'
  | 'adjusted'
  | 'su'
  | 'au'
  | 'type'
  | 'activity'
  | 'code'
  | 'series_id'
  | 'pattern'
  | 'bank_account'
  | 'id'
  | 'name';

export interface FieldSpec {
  name: FieldName;
  /** Must be filled in. */
  required?: boolean;
  /** Digits only, of this length (a code part). */
  digits?: number;
  /** An amount: shown formatted, typed with a decimal comma. */
  amount?: boolean;
  /** Chosen from a list (`type`: the account types). */
  options?: readonly string[];
  /** A short code: a narrow column. */
  code?: boolean;
}

const BUDGET_KEY: FieldSpec[] = [
  { name: 'ek', required: true, digits: 6, code: true },
  { name: 'zdroj', required: true, code: true },
  { name: 'oddiel', required: true, digits: 2, code: true },
  { name: 'trieda', required: true, digits: 3, code: true },
  { name: 'analytika', required: true, digits: 3, code: true },
];

export const ACCOUNT_TYPES = ['active', 'passive', 'cost', 'revenue'] as const;

export const FIELDS: Record<CustomerKind, FieldSpec[]> = {
  budget_expense: [
    ...BUDGET_KEY,
    { name: 'description' },
    { name: 'approved', amount: true },
    { name: 'adjusted', amount: true },
  ],
  budget_income: [
    { name: 'ek', required: true, digits: 6, code: true },
    { name: 'zdroj', required: true, code: true },
    { name: 'analytika', required: true, digits: 3, code: true },
    { name: 'description' },
    { name: 'approved', amount: true },
    { name: 'adjusted', amount: true },
  ],
  accounts: [
    { name: 'su', required: true, digits: 3, code: true },
    { name: 'au', required: true, digits: 3, code: true },
    { name: 'type', required: true, options: ACCOUNT_TYPES },
    { name: 'description' },
    { name: 'activity' },
  ],
  document_series: [
    { name: 'code', required: true, code: true },
    { name: 'series_id', required: true, code: true },
    { name: 'pattern', required: true },
    { name: 'description', required: true },
    { name: 'bank_account' },
  ],
  transfers: [
    { name: 'id', required: true },
    { name: 'name', required: true },
    { name: 'zdroj', required: true, code: true },
  ],
  cost_centres: [
    { name: 'code', required: true, code: true },
    { name: 'name', required: true },
  ],
};

export const GLOBAL_FIELDS: FieldSpec[] = [{ name: 'code', code: true }, { name: 'name' }];

/** Whether a kind is one of a customer's lists (not a global one). */
export function isCustomerKind(kind: string): kind is CustomerKind {
  return (CUSTOMER_TABS as readonly string[]).includes(kind);
}

/** An amount as the user types it (`1 200,50`) as the API reads it (`1200.50`). */
export function parseAmount(text: string): string {
  return text.replace(/\s/g, '').replace(',', '.');
}

/** A field's value as text: empty for none, lists joined, numbers and booleans as written. */
export function valueText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.map(valueText).join(', ');
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

export interface CodelistsSearch {
  kind?: CustomerKind;
  q?: string;
  year?: number;
}

/** `?kind=accounts&q=518 010&year=2026`: the tab, the search and the year to open with (the
 * health report's links). */
export function codelistsSearch(search: Record<string, unknown>): CodelistsSearch {
  const year = Number(search.year);
  return {
    kind: typeof search.kind === 'string' && isCustomerKind(search.kind) ? search.kind : undefined,
    q: typeof search.q === 'string' ? search.q : undefined,
    year: Number.isInteger(year) && year >= 2000 && year <= 2100 ? year : undefined,
  };
}
