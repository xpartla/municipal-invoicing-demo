import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { COLUMNS_STORAGE } from '../features/invoices/columns';
import { mockApi, type Call } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Faktúry (P2-M4-T07): the filters kept in the URL and back, sorting, the columns remembered
// per browser, the bulk actions with failures listed, the export dialog with the "already
// exported" notice and its job, and the export history on Importy a exporty.

const base = `/api/customers/${BOLDOG.id}`;

function row(id: string, number: string, state = 'booked', overrides: object = {}) {
  return {
    id,
    state,
    channel: 'dataset',
    source_ref: null,
    needs_review: false,
    series: 'FD',
    document_number: number,
    booking_date: '2026-06-23',
    supplier_name: 'Slovak Telekom, a.s.',
    supplier_ico: '35763469',
    invoice_number: `INV-${id}`,
    variable_symbol: '8390051427',
    issue_date: '2026-06-22',
    due_date: '2026-07-07',
    supply_date: '2026-06-21',
    gross: 93.71,
    currency: 'EUR',
    uploaded_at: '2026-06-23T08:00:00Z',
    uploaded_by: null,
    exported_at: null,
    paid_on: null,
    budget_keys: ['632005 41 01 110 000'],
    md: ['518 003'],
    dal: ['321 000'],
    ...overrides,
  };
}

const ROWS = [row('i1', 'FD/144/26'), row('i2', 'FD/145/26', 'ready')];

function invoicesApi(role: 'user' | 'viewer' = 'user', extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs(role) },
    [`GET ${base}/invoices`]: { body: { items: ROWS, total: ROWS.length } },
    [`GET ${base}/invoices/suppliers`]: {
      body: [{ ico: '35763469', name: 'Slovak Telekom, a.s.', invoices: 2 }],
    },
    [`GET ${base}/number-series`]: {
      body: { year: 2026, items: [{ series: 'FD' }, { series: 'FDŠJ' }] },
    },
    ...extra,
  });
}

/** The query string of the last call to the invoice list. */
function lastList(calls: Call[]): URLSearchParams {
  const found = calls.filter((c) => c.method === 'GET' && c.path.startsWith(`${base}/invoices?`));
  return new URLSearchParams(found.at(-1)?.path.split('?')[1] ?? '');
}

afterEach(() => {
  localStorage.clear();
});

describe('the invoice table', () => {
  // The view's link, as the filters and the sort below write it (the state list as JSON).
  const LINK = `/c/${BOLDOG.id}/invoices?q=telekom&state=%5B%22ready%22%5D&sort=-gross`;

  it('keeps the filters and the sort in the URL', async () => {
    const user = userEvent.setup();
    const { calls } = invoicesApi();
    const { router } = await renderApp(`/c/${BOLDOG.id}/invoices`);
    await screen.findByText('FD/144/26');
    expect(lastList(calls).get('sort')).toBe('-uploaded_at');

    await user.type(screen.getByRole('textbox', { name: 'Hľadať' }), 'telekom');
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ q: 'telekom' });
    });
    await user.click(screen.getByLabelText('Stav', { selector: 'input' }));
    await user.click(await screen.findByRole('option', { name: 'Pripravená' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ q: 'telekom', state: ['ready'] });
    });
    await user.click(screen.getByRole('button', { name: 'Zoradiť podľa: Suma' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ sort: 'gross' });
    });
    await user.click(screen.getByRole('button', { name: 'Zoradiť podľa: Suma' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ sort: '-gross' });
    });
    const query = lastList(calls);
    expect(query.get('q')).toBe('telekom');
    expect(query.getAll('state')).toEqual(['ready']);
    expect(query.get('sort')).toBe('-gross');
    expect(router.state.location.href).toBe(LINK);
  });

  it('opens the same view from its link', async () => {
    const { calls } = invoicesApi();
    await renderApp(LINK);
    await screen.findByText('FD/144/26');
    expect(screen.getByRole('textbox', { name: 'Hľadať' })).toHaveValue('telekom');
    expect(screen.getByText('Aktívne filtre: 2')).toBeInTheDocument();
    const read = lastList(calls);
    expect(read.get('q')).toBe('telekom');
    expect(read.getAll('state')).toEqual(['ready']);
    expect(read.get('sort')).toBe('-gross');
    expect(screen.getByRole('columnheader', { name: 'Suma' })).toHaveAttribute(
      'aria-sort',
      'descending',
    );
  });

  it('filters by a supplier picked from the suggestions and clears the filters', async () => {
    const user = userEvent.setup();
    const { calls } = invoicesApi();
    const { router } = await renderApp(`/c/${BOLDOG.id}/invoices?budget=632&mine=true`);
    await screen.findByText('FD/144/26');
    expect(lastList(calls).get('uploaded_by')).toBe('u-user');
    expect(screen.getByRole('textbox', { name: 'Položka alebo EK' })).toHaveValue('632');
    await user.type(screen.getByLabelText('Dodávateľ', { selector: 'input' }), 'telek');
    await user.click(
      await screen.findByRole('option', { name: 'Slovak Telekom, a.s. (35763469)' }),
    );
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({
        supplier_ico: '35763469',
        supplier: 'Slovak Telekom, a.s.',
      });
    });
    expect(lastList(calls).get('supplier_ico')).toBe('35763469');
    expect(lastList(calls).get('supplier')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Zrušiť filtre' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({});
    });
    expect(screen.getByRole('textbox', { name: 'Položka alebo EK' })).toHaveValue('');
  });

  it('remembers the chosen columns in this browser', async () => {
    const user = userEvent.setup();
    invoicesApi();
    const { unmount } = await renderApp(`/c/${BOLDOG.id}/invoices`);
    await screen.findByText('FD/144/26');
    const table = screen.getByRole('region', { name: 'Tabuľka faktúr' });
    expect(within(table).getByRole('columnheader', { name: 'Rozpočtová položka' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Stĺpce' }));
    await user.click(await screen.findByRole('checkbox', { name: 'Rozpočtová položka' }));
    await user.click(screen.getByRole('checkbox', { name: 'VS' }));
    expect(within(table).queryByRole('columnheader', { name: 'Rozpočtová položka' })).toBeNull();
    expect(within(table).getByRole('columnheader', { name: 'VS' })).toBeVisible();
    expect(JSON.parse(localStorage.getItem(COLUMNS_STORAGE) ?? '[]')).toContain('vs');
    unmount();
    invoicesApi();
    await renderApp(`/c/${BOLDOG.id}/invoices`);
    await screen.findByText('FD/144/26');
    expect(screen.queryByRole('columnheader', { name: 'Rozpočtová položka' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: 'VS' })).toBeVisible();
  });

  it('marks the selected invoices paid and lists those that failed', async () => {
    const user = userEvent.setup();
    const { calls } = invoicesApi('user', {
      [`POST ${base}/invoices/bulk/pay`]: {
        body: {
          results: [
            { invoice_id: 'i1', ok: true, code: null, message: null },
            { invoice_id: 'i2', ok: false, code: 'invalid_state', message: 'invoice i2 is ready' },
          ],
          done: 1,
          failed: 1,
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices`);
    await screen.findByText('FD/144/26');
    await user.click(screen.getByRole('checkbox', { name: 'Vybrať všetky faktúry na strane' }));
    expect(screen.getByText('Vybrané: 2')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Označiť ako uhradené' }));
    const dialog = await screen.findByRole('dialog', { name: 'Označiť ako uhradené' });
    const date = within(dialog).getByLabelText(/Dátum úhrady/);
    await user.clear(date);
    await user.type(date, '2026-07-02');
    await user.click(within(dialog).getByRole('button', { name: 'Označiť ako uhradené' }));
    const failures = await screen.findByRole('dialog', {
      name: 'Tieto faktúry sa nepodarilo spracovať',
    });
    expect(failures).toHaveTextContent('FD/145/26: V tomto stave sa to s faktúrou nedá.');
    const pay = calls.find((c) => c.path === `${base}/invoices/bulk/pay`);
    expect(pay?.body).toEqual({ invoice_ids: ['i1', 'i2'], paid_on: '2026-07-02' });
    expect(screen.queryByText('Vybrané: 2')).toBeNull();
  });

  it('exports the filtered invoices, saying which were exported before', async () => {
    const user = userEvent.setup();
    let polls = 0;
    const run = (state: string) => ({
      id: 'e1',
      format: 'xlsx',
      state,
      scope: { filter: { state: ['booked'] }, sort: '-gross' },
      requested: 2,
      invoices: state === 'done' ? 2 : 0,
      rows: 3,
      again: 1,
      skipped: 0,
      file_name: state === 'done' ? 'faktury-2026-07-01-1000.xlsx' : null,
      file_size: 100,
      error: null,
      job_id: 'j1',
      created_at: '2026-07-01T08:00:00Z',
      created_by: 'u-user',
      updated_at: '2026-07-01T08:00:00Z',
    });
    const { calls } = invoicesApi('user', {
      [`POST ${base}/exports/preview`]: { body: { invoices: 2, again: 1, skipped: 0 } },
      [`POST ${base}/exports`]: { status: 202, body: run('queued') },
      [`GET ${base}/exports/e1`]: () => ({ body: run(++polls > 1 ? 'done' : 'queued') }),
      [`GET ${base}/exports`]: { body: { items: [run('done')], total: 1 } },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices?state=%5B%22booked%22%5D&sort=-gross`);
    await screen.findByText('FD/144/26');
    await user.click(screen.getByRole('button', { name: 'Exportovať' }));
    const dialog = await screen.findByRole('dialog', { name: 'Export faktúr' });
    expect(await within(dialog).findByText('Zaúčtované faktúry do exportu: 2')).toBeVisible();
    expect(within(dialog).getByText('Už exportované, export sa zopakuje: 1')).toBeVisible();
    await user.click(within(dialog).getByRole('radio', { name: 'XLSX' }));
    await user.click(within(dialog).getByRole('button', { name: 'Exportovať' }));
    const download = await within(dialog).findByRole(
      'link',
      { name: 'Stiahnuť faktury-2026-07-01-1000.xlsx' },
      { timeout: 4000 },
    );
    expect(download).toHaveAttribute('href', `${base}/exports/e1/file`);
    const started = calls.find((c) => c.method === 'POST' && c.path === `${base}/exports`);
    expect(started?.body).toEqual({
      format: 'xlsx',
      filter: { state: ['booked'] },
      sort: '-gross',
    });
  });

  it('shows the viewer the invoices without actions', async () => {
    invoicesApi('viewer');
    await renderApp(`/c/${BOLDOG.id}/invoices`);
    await screen.findByText('FD/144/26');
    expect(screen.queryByRole('checkbox', { name: /Vybrať/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Exportovať' })).toBeNull();
    expect(screen.getByText('Počet: 2')).toBeInTheDocument();
  });
});

describe('the export history', () => {
  it('lists the exports with their files on Importy a exporty', async () => {
    mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}/imports`]: { body: { items: [], total: 0 } },
      [`GET ${base}/templates`]: { body: { items: [] } },
      [`GET ${base}/exports`]: {
        body: {
          items: [
            {
              id: 'e1',
              format: 'csv',
              state: 'done',
              scope: { invoice_ids: ['i1', 'i2'] },
              requested: 2,
              invoices: 2,
              rows: 3,
              again: 1,
              skipped: 0,
              file_name: 'faktury-2026-07-01-1000.csv',
              file_size: 300,
              error: null,
              job_id: 'j1',
              created_at: '2026-07-01T08:00:00Z',
              created_by: 'u-user',
              updated_at: '2026-07-01T08:00:01Z',
            },
          ],
          total: 1,
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/exchange`);
    const link = await screen.findByRole('link', {
      name: 'Stiahnuť export faktury-2026-07-01-1000.csv',
    });
    expect(link).toHaveAttribute('href', `${base}/exports/e1/file`);
    const row = link.closest('tr');
    expect(row).toHaveTextContent('Výber faktúr');
    expect(row).toHaveTextContent('z toho opakovane: 1');
    expect(row).toHaveTextContent('Hotovo');
  });
});
