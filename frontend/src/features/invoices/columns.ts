import { useCallback, useState } from 'react';

import type { SortKey } from './search';

/** The invoice table's columns (plan §10.3), which the user chooses; remembered per browser. */

export const COLUMNS = [
  { key: 'state', sort: 'state' },
  { key: 'number', sort: 'document_number' },
  { key: 'booking_date', sort: 'booking_date' },
  { key: 'supplier', sort: 'supplier_name' },
  { key: 'ico', sort: 'supplier_ico' },
  { key: 'invoice_number', sort: 'invoice_number' },
  { key: 'vs', sort: 'variable_symbol' },
  { key: 'issue_date', sort: 'issue_date' },
  { key: 'supply_date', sort: 'supply_date' },
  { key: 'due_date', sort: 'due_date' },
  { key: 'gross', sort: 'gross' },
  { key: 'budget', sort: null },
  { key: 'md_dal', sort: null },
  { key: 'uploaded', sort: 'uploaded_at' },
  { key: 'exported', sort: 'exported_at' },
  { key: 'paid', sort: 'paid_on' },
  { key: 'source', sort: null },
] as const satisfies readonly { key: string; sort: SortKey | null }[];

export type ColumnKey = (typeof COLUMNS)[number]['key'];

export const DEFAULT_COLUMNS: ColumnKey[] = [
  'state',
  'number',
  'booking_date',
  'supplier',
  'invoice_number',
  'gross',
  'budget',
  'uploaded',
];

export const COLUMNS_STORAGE = 'riso.invoices.columns';

const KNOWN = new Set<string>(COLUMNS.map((c) => c.key));

function stored(): ColumnKey[] | null {
  try {
    const raw = globalThis.localStorage.getItem(COLUMNS_STORAGE);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const keys = parsed.filter((k): k is ColumnKey => typeof k === 'string' && KNOWN.has(k));
    return keys.length ? keys : null;
  } catch {
    return null;
  }
}

/** The chosen columns, in the table's order, kept in this browser's storage. */
export function useColumnChoice() {
  const [chosen, setChosen] = useState<ColumnKey[]>(() => stored() ?? DEFAULT_COLUMNS);
  const choose = useCallback((keys: ColumnKey[]) => {
    const ordered = COLUMNS.map((c) => c.key).filter((k) => keys.includes(k));
    const next = ordered.length ? ordered : DEFAULT_COLUMNS;
    setChosen(next);
    try {
      globalThis.localStorage.setItem(COLUMNS_STORAGE, JSON.stringify(next));
    } catch {
      // Storage may be blocked (a private window); the choice then lasts for the page.
    }
  }, []);
  return { chosen, choose };
}
