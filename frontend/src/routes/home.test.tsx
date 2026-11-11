import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { currentMonth, monthDays, shiftMonth } from '../features/reporting/dashboard';
import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Domov (P2-M7-T03, plan §10.2, decision 67): the month picker, the tiles linking to the
// filtered invoice table, the charts with their text alternatives, the attention list, the
// number series and the onboarding checklist.

const base = `/api/customers/${BOLDOG.id}`;

function days(month: string, booked: Record<string, [number, number]>) {
  const { last } = monthDays(month);
  return Array.from({ length: Number(last.slice(8)) }, (_, n) => {
    const day = `${month}-${String(n + 1).padStart(2, '0')}`;
    const [count, total] = booked[day] ?? [0, 0];
    return { day, count, total };
  });
}

function dashboard(month: string, extra: object = {}) {
  return {
    month,
    tiles: {
      uploaded: 7,
      waiting: 1,
      review: 2,
      failed: 1,
      booked: 4,
      booked_total: 226.82,
    },
    per_day: days(month, {
      [`${month}-05`]: [1, 93.71],
      [`${month}-06`]: [2, 44.47],
      [`${month}-20`]: [1, 88.64],
    }),
    by_type: [
      { series: 'FD', credit_note: false, count: 2, total: 183.12 },
      { series: 'FD', credit_note: true, count: 1, total: -44.94 },
      { series: 'FDŠJ', credit_note: false, count: 1, total: 88.64 },
    ],
    suppliers_by_count: [
      { ico: '35763469', name: 'Slovak Telekom, a.s.', count: 2, total: 183.12 },
      { ico: '36283576', name: 'PENAM SLOVAKIA, a.s.', count: 1, total: 88.64 },
    ],
    suppliers_by_amount: [
      { ico: '35763469', name: 'Slovak Telekom, a.s.', count: 2, total: 183.12 },
      { ico: '36283576', name: 'PENAM SLOVAKIA, a.s.', count: 1, total: 88.64 },
    ],
    units: [
      {
        function: '01 110',
        code: '01.1.1',
        name: 'Výkonné a zákonodarné orgány',
        invoices: 3,
        total: 138.18,
      },
    ],
    months: Array.from({ length: 12 }, (_, n) => ({
      month: shiftMonth(month, n - 11),
      count: n === 11 ? 4 : 0,
      total: n === 11 ? 226.82 : 0,
    })),
    review: { booked: 4, reviewed: 1, rate: 0.25, median_seconds: 949_470 },
    budget: null,
    attention: {
      failed: [
        {
          id: 'inv-failed',
          state: 'extraction_failed',
          supplier_name: null,
          source_ref: 'sken-12.jpg',
          uploaded_at: '2026-11-12T09:00:00Z',
        },
      ],
      failed_total: 1,
      waiting: [
        {
          id: 'inv-old',
          state: 'needs_review',
          supplier_name: 'ZSE Energia, a.s.',
          source_ref: null,
          uploaded_at: '2026-01-01T07:00:00Z',
        },
      ],
      waiting_total: 78,
      warnings: [],
    },
    onboarding: {
      year: 2026,
      profile: false,
      codelists: true,
      health: true,
      first_booked: true,
      done: false,
    },
    ...extra,
  };
}

const SERIES = {
  year: 2026,
  items: [
    {
      series: 'FD',
      year: 2026,
      pattern: 'FD/XXX/RR',
      last_used: 147,
      last_used_number: 'FD/147/26',
      next_number: 'FD/148/26',
      used: [],
      gaps: ['FD/145/26', 'FD/146/26'],
      stored: true,
    },
  ],
};

function routes(answer: (month: string) => object = (m) => dashboard(m)) {
  return {
    'GET /api/me': { body: meAs('viewer') },
    [`GET ${base}/dashboard`]: (call: { path: string }) => {
      const month = new URL(call.path, 'http://x').searchParams.get('month') ?? currentMonth();
      return { body: answer(month) };
    },
    [`GET ${base}/number-series`]: { body: SERIES },
  };
}

describe('Domov', () => {
  it('shows the tiles of the current month, each linking to the filtered invoice table', async () => {
    const api = mockApi(routes());
    await renderApp(`/c/${BOLDOG.id}`);
    const tiles = await screen.findByRole('list', { name: 'Ukazovatele mesiaca' });
    const month = currentMonth();
    const { first, last } = monthDays(month);
    const link = (name: RegExp) => within(tiles).getByRole('link', { name });
    expect(link(/Nahrané\s*7/)).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices?uploaded_from=${first}&uploaded_to=${last}`,
    );
    expect(link(/Na kontrolu\s*2/).getAttribute('href')).toContain(
      'state=%5B%22needs_review%22%5D',
    );
    expect(link(/Neúspešné\s*1/).getAttribute('href')).toContain('extraction_failed');
    expect(link(/Zaúčtované\s*4/)).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices?booked_from=${first}&booked_to=${last}`,
    );
    expect(link(/Suma zaúčtovaných\s*226,82/)).toBeVisible();
    expect(api.calls.some((c) => c.path === `${base}/dashboard?month=${month}`)).toBe(true);
  });

  it('moves between months and keeps the month in the URL', async () => {
    const api = mockApi(routes());
    const { router } = await renderApp(`/c/${BOLDOG.id}?month=2026-03`);
    expect(await screen.findByRole('combobox', { name: 'Mesiac' })).toHaveValue('marec 2026');
    await userEvent.click(
      screen.getByRole('button', { name: 'Predchádzajúci mesiac: február 2026' }),
    );
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ month: '2026-02' });
    });
    expect(api.calls.some((c) => c.path === `${base}/dashboard?month=2026-02`)).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: 'Nasledujúci mesiac: marec 2026' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ month: '2026-03' });
    });
  });

  it('cannot go past the current month', async () => {
    mockApi(routes());
    await renderApp(`/c/${BOLDOG.id}`);
    const next = await screen.findByRole('button', { name: /^Nasledujúci mesiac/ });
    expect(next).toBeDisabled();
  });

  it('gives each chart a summary and a table view', async () => {
    mockApi(routes());
    await renderApp(`/c/${BOLDOG.id}?month=2026-11`);
    const perDay = await screen.findByRole('region', { name: 'Zaúčtované podľa dní' });
    expect(within(perDay).getByText('Spolu 4 faktúry; najviac 2 dňa 6. 11. 2026.')).toBeVisible();
    await userEvent.click(within(perDay).getByRole('radio', { name: 'Tabuľka' }));
    const table = within(perDay).getByRole('table');
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(4); // the header and the three days with bookings
    expect(rows[2]).toHaveTextContent('6. 11. 2026');
    expect(rows[2]).toHaveTextContent('44,47 €');

    const months = screen.getByRole('region', { name: 'Zaúčtované za 12 mesiacov' });
    expect(
      within(months).getByText(/december 2025 – november 2026: 4 faktúry za 226,82 €/),
    ).toBeVisible();
    await userEvent.click(within(months).getByRole('radio', { name: 'Tabuľka' }));
    expect(within(within(months).getByRole('table')).getAllByRole('row')).toHaveLength(13);
  });

  it('shows the tables: by type, suppliers, units, review', async () => {
    mockApi(routes());
    await renderApp(`/c/${BOLDOG.id}?month=2026-11`);
    const byType = await screen.findByRole('region', { name: 'Podľa druhu' });
    expect(
      within(byType).getByRole('row', { name: /FD\s*Dobropis\s*1\s*-44,94\s€/ }),
    ).toBeVisible();
    const suppliers = screen.getByRole('region', { name: 'Najčastejší dodávatelia' });
    expect(
      within(suppliers).getByRole('row', { name: /Slovak Telekom.*2\s*183,12\s€/ }),
    ).toBeVisible();
    expect(screen.getByRole('region', { name: 'Dodávatelia s najvyššou sumou' })).toBeVisible();
    const units = screen.getByRole('region', { name: 'Podľa útvaru (funkcie)' });
    expect(within(units).getByRole('row', { name: /01\.1\.1\s*Výkonné/ })).toBeVisible();
    const review = screen.getByRole('region', { name: 'Kontrola a čas' });
    expect(within(review).getByText('25 %')).toBeVisible();
    expect(within(review).getByText('1 z 4 zaúčtovaných')).toBeVisible();
    expect(within(review).getByText('10 d 23 h')).toBeVisible();
  });

  it('lists what needs attention, with links', async () => {
    mockApi(routes());
    await renderApp(`/c/${BOLDOG.id}?month=2026-11`);
    const attention = await screen.findByRole('region', { name: 'Vyžaduje pozornosť' });
    expect(within(attention).getByRole('link', { name: 'sken-12.jpg' })).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices/inv-failed`,
    );
    expect(within(attention).getByText('Čakajú najdlhšie (78)')).toBeVisible();
    expect(within(attention).getByRole('link', { name: 'ZSE Energia, a.s.' })).toBeVisible();
    expect(
      within(attention).getByRole('link', { name: 'Všetky čakajúce faktúry' }).getAttribute('href'),
    ).toContain('sort=uploaded_at');
  });

  it('warns about missing code lists', async () => {
    mockApi(
      routes((m) =>
        dashboard(m, {
          attention: {
            failed: [],
            failed_total: 0,
            waiting: [],
            waiting_total: 0,
            warnings: [{ code: 'list_missing', subject: 'accounts', kind: 'accounts' }],
          },
        }),
      ),
    );
    await renderApp(`/c/${BOLDOG.id}?month=2026-11`);
    const attention = await screen.findByRole('region', { name: 'Vyžaduje pozornosť' });
    expect(
      within(attention).getByRole('link', { name: 'Chýba číselník Účtový rozvrh' }),
    ).toHaveAttribute('href', `/c/${BOLDOG.id}/codelists`);
  });

  it('shows the number series and the onboarding checklist until it is done', async () => {
    mockApi(routes());
    await renderApp(`/c/${BOLDOG.id}?month=2026-11`);
    const series = await screen.findByRole('region', { name: 'Číselné rady 2026' });
    expect(
      await within(series).findByRole('row', { name: /FD\s*FD\/147\/26\s*FD\/148\/26\s*2/ }),
    ).toBeVisible();
    const checklist = screen.getByRole('region', { name: 'Začíname' });
    expect(within(checklist).getByText('Hotové 3 zo 4 krokov.')).toBeVisible();
    expect(
      within(checklist).getByRole('link', { name: 'Doplňte adresu a bankový účet obce' }),
    ).toHaveAttribute('href', '/profile');
  });

  it('hides the checklist once it is done and shows the drawdown when the budget has amounts', async () => {
    mockApi(
      routes((m) =>
        dashboard(m, {
          onboarding: {
            year: 2026,
            profile: true,
            codelists: true,
            health: true,
            first_booked: true,
            done: true,
          },
          budget: {
            year: 2026,
            rows: [
              {
                key: '632001 41 01 110 001',
                description: 'Elektrická energia',
                budgeted: 1500.5,
                drawn: 375.13,
                share: 0.25,
              },
            ],
            budgeted: 1500.5,
            drawn: 375.13,
            elsewhere: 12,
          },
        }),
      ),
    );
    await renderApp(`/c/${BOLDOG.id}?month=2026-11`);
    const budget = await screen.findByRole('region', { name: 'Čerpanie rozpočtu 2026' });
    expect(screen.queryByRole('region', { name: 'Začíname' })).toBeNull();
    expect(
      within(budget).getByRole('row', {
        name: /632001 41 01 110 001.*1\s500,50\s€.*375,13\s€.*25\s%/,
      }),
    ).toBeVisible();
    expect(within(budget).getByText(/Mimo rozpočtovaných položiek 12,00 €/)).toBeVisible();
  });
});
