import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi, type Call } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Faktúra (P2-M4-T08): what the demo's proposal page did, on a stored invoice: the two cards
// with copy buttons, "Iná položka", accepting (with the number's preview), correcting with
// codes from the lists, manual entry, unbooking, "Prečo práve toto", the history.

const base = `/api/customers/${BOLDOG.id}`;
const ID = 'inv-1';

const posting = (md: string, amount: number, text: string) => ({
  md,
  dal: '321 000',
  amount,
  text,
  stredisko: null,
  transfer: null,
});
const budget = (key: string, amount: number, text: string) => {
  const [ek, zdroj, oddiel, trieda, analytika] = key.split(' ');
  return {
    key,
    ek,
    zdroj,
    oddiel,
    trieda,
    analytika,
    amount,
    text,
    stredisko: null,
    transfer: null,
  };
};

const PROPOSAL = {
  invoice_id: ID,
  bundle_id: '00305863/2026-08',
  document: { series: 'FD', number: 'FD/144/26', booking_date: '2026-06-23' },
  supplier: { name: 'Slovak Telekom, a.s.', ico: '35763469', known: true },
  invoice: { number: '8390051427', gross: 93.71 },
  posting: [posting('518 003', 93.71, 'tel.poplatky')],
  budget: [budget('632005 41 01 110 000', 93.71, 'telefon,fax')],
  confidence: { overall: 0.95, ek: 0.95 },
  evidence: [
    {
      field: 'ek',
      source: 'supplier_memory',
      detail: 'FD/215/26 coded 632005 41 01 110 000 for this IČO',
    },
  ],
  alternatives: [
    {
      budget_key: '632003 41 01 110 001',
      md: '518 001',
      dal: '321 000',
      transfer: null,
      budget_text: 'MŠ - telefon',
      posting_text: 'tel. MŠ',
      score: 0.4,
      why: 'x',
    },
  ],
  validation: { ok: true, checks: [], errors: [], warnings: [] },
  needs_review: false,
  review_reasons: [],
};

function invoice(overrides: object = {}) {
  return {
    id: ID,
    customer_id: BOLDOG.id,
    channel: 'dataset',
    state: 'ready',
    source_ref: 'anchor-telekom',
    document_id: null,
    fields: {
      id: ID,
      supplier: { name: 'Slovak Telekom, a.s.', ico: '35763469' },
      customer: { name: 'Obec Boldog', ico: '00305863' },
      invoice: {
        number: '8390051427',
        issue_date: '2026-06-22',
        delivery_date: '2026-06-21',
        due_date: '2026-07-07',
        variable_symbol: '8390051427',
        currency: 'EUR',
      },
      handwritten: { date: '2026-06-23', number: '144' },
      totals: { gross: 93.71, vat_rates: [] },
      lines: [{ description: 'Poplatky', gross: 93.71 }],
      free_text: [],
      ocr_meta: { synthetic: true, confidence: {} },
      intake: { channel: 'dataset', format: null },
    },
    proposal: PROPOSAL,
    basis: {
      year: 2026,
      bundle_id: '00305863/2026-08',
      version_ids: ['v1'],
      conventions_revision: 1,
    },
    coding_error: null,
    needs_review: false,
    booking: null,
    number: null,
    paid_on: null,
    uploaded_at: '2026-01-01T07:00:00Z',
    uploaded_by: null,
    checked_at: '2026-01-01T07:00:00Z',
    coded_at: '2026-01-01T07:00:00Z',
    booked_at: null,
    exported_at: null,
    paid_at: null,
    discarded_at: null,
    discard_reason: null,
    extraction_error: null,
    actions: ['check', 'recode', 'book', 'discard'],
    ...overrides,
  };
}

const entry = (key: string, description: string, values: object = {}) => ({
  key,
  active: true,
  values: { description, ...values },
});

const LISTS = {
  budget_expense: [
    entry('632005 41 01 110 000', 'telefon,fax'),
    entry('632003 41 01 110 001', 'MŠ - telefon'),
    entry('637004 41 01 110 000', 'všeobecné služby'),
  ],
  accounts: [
    entry('518 003', 'telekomunikačné služby'),
    entry('518 001', 'služby MŠ'),
    entry('321 000', 'Dodávatelia'),
  ],
  transfers: [],
};

function detailApi(
  role: 'user' | 'viewer',
  current: object,
  extra: Parameters<typeof mockApi>[0] = {},
) {
  const lists = Object.fromEntries(
    Object.entries(LISTS).map(([kind, items]) => [
      `GET ${base}/codelists/${kind}/entries`,
      { body: { version: null, items, total: items.length } },
    ]),
  );
  return mockApi({
    'GET /api/me': { body: meAs(role) },
    [`GET ${base}/invoices/${ID}`]: { body: current },
    [`GET ${base}/invoices`]: { body: { items: [], total: 0 } },
    [`GET ${base}/number-series`]: { body: { year: 2026, items: [{ series: 'FD' }] } },
    ...lists,
    ...extra,
  });
}

const posted = (calls: Call[], step: string) =>
  calls.filter((c) => c.method === 'POST' && c.path === `${base}/invoices/${ID}/${step}`);

describe('the invoice detail', () => {
  it('lays the proposal out like TOPSET with copy buttons for values and lines', async () => {
    const user = userEvent.setup();
    detailApi('user', invoice());
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(await screen.findByRole('heading', { level: 1, name: 'Faktúra' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Zaúčtovanie záväzku' })).toBeVisible();
    const budgetCard = screen.getByRole('heading', { name: 'Rozpočet záväzku' }).parentElement;
    if (!budgetCard) throw new Error('no budget card');
    expect(
      within(budgetCard).getByRole('group', { name: 'Položka 632005 41 01 110 000' }),
    ).toBeVisible();
    expect(await screen.findByText('telekomunikačné služby')).toBeVisible();
    expect(screen.getByText('Istota 95 %')).toBeVisible();

    const [copyAmount] = screen.getAllByRole('button', { name: 'Kopírovať: Suma' });
    if (!copyAmount) throw new Error('no amount copy button');
    await user.click(copyAmount);
    expect(await navigator.clipboard.readText()).toBe('93,71');
    await user.click(screen.getByRole('button', { name: 'Kopírovať riadok zaúčtovania 1' }));
    expect(await navigator.clipboard.readText()).toBe('518 003\t321 000\t93,71\ttel.poplatky');
    await user.click(screen.getByRole('button', { name: 'Kopírovať riadok rozpočtu 1' }));
    expect(await navigator.clipboard.readText()).toBe('632005 41 01 110 000\t93,71\ttelefon,fax');
  });

  it('accepts the proposal as it is when booking moves nothing', async () => {
    const user = userEvent.setup();
    const booked = invoice({
      state: 'booked',
      number: 'FD/144/26',
      booking: {
        coding: PROPOSAL,
        action: 'accepted',
        at: '2026-06-23T08:00:00Z',
        by: 'u-user',
        note: null,
      },
      booked_at: '2026-06-23T08:00:00Z',
      actions: ['unbook', 'export', 'pay'],
    });
    let current: object = invoice();
    const { calls } = detailApi('user', invoice(), {
      [`GET ${base}/invoices/${ID}`]: () => ({ body: current }),
      [`POST ${base}/invoices/${ID}/booking-preview`]: {
        body: { number: 'FD/144/26', requested: 'FD/144/26', moved: false, shifts: [] },
      },
      [`POST ${base}/invoices/${ID}/book`]: () => {
        current = booked;
        return {
          body: {
            invoice: booked,
            placement: { number: 'FD/144/26', requested: 'FD/144/26', moved: false, shifts: [] },
          },
        };
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    await user.click(await screen.findByRole('button', { name: 'Prijať' }));
    expect(await screen.findByText('Zaúčtované pod číslom FD/144/26.')).toBeVisible();
    const [book] = posted(calls, 'book');
    expect(book?.body).toMatchObject({
      action: 'accepted',
      coding: { document: PROPOSAL.document, posting: PROPOSAL.posting, budget: PROPOSAL.budget },
    });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Faktúra FD/144/26' }),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Zrušiť zaúčtovanie' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Prijať' })).toBeNull();
  });

  it('swaps a whole line for an alternative and confirms the numbers it moves', async () => {
    const user = userEvent.setup();
    const shifts = [{ invoice_id: 'inv-9', old: 'FD/144/26', new: 'FD/145/26' }];
    const { calls } = detailApi('user', invoice(), {
      [`POST ${base}/invoices/${ID}/booking-preview`]: {
        body: { number: 'FD/144/26', requested: 'FD/144/26', moved: false, shifts },
      },
      [`POST ${base}/invoices/${ID}/book`]: {
        body: {
          invoice: invoice({ state: 'booked', number: 'FD/144/26', actions: [] }),
          placement: { number: 'FD/144/26', requested: 'FD/144/26', moved: false, shifts },
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    await user.click(
      await screen.findByLabelText('Iná položka pre riadok 1', { selector: 'input' }),
    );
    await user.click(await screen.findByRole('option', { name: /^632003 41 01 110 001/ }));
    expect(screen.getByRole('group', { name: 'Položka 632003 41 01 110 001' })).toBeVisible();
    expect(screen.getByText('tel. MŠ')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Prijať so zmenou' }));
    const dialog = await screen.findByRole('dialog', { name: 'Zaúčtovanie' });
    expect(dialog).toHaveTextContent('Doklad dostane číslo FD/144/26.');
    expect(dialog).toHaveTextContent('FD/144/26 → FD/145/26');
    await user.click(within(dialog).getByRole('button', { name: 'Zaúčtovať' }));
    await waitFor(() => {
      expect(posted(calls, 'book')).toHaveLength(1);
    });
    expect(posted(calls, 'book')[0]?.body).toMatchObject({
      action: 'corrected',
      coding: {
        posting: [{ md: '518 001', text: 'tel. MŠ', amount: 93.71 }],
        budget: [{ key: '632003 41 01 110 001', ek: '632003', analytika: '001' }],
      },
    });
  });

  it('corrects with codes from the lists, the picked position bringing its line', async () => {
    const user = userEvent.setup();
    const { calls } = detailApi('user', invoice(), {
      [`POST ${base}/invoices/${ID}/line`]: {
        body: {
          budget_key: '637004 41 01 110 000',
          md: '518 001',
          dal: '321 000',
          transfer: null,
          budget_text: 'služby',
          posting_text: 'služby obce',
          score: 0,
          why: 'x',
        },
      },
      [`POST ${base}/invoices/${ID}/booking-preview`]: {
        status: 422,
        body: {
          code: 'validation_failed',
          detail: [{ loc: ['body', 'coding'], msg: 'FD/144/26 is already used', type: 'x' }],
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    await user.click(await screen.findByRole('button', { name: 'Opraviť a prijať' }));
    const line = screen.getByRole('group', { name: 'Riadok 1' });
    await user.click(within(line).getByLabelText('Rozpočtová položka', { selector: 'input' }));
    await user.click(await screen.findByRole('option', { name: /všeobecné služby/ }));
    await waitFor(() => {
      expect(within(line).getByLabelText('Popis v zaúčtovaní')).toHaveValue('služby obce');
    });
    expect(posted(calls, 'line')[0]?.body).toEqual({ budget_key: '637004 41 01 110 000' });
    expect(within(line).getByLabelText('Účet MD', { selector: 'input' })).toHaveValue(
      '518 001 · služby MŠ',
    );

    await user.click(screen.getByRole('button', { name: 'Pridať riadok' }));
    expect(screen.getByRole('button', { name: 'Uložiť opravu' })).toBeDisabled();
    expect(screen.getByText('Riadok 2: položka „—“ nie je v rozpočte.')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Odstrániť riadok 2' }));
    expect(screen.getByRole('button', { name: 'Uložiť opravu' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Uložiť opravu' }));
    expect(await screen.findByText('číslo FD/144/26 je už použité')).toBeVisible();
    expect(posted(calls, 'booking-preview')[0]?.body).toMatchObject({ action: 'corrected' });
    await user.click(screen.getByRole('button', { name: 'Zrušiť' }));
    expect(screen.getByRole('group', { name: 'Položka 632005 41 01 110 000' })).toBeVisible();
  });

  it('offers manual entry when nothing was proposed', async () => {
    const user = userEvent.setup();
    detailApi(
      'user',
      invoice({ proposal: { ...PROPOSAL, posting: [], budget: [], alternatives: [] } }),
    );
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(await screen.findByRole('heading', { name: 'Ručné zaúčtovanie' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Zadať ručne' }));
    const line = screen.getByRole('group', { name: 'Riadok 1' });
    expect(within(line).getByLabelText('Suma')).toHaveValue('93,71');
    expect(screen.getByRole('button', { name: 'Uložiť opravu' })).toBeDisabled();
  });

  it('unbooks a booked invoice with a reason', async () => {
    const user = userEvent.setup();
    const booked = invoice({
      state: 'booked',
      number: 'FD/144/26',
      booking: {
        coding: PROPOSAL,
        action: 'corrected',
        at: '2026-06-23T08:00:00Z',
        by: 'u-user',
        note: null,
      },
      booked_at: '2026-06-23T08:00:00Z',
      actions: ['unbook', 'export', 'pay'],
    });
    const { calls } = detailApi('user', booked, {
      [`POST ${base}/invoices/${ID}/unbook`]: { body: invoice() },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(await screen.findByText('Oprava uložená')).toBeVisible();
    expect(screen.queryByLabelText('Iná položka pre riadok 1')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Zrušiť zaúčtovanie' }));
    const dialog = await screen.findByRole('dialog', { name: 'Zrušiť zaúčtovanie' });
    await user.type(within(dialog).getByLabelText('Dôvod (nepovinné)'), 'zlý dodávateľ');
    await user.click(within(dialog).getByRole('button', { name: 'Zrušiť zaúčtovanie' }));
    expect(await screen.findByText('Zaúčtovanie zrušené.')).toBeVisible();
    expect(posted(calls, 'unbook')[0]?.body).toEqual({ reason: 'zlý dodávateľ' });
  });

  it('explains the proposal and shows the history with names', async () => {
    const user = userEvent.setup();
    detailApi('viewer', invoice(), {
      [`GET ${base}/invoices/${ID}/history`]: {
        body: {
          items: [
            {
              kind: 'created',
              at: '2026-01-01T07:00:00Z',
              actor_id: null,
              real_actor_id: null,
              from_state: null,
              to_state: 'extracted',
              details: { channel: 'dataset' },
            },
            {
              kind: 'booked',
              at: '2026-06-23T08:00:00Z',
              actor_id: 'u-user',
              real_actor_id: 'u-admin',
              from_state: 'ready',
              to_state: 'booked',
              details: { action: 'accepted', number: 'FD/144/26' },
            },
          ],
          names: { 'u-user': 'Jana Vzorová', 'u-admin': 'Alena Správcová' },
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    await screen.findByRole('heading', { name: 'Zaúčtovanie záväzku' });
    expect(screen.queryByRole('button', { name: 'Prijať' })).toBeNull();
    expect(screen.queryByLabelText('Iná položka pre riadok 1')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Prečo práve toto' }));
    expect(await screen.findByText('precedens dodávateľa')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'História' }));
    const rows = await screen.findAllByRole('row');
    expect(rows[1]).toHaveTextContent('Vytvorená');
    expect(rows[1]).toHaveTextContent('systém');
    expect(rows[2]).toHaveTextContent('Alena Správcová ako Jana Vzorová');
    expect(rows[2]).toHaveTextContent('číslo FD/144/26 · návrh prijatý');

    await user.click(screen.getByRole('tab', { name: 'Údaje faktúry' }));
    expect(await screen.findByText('Číslo rukou na doklade')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Vstup z OCR (JSON)' }));
    expect(await screen.findByText(/"handwritten"/)).toBeInTheDocument();
  });
});
