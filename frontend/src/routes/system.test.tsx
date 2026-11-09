import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Systém (P2-M2-T09): the parameters form with the API's 422, the conventions editor (rule
// order, a new rule, saving with the revision, a conflict), read-only for a viewer, and the
// health report's findings with their links.

const base = `/api/customers/${BOLDOG.id}`;

const parameters = {
  customer_id: BOLDOG.id,
  year: 2026,
  values: {
    vat_payer: false,
    default_zdroj: '41',
    default_series: 'FD',
    default_dal: '321 000',
    canteen_series: 'FDŠJ',
    canteen_dal: '321 080',
  },
};

const conventions = {
  customer_id: BOLDOG.id,
  year: 2026,
  revision: 3,
  updated_at: '2026-11-08T10:00:00Z',
  updated_by: 'u1',
  document: {
    au_rules: {
      debit: {
        '518': {
          default: '000',
          rules: [
            {
              au: '003',
              concepts: ['telecom'],
              function: [],
              ek: [],
              zdroj: [],
              terms: [],
              note: 'telekom',
            },
            {
              au: '004',
              concepts: ['waste'],
              function: [],
              ek: [],
              zdroj: [],
              terms: [],
              note: null,
            },
          ],
        },
      },
      credit: {},
    },
    canteen: null,
    concepts: {},
    transfers: { never: [] },
  },
};

const health = {
  year: 2026,
  errors: 0,
  warnings: 2,
  findings: [
    {
      code: 'ek_without_bridge',
      severity: 'warning',
      subject: '611000',
      where: null,
      kind: 'budget_expense',
      count: 8,
      message: '',
    },
    {
      code: 'convention_missing_account',
      severity: 'warning',
      subject: '518 010',
      where: 'debit 518',
      kind: 'accounts',
      count: 1,
      message: '',
    },
    {
      code: 'list_missing',
      severity: 'info',
      subject: 'cost_centres',
      where: null,
      kind: 'cost_centres',
      count: 1,
      message: '',
    },
  ],
};

function systemApi(role: 'viewer' | 'user', extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs(role) },
    [`GET ${base}/codelists`]: { body: { year: 2026, years: [2026], lists: [] } },
    [`GET ${base}/parameters`]: { body: parameters },
    [`GET ${base}/conventions`]: { body: conventions },
    [`GET ${base}/health`]: { body: health },
    ...extra,
  });
}

describe('Systém: parametre', () => {
  it('saves the parameters and lands a 422 on its field', async () => {
    const user = userEvent.setup();
    const { calls } = systemApi('user', {
      [`PUT ${base}/parameters`]: {
        status: 422,
        body: {
          detail: [{ loc: ['body', 'values', 'default_series'], msg: 'x', type: 'unknown_series' }],
          code: 'validation_failed',
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/system`);
    const series = await screen.findByLabelText(/^Predvolená rada/);
    expect(series).toHaveValue('FD');
    await user.clear(series);
    await user.type(series, 'FX');
    await user.click(screen.getByRole('button', { name: 'Uložiť' }));
    await waitFor(() => {
      expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
        values: { ...parameters.values, default_series: 'FX' },
      });
    });
    expect(await screen.findByText('x')).toBeInTheDocument();
  });

  it('checks the account shape before sending', async () => {
    const user = userEvent.setup();
    const { calls } = systemApi('user');
    await renderApp(`/c/${BOLDOG.id}/system`);
    const dal = await screen.findByLabelText(/^Účet záväzku \(DAL\)/);
    await user.clear(dal);
    await user.type(dal, '321000');
    await user.click(screen.getByRole('button', { name: 'Uložiť' }));
    expect(await screen.findByText('Účet v tvare SÚ AÚ, napr. 321 000.')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'PUT')).toBe(false);
  });
});

describe('Systém: účtovacie zvyklosti', () => {
  it('reorders rules, adds one and saves the document with its revision', async () => {
    const user = userEvent.setup();
    const { calls } = systemApi('user', {
      [`PUT ${base}/conventions`]: ({ body }) => ({
        body: { ...conventions, revision: 4, document: (body as { document: object }).document },
      }),
    });
    await renderApp(`/c/${BOLDOG.id}/system`);
    await user.click(await screen.findByRole('tab', { name: 'Účtovacie zvyklosti' }));
    const rules = await screen.findByRole('region', { name: 'Pravidlá pre SÚ 518' });
    expect(within(rules).getAllByRole('row')).toHaveLength(3);
    await user.click(screen.getByRole('button', { name: 'Posunúť pravidlo 2 pre SÚ 518 vyššie' }));
    await user.click(screen.getByRole('button', { name: 'Pridať pravidlo pre SÚ 518' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^AÚ/), '010');
    await user.type(
      within(dialog).getByRole('combobox', { name: 'Pojmy' }),
      'municipal_company{enter}',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Použiť' }));
    await user.click(screen.getByRole('button', { name: 'Uložiť zvyklosti' }));
    await waitFor(() => {
      expect(calls.some((c) => c.method === 'PUT')).toBe(true);
    });
    const put = calls.find((c) => c.method === 'PUT')?.body as {
      revision: number;
      document: {
        au_rules: { debit: Record<string, { rules: { au: string; concepts: string[] }[] }> };
      };
    };
    expect(put.revision).toBe(3);
    expect(put.document.au_rules.debit['518']?.rules.map((r) => r.au)).toEqual([
      '004',
      '003',
      '010',
    ]);
    expect(put.document.au_rules.debit['518']?.rules[2]?.concepts).toEqual(['municipal_company']);
  });

  it('says so when someone saved in between', async () => {
    const user = userEvent.setup();
    systemApi('user', {
      [`PUT ${base}/conventions`]: { status: 409, body: { detail: 'stale', code: 'conflict' } },
    });
    await renderApp(`/c/${BOLDOG.id}/system`);
    await user.click(await screen.findByRole('tab', { name: 'Účtovacie zvyklosti' }));
    await user.click(
      await screen.findByRole('button', { name: 'Odstrániť pravidlo 2 pre SÚ 518' }),
    );
    await user.click(screen.getByRole('button', { name: 'Uložiť zvyklosti' }));
    expect(await screen.findByText(/Medzitým zvyklosti niekto uložil/)).toBeInTheDocument();
  });

  it('is read-only for a viewer', async () => {
    const user = userEvent.setup();
    systemApi('viewer');
    await renderApp(`/c/${BOLDOG.id}/system`);
    expect(await screen.findByLabelText(/^Predvolená rada/)).toHaveAttribute('readonly');
    expect(screen.queryByRole('button', { name: 'Uložiť' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Účtovacie zvyklosti' }));
    await screen.findByRole('region', { name: 'Pravidlá pre SÚ 518' });
    expect(screen.queryByRole('button', { name: 'Uložiť zvyklosti' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Pridať pravidlo/ })).not.toBeInTheDocument();
  });
});

describe('Systém: kontrola znalostí', () => {
  it('lists the findings in Slovak with links to what they concern', async () => {
    const user = userEvent.setup();
    systemApi('user');
    await renderApp(`/c/${BOLDOG.id}/system`);
    await user.click(await screen.findByRole('tab', { name: 'Kontrola znalostí' }));
    expect(
      await screen.findByText(
        'EK 611000 nemá pravidlo pre syntetický účet; jej 8 položiek sa nenavrhuje.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Zvyklosť (MD, SÚ 518) uvádza účet 518 010, ktorý v účtovom rozvrhu nie je.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('2 upozornenia')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Výdavkový rozpočet' });
    // The router writes a number-like string JSON-quoted, and reads it back as a string.
    expect(decodeURIComponent(link.getAttribute('href') ?? '')).toContain('q="611000"');
    await user.click(screen.getByRole('button', { name: 'Účtovacie zvyklosti' }));
    expect(await screen.findByRole('region', { name: 'Pravidlá pre SÚ 518' })).toBeInTheDocument();
  });
});
