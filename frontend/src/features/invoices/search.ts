import type { Schemas } from '../../api/client';
import type { paths } from '../../api/schema';

/**
 * The invoice table's state in the URL (plan §10.3): every filter, the sort and the page, so a
 * filtered view is a link. The names are the API's query parameters; `mine` stands for
 * "uploaded by me".
 */

export const STATES = [
  'uploaded',
  'extracting',
  'extraction_failed',
  'extracted',
  'checked',
  'needs_review',
  'ready',
  'booked',
  'exported',
  'paid',
  'discarded',
  'duplicate',
] as const;
export type InvoiceState = (typeof STATES)[number];

export const CHANNELS = ['scan', 'digital_pdf', 'einvoice', 'manual', 'dataset'] as const;
export type Channel = (typeof CHANNELS)[number];

export const SORT_KEYS = [
  'state',
  'document_number',
  'booking_date',
  'supplier_name',
  'supplier_ico',
  'invoice_number',
  'variable_symbol',
  'issue_date',
  'due_date',
  'supply_date',
  'gross',
  'uploaded_at',
  'exported_at',
  'paid_on',
] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export const DATE_FILTERS = ['issue', 'due', 'booking', 'uploaded', 'exported', 'paid'] as const;
export type DateFilter = (typeof DATE_FILTERS)[number];
type DateBound = `${DateFilter}_${'from' | 'to'}`;

export const DEFAULT_SORT = '-uploaded_at';

export interface InvoiceSearch extends Partial<Record<DateBound, string>> {
  q?: string;
  supplier_ico?: string;
  supplier?: string;
  /** The chosen supplier's name, shown in the filter (not sent to the API). */
  state?: InvoiceState[];
  series?: string[];
  channel?: Channel[];
  needs_review?: boolean;
  mine?: boolean;
  amount_min?: string;
  amount_max?: string;
  budget?: string;
  md?: string;
  dal?: string;
  sort?: string;
  page?: number;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const AMOUNT = /^-?\d+([.,]\d{1,2})?$/;

function text(value: unknown, max = 200): string | undefined {
  if (typeof value !== 'string' && typeof value !== 'number') return undefined;
  const found = String(value).trim().slice(0, max);
  return found || undefined;
}

function list<T extends string>(value: unknown, allowed: readonly T[]): T[] | undefined {
  const items = (Array.isArray(value) ? value : [value]).filter(
    (v): v is T => typeof v === 'string' && allowed.includes(v as T),
  );
  return items.length ? [...new Set(items)] : undefined;
}

function strings(value: unknown): string[] | undefined {
  const items = (Array.isArray(value) ? value : [value])
    .map((v) => text(v, 16))
    .filter((v): v is string => v !== undefined);
  return items.length ? [...new Set(items)] : undefined;
}

function flag(value: unknown): boolean | undefined {
  if (value === true || value === 'true') return true;
  if (value === false || value === 'false') return false;
  return undefined;
}

/** The URL's search, checked: unknown values are dropped, so a hand-edited link still works. */
export function invoicesSearch(raw: Record<string, unknown>): InvoiceSearch {
  const found: InvoiceSearch = {
    q: text(raw.q),
    supplier_ico:
      typeof raw.supplier_ico === 'string' && /^\d{8}$/.test(raw.supplier_ico)
        ? raw.supplier_ico
        : undefined,
    supplier: text(raw.supplier),
    state: list(raw.state, STATES),
    series: strings(raw.series),
    channel: list(raw.channel, CHANNELS),
    needs_review: flag(raw.needs_review),
    mine: flag(raw.mine) ? true : undefined,
    budget: text(raw.budget, 32),
    md: text(raw.md, 16),
    dal: text(raw.dal, 16),
  };
  for (const name of DATE_FILTERS) {
    for (const end of ['from', 'to'] as const) {
      const value = raw[`${name}_${end}`];
      if (typeof value === 'string' && ISO_DATE.test(value)) found[`${name}_${end}`] = value;
    }
  }
  for (const name of ['amount_min', 'amount_max'] as const) {
    const value = text(raw[name], 20);
    if (value && AMOUNT.test(value)) found[name] = value.replace(',', '.');
  }
  const sort = text(raw.sort, 40);
  if (sort && SORT_KEYS.includes(sort.replace(/^-/, '') as SortKey)) found.sort = sort;
  const page = Number(raw.page);
  if (Number.isInteger(page) && page > 1) found.page = page;
  return without(found, []);
}

/** The search without the given keys and without unset ones. */
function without<K extends keyof InvoiceSearch>(
  search: InvoiceSearch,
  keys: readonly K[],
): Omit<InvoiceSearch, K> {
  return Object.fromEntries(
    Object.entries(search).filter(([k, v]) => v !== undefined && !keys.includes(k as K)),
  ) as Omit<InvoiceSearch, K>;
}

/** The filters set, without the sort and the page: what an export of the view takes. */
export function filtersOf(search: InvoiceSearch): InvoiceSearch {
  return without(search, ['sort', 'page']);
}

/** How many filters are set (the supplier's name and the flags count once each). */
export function activeFilters(search: InvoiceSearch): number {
  return Object.keys(without(search, ['sort', 'page', 'supplier'])).length;
}

export type InvoiceQuery = NonNullable<
  paths['/api/customers/{customer_id}/invoices']['get']['parameters']['query']
>;

/** The API's query for a page of the view. `me` is the caller's ID (for `mine`). */
export function apiQuery(
  search: InvoiceSearch,
  me: string | undefined,
  size: number,
): InvoiceQuery {
  return {
    ...without(search, ['supplier', 'mine', 'sort', 'page']),
    uploaded_by: search.mine && me ? me : undefined,
    sort: search.sort ?? DEFAULT_SORT,
    page: search.page ?? 1,
    size,
  };
}

export type ExportFilter = Schemas['ExportFilterIn'];

/** The view's filters as an export's body takes them. */
export function exportFilter(search: InvoiceSearch, me: string | undefined): ExportFilter {
  const body: ExportFilter = without(search, ['supplier', 'mine', 'sort', 'page']);
  if (search.mine && me) body.uploaded_by = me;
  return body;
}

/** The sort toggled by a click on a column: ascending, then descending, by that column. */
export function nextSort(current: string | undefined, key: SortKey): string {
  const now = current ?? DEFAULT_SORT;
  return now === key ? `-${key}` : key;
}

/** The invoice page's tab and, from Nová faktúra, the uploads still to check after it. */
export interface InvoicePageSearch {
  tab?: 'check' | 'proposal' | 'fields' | 'history';
  queue?: string;
}

const TABS = new Set(['check', 'proposal', 'fields', 'history']);

export function invoicePageSearch(raw: Record<string, unknown>): InvoicePageSearch {
  const tab = typeof raw.tab === 'string' && TABS.has(raw.tab) ? raw.tab : undefined;
  const queue =
    typeof raw.queue === 'string' && /^[\w-]+(,[\w-]+)*$/.test(raw.queue) ? raw.queue : undefined;
  return { tab: tab as InvoicePageSearch['tab'], queue };
}
