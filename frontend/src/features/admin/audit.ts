import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';

/** The audit viewer (plan §10.9): the log filtered by actor, customer, action and time. */

export type AuditEvent = Schemas['AuditEventOut'];

export const AUDIT_PAGE = 50;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ID = /^[\w-]{1,36}$/;

export interface AuditSearch {
  actor?: string;
  customer?: string;
  action?: string;
  from?: string;
  to?: string;
  page?: number;
}

export function auditSearch(raw: Record<string, unknown>): AuditSearch {
  const id = (value: unknown) => (typeof value === 'string' && ID.test(value) ? value : undefined);
  const day = (value: unknown) =>
    typeof value === 'string' && ISO_DATE.test(value) ? value : undefined;
  const action =
    typeof raw.action === 'string' && raw.action.trim()
      ? raw.action.trim().slice(0, 80)
      : undefined;
  const page = Number(raw.page);
  return {
    actor: id(raw.actor),
    customer: id(raw.customer),
    action,
    from: day(raw.from),
    to: day(raw.to),
    page: Number.isInteger(page) && page > 1 ? page : undefined,
  };
}

/** The instant a Bratislava day starts, as UTC ISO: `2026-11-01` → `2026-10-31T23:00:00Z`. */
export function dayStart(day: string): string {
  const [year = 0, month = 1, date = 1] = day.split('-').map(Number);
  // Bratislava is UTC+1 or UTC+2; find the offset of that midnight.
  for (const offset of [1, 2]) {
    const guess = new Date(Date.UTC(year, month - 1, date, -offset));
    const local = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Bratislava',
      hour: '2-digit',
      hourCycle: 'h23',
    }).format(guess);
    if (local === '00') return guess.toISOString().replace('.000Z', 'Z');
  }
  return `${day}T00:00:00Z`;
}

function nextDay(day: string): string {
  const [year = 0, month = 1, date = 1] = day.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, date + 1)).toISOString().slice(0, 10);
}

export function useAudit(search: AuditSearch) {
  return useQuery({
    queryKey: ['audit', search],
    queryFn: () =>
      unwrap(
        api.GET('/api/admin/audit', {
          params: {
            query: {
              actor_id: search.actor,
              customer_id: search.customer,
              action: search.action,
              since: search.from ? dayStart(search.from) : undefined,
              until: search.to ? dayStart(nextDay(search.to)) : undefined,
              page: search.page ?? 1,
              size: AUDIT_PAGE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
