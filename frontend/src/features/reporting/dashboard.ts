import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';
import type { InvoiceSearch } from '../invoices/search';

/** Domov (plan §10.2, decision 67): the customer's numbers for a Bratislava month. */

export type Dashboard = Schemas['DashboardOut'];
export type DashboardTiles = Dashboard['tiles'];
export type AttentionItem = Schemas['AttentionItemOut'];

const MONTH = /^(\d{4})-(0[1-9]|1[0-2])$/;

/** `2026-11` for the month Bratislava is in now. */
export function currentMonth(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Bratislava',
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(now);
  const year = parts.find((p) => p.type === 'year')?.value ?? '2026';
  const month = parts.find((p) => p.type === 'month')?.value ?? '01';
  return `${year}-${month}`;
}

export function isMonth(value: unknown): value is string {
  return typeof value === 'string' && MONTH.test(value);
}

/** `2026-11` shifted by `months`: `shiftMonth('2026-11', 2)` is `2027-01`. */
export function shiftMonth(month: string, months: number): string {
  const [year = 0, number = 1] = month.split('-').map(Number);
  const index = year * 12 + number - 1 + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
}

/** The month's first and last day, ISO: what the invoice table's date filters take. */
export function monthDays(month: string): { first: string; last: string } {
  const [year = 0, number = 1] = month.split('-').map(Number);
  const last = new Date(Date.UTC(year, number, 0)).getUTCDate();
  return { first: `${month}-01`, last: `${month}-${String(last).padStart(2, '0')}` };
}

/** `2026-11` → `november 2026`. */
export function monthLabel(month: string): string {
  const [year = 0, number = 1] = month.split('-').map(Number);
  return new Intl.DateTimeFormat('sk-SK', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, number - 1, 15)));
}

export function useDashboard(customerId: string, month: string) {
  return useQuery({
    queryKey: ['dashboard', customerId, month],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}/dashboard', {
          params: { path: { customer_id: customerId }, query: { month } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export interface HomeSearch {
  month?: string;
}

export function homeSearch(raw: Record<string, unknown>): HomeSearch {
  return { month: isMonth(raw.month) ? raw.month : undefined };
}

export type TileKey = keyof DashboardTiles;

/** The invoice table's filter behind each tile (plan §10.2: each tile links to it). */
export function tileSearch(tile: TileKey, month: string): InvoiceSearch {
  const { first, last } = monthDays(month);
  const uploaded = { uploaded_from: first, uploaded_to: last };
  switch (tile) {
    case 'uploaded':
      return uploaded;
    case 'waiting':
      return { ...uploaded, state: ['extracted'] };
    case 'review':
      return { ...uploaded, state: ['needs_review'] };
    case 'failed':
      return { ...uploaded, state: ['extraction_failed'] };
    case 'booked':
    case 'booked_total':
      return { booked_from: first, booked_to: last };
  }
}

/** Seconds in the largest units that matter: `4 d 23 h`, `3 h 15 min`, `12 min`. */
export function durationParts(seconds: number): {
  unit: 'days' | 'hours' | 'minutes';
  days: number;
  hours: number;
  minutes: number;
} {
  const total = Math.round(seconds / 60);
  const days = Math.floor(total / 1440);
  const hours = Math.floor((total % 1440) / 60);
  const minutes = total % 60;
  const unit = days > 0 ? 'days' : hours > 0 ? 'hours' : 'minutes';
  return { unit, days, hours, minutes };
}
