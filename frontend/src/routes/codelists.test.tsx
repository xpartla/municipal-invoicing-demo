import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Číselníky and Globálne číselníky (P2-M2-T08): the tabs and their columns, the search, the
// row dialog with the API's 422 and 409, the history with the difference, and the admin's
// checklist.

const base = `/api/customers/${BOLDOG.id}/codelists`;

function version(id: string, number: number, kind: string, status = 'active') {
  return {
    id,
    kind,
    year: 2026,
    number,
    status,
    origin: number === 1 ? 'seed' : 'edit',
    created_at: '2026-01-01T07:00:00Z',
    created_by: null,
    entry_count: 2,
    period: '2026-08',
    note: null,
  };
}

const KINDS = [
  'accounts',
  'budget_expense',
  'budget_income',
  'document_series',
  'transfers',
  'cost_centres',
];

const overview = {
  year: 2026,
  years: [2026],
  lists: KINDS.map((kind) => ({
    kind,
    fields: [],
    version:
      kind === 'cost_centres' ? null : version(`v-${kind}`, kind === 'accounts' ? 2 : 1, kind),
  })),
};

const position = (analytika: string, description: string, active = true) => ({
  key: `632005 41 01 110 ${analytika}`,
  active,
  values: {
    ek: '632005',
    zdroj: '41',
    oddiel: '01',
    trieda: '110',
    analytika,
    description,
    aliases: [],
    rows: [7],
    approved: null,
    adjusted: null,
    active,
  },
});

const expense = {
  version: version('v-budget_expense', 1, 'budget_expense'),
  items: [position('000', 'telefon,fax'), position('001', 'starý telefón', false)],
  total: 2,
};

function codelistsApi(role: 'viewer' | 'user', extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs(role) },
    [`GET ${base}`]: { body: overview },
    [`GET ${base}/budget_expense/entries`]: { body: expense },
    [`GET ${base}/budget_expense/versions`]: { body: [expense.version] },
    ...extra,
  });
}

describe('Číselníky', () => {
  it('shows the expense budget with the key parts as columns and inactive rows marked', async () => {
    codelistsApi('user');
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    const table = await screen.findByRole('region', { name: 'Výdavkový rozpočet' });
    for (const column of ['EK', 'Zdroj', 'Oddiel', 'Trieda', 'Analytika', 'Popis']) {
      expect(within(table).getByRole('columnheader', { name: column })).toBeInTheDocument();
    }
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    const [, , inactive] = rows;
    expect(inactive && within(inactive).getByText('neaktívny')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Účtový rozvrh' })).toBeInTheDocument();
    expect(screen.getByText(/Kľúč položky tvorí ekonomická klasifikácia/)).toBeInTheDocument();
  });

  it('searches with the typed text', async () => {
    const user = userEvent.setup();
    const { calls } = codelistsApi('user');
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.type(await screen.findByLabelText('Hľadať'), 'telefón');
    await waitFor(() => {
      expect(calls.some((c) => c.path.includes('q=telef%C3%B3n'))).toBe(true);
    });
  });

  it('edits a row against the active version and lands a 422 on its field', async () => {
    const user = userEvent.setup();
    const key = encodeURIComponent('632005 41 01 110 000');
    const { calls } = codelistsApi('user', {
      [`PUT ${base}/budget_expense/entries/${key}`]: {
        status: 422,
        body: {
          detail: [{ loc: ['body', 'values', 'ek'], msg: 'x', type: 'string_pattern_mismatch' }],
          code: 'validation_failed',
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.click(await screen.findByRole('button', { name: 'Akcie: 632005 41 01 110 000' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Upraviť' }));
    const dialog = await screen.findByRole('dialog');
    const description = within(dialog).getByLabelText('Popis');
    expect(description).toHaveValue('telefon,fax');
    await user.clear(description);
    await user.type(description, 'telefón a fax');
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    await waitFor(() => {
      expect(within(dialog).getByText('Nesprávny tvar kódu.')).toBeInTheDocument();
    });
    const put = calls.find((c) => c.method === 'PUT');
    expect(put?.body).toMatchObject({
      version_id: 'v-budget_expense',
      values: { ek: '632005', description: 'telefón a fax', approved: null },
    });
  });

  it('says so when someone else edited the list first', async () => {
    const user = userEvent.setup();
    codelistsApi('user', {
      [`POST ${base}/budget_expense/entries`]: {
        status: 409,
        body: { detail: 'stale', code: 'conflict' },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.click(await screen.findByRole('button', { name: 'Pridať riadok' }));
    const dialog = await screen.findByRole('dialog');
    for (const [label, value] of [
      ['EK', '632005'],
      ['Zdroj', '41'],
      ['Oddiel', '01'],
      ['Trieda', '110'],
      ['Analytika', '002'],
    ] as const) {
      await user.type(within(dialog).getByLabelText(new RegExp(`^${label}`)), value);
    }
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Medzitým niekto číselník zmenil',
    );
  });

  it('checks the code parts before sending', async () => {
    const user = userEvent.setup();
    const { calls } = codelistsApi('user');
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.click(await screen.findByRole('button', { name: 'Pridať riadok' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^EK/), '6320');
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    expect(await within(dialog).findByText('Presne 6 číslic.')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('deactivates a row', async () => {
    const user = userEvent.setup();
    const key = encodeURIComponent('632005 41 01 110 000');
    const { calls } = codelistsApi('user', {
      [`POST ${base}/budget_expense/entries/${key}/deactivate`]: {
        body: version('v2', 2, 'budget_expense'),
      },
    });
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.click(await screen.findByRole('button', { name: 'Akcie: 632005 41 01 110 000' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Deaktivovať' }));
    await waitFor(() => {
      expect(calls.find((c) => c.path.includes('/deactivate'))?.body).toEqual({
        version_id: 'v-budget_expense',
      });
    });
  });

  it('gives a viewer no editing', async () => {
    codelistsApi('viewer');
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await screen.findByRole('region', { name: 'Výdavkový rozpočet' });
    expect(screen.queryByRole('button', { name: 'Pridať riadok' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Akcie:/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verzie a zmeny' })).toBeInTheDocument();
  });

  it('shows the history and what a version changed', async () => {
    const user = userEvent.setup();
    const old = { ...version('v-a1', 1, 'accounts', 'superseded') };
    const current = version('v-accounts', 2, 'accounts');
    const account = (description: string) => ({
      key: '518 003',
      active: true,
      values: { su: '518', au: '003', type: 'cost', description, activity: null, row: 12 },
    });
    codelistsApi('user', {
      [`GET ${base}/accounts/entries`]: {
        body: { version: current, items: [account('Telekom')], total: 1 },
      },
      [`GET ${base}/accounts/versions`]: { body: [current, old] },
      [`GET ${base}/accounts/diff`]: {
        body: {
          old,
          new: current,
          added: [],
          removed: [],
          changed: [{ key: '518 003', before: account('Pošta'), after: account('Telekom') }],
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.click(await screen.findByRole('tab', { name: 'Účtový rozvrh' }));
    await screen.findByRole('region', { name: 'Účtový rozvrh' });
    await user.click(screen.getByRole('button', { name: 'Verzie a zmeny' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(await within(dialog).findByRole('button', { name: 'Zmeny 1 → 2' }));
    const changes = await within(dialog).findByRole('region', { name: 'Zmeny z verzie 1 na 2' });
    expect(await within(changes).findByText('Popis: Pošta → Telekom')).toBeInTheDocument();
  });

  it('offers to start a list the year does not have', async () => {
    const user = userEvent.setup();
    codelistsApi('user');
    await renderApp(`/c/${BOLDOG.id}/codelists`);
    await user.click(await screen.findByRole('tab', { name: 'Strediská' }));
    expect(await screen.findByText(/tento číselník ešte nie je/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pridať riadok' })).toBeInTheDocument();
  });
});

describe('Globálne číselníky', () => {
  it('shows which global lists each year has, and a list to read', async () => {
    const lists = (year: number, present: boolean) =>
      ['ek', 'cofog', 'funding_sources', 'framework_accounts'].map((kind) => ({
        kind,
        fields: ['code', 'name', 'active'],
        version: present ? { ...version(`g-${kind}`, 1, kind), year, entry_count: 691 } : null,
      }));
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/codelists': {
        body: [
          { year: 2026, complete: true, lists: lists(2026, true) },
          { year: 2027, complete: false, lists: lists(2027, false) },
        ],
      },
      'GET /api/admin/codelists/ek/entries': {
        body: {
          version: version('g-ek', 1, 'ek'),
          items: [
            {
              key: '632005',
              active: true,
              values: { code: '632005', name: 'Telekomunikačné služby' },
            },
          ],
          total: 1,
        },
      },
    });
    await renderApp('/admin/codelists');
    const checklist = await screen.findByRole('region', {
      name: 'Globálne číselníky podľa rokov',
    });
    const rows = within(checklist).getAllByRole('row');
    const [, complete, incomplete] = rows;
    expect(complete && within(complete).getAllByText('691 riadkov')).toHaveLength(4);
    expect(incomplete && within(incomplete).getAllByText('chýba')).toHaveLength(4);
    expect(await screen.findByText('Telekomunikačné služby')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Akcie:/ })).not.toBeInTheDocument();
  });
});
