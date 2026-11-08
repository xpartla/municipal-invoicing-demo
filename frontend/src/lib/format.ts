/**
 * Shared formatters (guide §6.7): amounts `93,71 €`, dates `11. 6. 2026`, instants in
 * Europe/Bratislava. A non-breaking space keeps an amount or a date on one line.
 */

const NBSP = ' ';
const TIME_ZONE = 'Europe/Bratislava';
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

type AmountInput = number | string | null | undefined;

function toCents(value: AmountInput): string | null {
  if (value === null || value === undefined || value === '') return null;
  const amount = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(amount)) return null;
  const fixed = Math.abs(amount).toFixed(2);
  return amount < 0 && fixed !== '0.00' ? `-${fixed}` : fixed;
}

/** `1234.5` → `1 234,50 €` (the spaces are non-breaking). Empty for a missing amount. */
export function formatAmount(value: AmountInput, options: { currency?: boolean } = {}): string {
  const fixed = toCents(value);
  if (fixed === null) return '';
  const negative = fixed.startsWith('-');
  const [whole = '0', cents = '00'] = fixed.replace('-', '').split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  const number = `${negative ? '-' : ''}${grouped},${cents}`;
  return options.currency === false ? number : `${number}${NBSP}€`;
}

/**
 * The amount as the accountant types it into TOPSET: `1234,50`, no grouping, no currency.
 * The copy buttons use it.
 */
export function formatAmountForCopy(value: AmountInput): string {
  const fixed = toCents(value);
  return fixed === null ? '' : fixed.replace('.', ',');
}

/** An ISO date `2026-06-11` → `11. 6. 2026`. Dates carry no time zone, so none is applied. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '';
  const match = ISO_DATE.exec(value);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${Number(day)}.${NBSP}${Number(month)}.${NBSP}${year ?? ''}`;
}

const instantParts = new Intl.DateTimeFormat('sk-SK', {
  timeZone: TIME_ZONE,
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

/** A UTC instant → its date and time in Bratislava: `11. 6. 2026 08:05`. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '';
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value;
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    instantParts.formatToParts(instant).find((p) => p.type === type)?.value ?? '';
  return `${part('day')}.${NBSP}${part('month')}.${NBSP}${part('year')} ${part('hour')}:${part('minute')}`;
}
