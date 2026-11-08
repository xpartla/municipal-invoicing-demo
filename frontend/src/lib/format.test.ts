import { describe, expect, it } from 'vitest';

import { formatAmount, formatAmountForCopy, formatDate, formatDateTime } from './format';

const NBSP = ' ';

describe('formatAmount', () => {
  it.each([
    [93.71, `93,71${NBSP}€`],
    ['93.71', `93,71${NBSP}€`],
    [93.7, `93,70${NBSP}€`],
    [0, `0,00${NBSP}€`],
    [1234.5, `1${NBSP}234,50${NBSP}€`],
    [1234567.891, `1${NBSP}234${NBSP}567,89${NBSP}€`],
    [-12.3, `-12,30${NBSP}€`],
    [-0.001, `0,00${NBSP}€`],
  ])('%s → %s', (value, expected) => {
    expect(formatAmount(value)).toBe(expected);
  });

  it('leaves the currency out on request', () => {
    expect(formatAmount(1234.5, { currency: false })).toBe(`1${NBSP}234,50`);
  });

  it.each([null, undefined, '', 'abc', Number.NaN, Number.POSITIVE_INFINITY])(
    'is empty for %s',
    (value) => {
      expect(formatAmount(value)).toBe('');
    },
  );
});

describe('formatAmountForCopy', () => {
  it.each([
    [93.71, '93,71'],
    [1234.5, '1234,50'],
    [-5, '-5,00'],
    [null, ''],
  ])('%s → %s', (value, expected) => {
    expect(formatAmountForCopy(value)).toBe(expected);
  });
});

describe('formatDate', () => {
  it.each([
    ['2026-06-11', `11.${NBSP}6.${NBSP}2026`],
    ['2026-12-01', `1.${NBSP}12.${NBSP}2026`],
    ['2026-01-31', `31.${NBSP}1.${NBSP}2026`],
  ])('%s → %s', (value, expected) => {
    expect(formatDate(value)).toBe(expected);
  });

  it('is empty for a missing date and leaves other text alone', () => {
    expect(formatDate(null)).toBe('');
    expect(formatDate('')).toBe('');
    expect(formatDate('11.6.2026')).toBe('11.6.2026');
  });
});

describe('formatDateTime', () => {
  it.each([
    ['2026-06-11T06:05:00Z', `11.${NBSP}6.${NBSP}2026 08:05`], // CEST, UTC+2
    ['2026-06-10T22:30:00Z', `11.${NBSP}6.${NBSP}2026 00:30`], // past midnight in Bratislava
    ['2026-01-10T22:30:00Z', `10.${NBSP}1.${NBSP}2026 23:30`], // CET, UTC+1
    ['2026-01-10T23:00:00+00:00', `11.${NBSP}1.${NBSP}2026 00:00`],
  ])('%s → %s', (value, expected) => {
    expect(formatDateTime(value)).toBe(expected);
  });

  it('is empty for a missing instant and leaves an invalid one alone', () => {
    expect(formatDateTime(undefined)).toBe('');
    expect(formatDateTime('not a date')).toBe('not a date');
  });
});
