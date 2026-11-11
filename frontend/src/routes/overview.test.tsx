import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { currentMonth } from '../features/reporting/dashboard';
import { mockApi } from '../test/api';
import { BOLDOG, LEHOTA, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Prehľad klientov and Platforma (P2-M7-T04, plan §10.8, §10.9, decision 67): the totals and a
// row per customer opening it; admins choose a provider; the platform's counts with links.

function row(customer: typeof BOLDOG, extra: object = {}) {
  return {
    customer_id: customer.id,
    name: customer.name,
    ico: customer.ico,
    uploaded: 0,
    waiting: 0,
    review: 0,
    failed: 0,
    booked: 0,
    last_activity: null,
    missing_lists: [],
    open_imports: 0,
    ...extra,
  };
}

function overview(month: string, providerId = 'p1', name = 'Účtovníctvo Vzor, s.r.o.') {
  return {
    provider_id: providerId,
    provider_name: name,
    month,
    totals: {
      customers: 2,
      uploaded: 7,
      waiting: 1,
      review: 2,
      failed: 1,
      booked: 4,
      missing_lists: 1,
      open_imports: 1,
    },
    rows: [
      row(BOLDOG, {
        uploaded: 7,
        waiting: 1,
        review: 2,
        failed: 1,
        booked: 4,
        last_activity: '2026-11-10T09:15:00Z',
        open_imports: 1,
      }),
      row(LEHOTA, { missing_lists: ['accounts', 'budget_expense', 'document_series'] }),
    ],
  };
}

describe('Prehľad klientov', () => {
  it('staff land on it: the totals, then a row per customer that opens it', async () => {
    const api = mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/overview': (call) => ({
        body: overview(new URL(call.path, 'http://x').searchParams.get('month') ?? ''),
      }),
    });
    const { router } = await renderApp('/');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/provider');
    });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Prehľad klientov' }),
    ).toBeVisible();
    const totals = await screen.findByRole('list', { name: 'Súčty za všetkých klientov' });
    expect(
      within(totals)
        .getAllByRole('listitem')
        .map((i) => i.textContent),
    ).toEqual([
      'Klienti2',
      'Nahrané7',
      'Čakajú na kontrolu1',
      'Na kontrolu2',
      'Neúspešné1',
      'Zaúčtované4',
      'Bez číselníkov1',
      'Otvorené importy1',
    ]);
    const table = screen.getByRole('region', { name: 'Klienti' });
    const boldog = within(table).getByRole('row', { name: /Obec Boldog/ });
    expect(boldog).toHaveTextContent('10. 11. 2026 10:15');
    expect(within(boldog).getByText('Pripravené')).toBeVisible();
    expect(
      within(boldog).getByRole('link', { name: '1 otvorený import klienta Obec Boldog' }),
    ).toHaveAttribute('href', `/c/${BOLDOG.id}/exchange`);
    const lehota = within(table).getByRole('row', { name: /Obec Vzorová Lehota/ });
    expect(lehota).toHaveTextContent('Účtový rozvrh, Výdavkový rozpočet, Číselné rady dokladov');
    expect(lehota).toHaveTextContent('zatiaľ nič');
    expect(within(table).getByRole('link', { name: 'Obec Boldog' })).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}`,
    );
    expect(
      api.calls.some((c) => c.path === `/api/providers/p1/overview?month=${currentMonth()}`),
    ).toBe(true);
  });

  it('admins choose the provider, kept in the URL with the month', async () => {
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/providers': {
        body: [
          {
            provider: { id: 'p1', name: 'Účtovníctvo Vzor, s.r.o.', ico: null, status: 'active' },
            staff: [],
            customers: [],
          },
          {
            provider: { id: 'p2', name: 'Iná firma, s.r.o.', ico: null, status: 'active' },
            staff: [],
            customers: [],
          },
          {
            provider: { id: 'p3', name: 'Zrušená firma', ico: null, status: 'removed' },
            staff: [],
            customers: [],
          },
        ],
      },
      'GET /api/providers/p1/overview': { body: overview('2026-10') },
      'GET /api/providers/p2/overview': {
        body: { ...overview('2026-10', 'p2', 'Iná firma, s.r.o.'), rows: [] },
      },
    });
    const { router } = await renderApp('/provider?month=2026-10');
    expect(await screen.findByRole('region', { name: 'Klienti' })).toBeVisible();
    await userEvent.click(screen.getByRole('combobox', { name: 'Servisný účet' }));
    expect(screen.queryByRole('option', { name: 'Zrušená firma' })).toBeNull();
    await userEvent.click(screen.getByRole('option', { name: 'Iná firma, s.r.o.' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ month: '2026-10', provider: 'p2' });
    });
    expect(await screen.findByText('Servisný účet zatiaľ nemá klientov.')).toBeVisible();
  });

  it('is not for customer logins', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp('/provider');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Prístup zamietnutý' }),
    ).toBeVisible();
  });
});

describe('Platforma', () => {
  it('admins land on the counts, each leading to its screen', async () => {
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/overview': (call) => ({
        body: {
          month: new URL(call.path, 'http://x').searchParams.get('month'),
          providers: 2,
          customers: 4,
          users: 6,
          invoices: 81,
          ocr_pages: 12,
          failed_jobs: 1,
          logins: 9,
          login_users: 3,
          unsent_mail: 5,
        },
      }),
    });
    const { router } = await renderApp('/');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/admin');
    });
    const counts = await screen.findByRole('list', { name: 'Počty' });
    const link = (name: RegExp) => within(counts).getByRole('link', { name });
    expect(link(/Servisné účty\s*2/)).toHaveAttribute('href', '/admin/providers');
    expect(link(/Neúspešné úlohy\s*1/)).toHaveAttribute('href', '/admin/jobs');
    expect(link(/Prihlásenia za 7 dní\s*9\s*3 používatelia/)).toHaveAttribute(
      'href',
      '/admin/audit',
    );
    expect(link(/Neodoslané e-maily\s*5/)).toHaveAttribute('href', '/admin/outbox');
    expect(within(counts).getByText('81')).toBeVisible();
    expect(within(counts).getByText('12')).toBeVisible();
  });

  it('is not for staff', async () => {
    mockApi({ 'GET /api/me': { body: meAs('staff') } });
    await renderApp('/admin');
    expect(await screen.findByRole('heading', { level: 1 })).not.toHaveTextContent('Platforma');
  });
});
