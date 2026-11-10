import { describe, expect, it } from 'vitest';

import { activeFilters, apiQuery, exportFilter, invoicesSearch, nextSort } from './search';

// The invoice table's URL state (P2-M4-T07): what a link may carry, and what the API gets.

describe('invoicesSearch', () => {
  it('keeps the known filters and drops what a hand-edited link got wrong', () => {
    expect(
      invoicesSearch({
        q: '  telekom ',
        state: ['ready', 'nonsense', 'ready'],
        channel: 'dataset',
        series: ['FD', 'FDŠJ'],
        supplier_ico: '35763469',
        supplier: 'Slovak Telekom, a.s.',
        needs_review: 'false',
        mine: true,
        issue_from: '2026-06-01',
        issue_to: '1.6.2026',
        amount_min: '100,5',
        amount_max: 'lots',
        budget: '632',
        sort: '-gross',
        page: 3,
      }),
    ).toEqual({
      q: 'telekom',
      state: ['ready'],
      channel: ['dataset'],
      series: ['FD', 'FDŠJ'],
      supplier_ico: '35763469',
      supplier: 'Slovak Telekom, a.s.',
      needs_review: false,
      mine: true,
      issue_from: '2026-06-01',
      amount_min: '100.5',
      budget: '632',
      sort: '-gross',
      page: 3,
    });
    expect(invoicesSearch({ sort: '-password', page: 1, supplier_ico: '123', q: '' })).toEqual({});
  });
});

describe('apiQuery and exportFilter', () => {
  const search = invoicesSearch({
    q: 'zse',
    supplier: 'ZSE',
    supplier_ico: '36677281',
    mine: true,
    state: ['booked'],
    sort: 'booking_date',
    page: 2,
  });

  it('gives the API the filters, the caller for "mine", the sort and the page', () => {
    expect(apiQuery(search, 'u-jana', 50)).toEqual({
      q: 'zse',
      supplier_ico: '36677281',
      state: ['booked'],
      uploaded_by: 'u-jana',
      sort: 'booking_date',
      page: 2,
      size: 50,
    });
    expect(apiQuery({}, 'u-jana', 50)).toEqual({
      sort: '-uploaded_at',
      page: 1,
      size: 50,
      uploaded_by: undefined,
    });
  });

  it('gives an export the filters only', () => {
    expect(exportFilter(search, 'u-jana')).toEqual({
      q: 'zse',
      supplier_ico: '36677281',
      state: ['booked'],
      uploaded_by: 'u-jana',
    });
    expect(activeFilters(search)).toBe(4);
  });
});

describe('nextSort', () => {
  it('sorts by a column ascending, then descending', () => {
    expect(nextSort(undefined, 'gross')).toBe('gross');
    expect(nextSort('gross', 'gross')).toBe('-gross');
    expect(nextSort('-gross', 'gross')).toBe('gross');
    expect(nextSort('-gross', 'supplier_name')).toBe('supplier_name');
  });
});
