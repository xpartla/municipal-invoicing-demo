import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Úložisko (P2-M5-T11, plan §10.7): the customer's files by kind with their size, what uses
// them and the download, the totals by kind and in all, the kind filter and the page in the
// URL.

const base = `/api/customers/${BOLDOG.id}`;

function file(kind: string, id: string, name: string, size: number, extra: object = {}) {
  return {
    kind,
    id,
    name,
    media_type: 'application/pdf',
    size,
    created_at: '2026-06-23T08:15:00Z',
    created_by: 'u-user',
    invoice_id: null,
    detail: null,
    ...extra,
  };
}

const ITEMS = [
  file('document', 'doc-1', 'telekom-jun.jpg', 812_345, {
    media_type: 'image/jpeg',
    invoice_id: 'inv-1',
  }),
  file('document', 'doc-2', 'zse.pdf', 2_400, {}),
  file('import', 'run-1', 'rozpocet-2026.xlsx', 48_000, { detail: 'budget_expense' }),
  file('export', 'run-2', 'faktury-2026-06.csv', 1_536, { detail: '12', media_type: 'text/csv' }),
];

const KINDS = {
  document: { count: 2, size: 814_745 },
  import: { count: 1, size: 48_000 },
  export: { count: 1, size: 1_536 },
};

describe('Úložisko', () => {
  it('lists the files with their size, what uses them and the download, and the totals', async () => {
    mockApi({
      'GET /api/me': { body: meAs('viewer') },
      [`GET ${base}/files`]: {
        body: { items: ITEMS, total: 4, size: 864_281, kinds: KINDS },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/files`);
    expect(await screen.findByRole('heading', { level: 1, name: 'Úložisko' })).toBeVisible();

    const totals = screen.getByRole('list', { name: 'Súčty podľa druhu' });
    const total = (name: string) =>
      within(totals)
        .getAllByRole('listitem')
        .find((item) => within(item).queryByText(name) !== null);
    expect(total('Všetko')).toHaveTextContent('844,0 kB');
    expect(total('Všetko')).toHaveTextContent('4 súbory');
    expect(total('Doklady')).toHaveTextContent('795,6 kB');
    expect(total('Doklady')).toHaveTextContent('2 súbory');
    expect(total('Importy')).toHaveTextContent('1 súbor');

    const table = screen.getByRole('table', { name: 'Súbory' });
    const row = (name: string) => within(table).getByRole('row', { name: new RegExp(name) });
    expect(
      within(row('telekom-jun.jpg')).getByRole('link', { name: 'Stiahnuť telekom-jun.jpg' }),
    ).toHaveAttribute('href', `${base}/documents/doc-1/file`);
    expect(within(row('telekom-jun.jpg')).getByText('793,3 kB')).toBeVisible();
    expect(within(row('telekom-jun.jpg')).getByRole('link', { name: 'Faktúra' })).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices/inv-1`,
    );
    expect(within(row('zse.pdf')).getByText('2,3 kB')).toBeVisible();
    expect(within(row('zse.pdf')).getByText('Nepoužíva sa')).toBeVisible();
    expect(
      within(row('rozpocet-2026.xlsx')).getByRole('link', { name: 'Stiahnuť rozpocet-2026.xlsx' }),
    ).toHaveAttribute('href', `${base}/imports/run-1/file`);
    expect(within(row('rozpocet-2026.xlsx')).getByText('Import: Výdavkový rozpočet')).toBeVisible();
    expect(
      within(row('faktury-2026-06.csv')).getByRole('link', {
        name: 'Stiahnuť faktury-2026-06.csv',
      }),
    ).toHaveAttribute('href', `${base}/exports/run-2/file`);
    expect(within(row('faktury-2026-06.csv')).getByText('Export: 12 faktúr')).toBeVisible();
    expect(within(row('faktury-2026-06.csv')).getByText('1,5 kB')).toBeVisible();
  });

  it('filters by kind and pages, keeping both in the URL', async () => {
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}/files`]: (call) => ({
        body: {
          items: call.path.includes('kind=import') ? [ITEMS[2]] : ITEMS,
          total: call.path.includes('kind=import') ? 1 : 120,
          size: 864_281,
          kinds: KINDS,
        },
      }),
    });
    const user = userEvent.setup();
    const { router } = await renderApp(`/c/${BOLDOG.id}/files`);
    await screen.findByRole('table', { name: 'Súbory' });
    await user.click(screen.getByRole('button', { name: 'Ďalšie' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ page: 2 });
    });
    expect(calls.at(-1)?.path).toContain('page=2');

    await user.click(screen.getByRole('radio', { name: 'Importy' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ kind: 'import' });
    });
    const last = calls.filter((c) => c.path.startsWith(`${base}/files`)).at(-1)?.path ?? '';
    expect(last).toContain('kind=import');
    expect(last).toContain('page=1');
    const table = await screen.findByRole('table', { name: 'Súbory' });
    await waitFor(() => {
      expect(within(table).getAllByRole('row')).toHaveLength(2);
    });
  });

  it('says when there are no files', async () => {
    mockApi({
      'GET /api/me': { body: meAs('viewer') },
      [`GET ${base}/files`]: {
        body: {
          items: [],
          total: 0,
          size: 0,
          kinds: {
            document: { count: 0, size: 0 },
            import: { count: 0, size: 0 },
            export: { count: 0, size: 0 },
          },
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/files`);
    expect(await screen.findByText('Klient zatiaľ nemá žiadne súbory.')).toBeVisible();
  });
});
